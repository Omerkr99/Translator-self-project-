"""Container-level service used by both CLI and desktop Asset Browser."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from gcrts.asset_compression import decode_stream, discover_streams, encode_stream, pad_to_exact_size
from gcrts.asset_descriptor import AssetDescriptor, SizePolicy
from gcrts.asset_registry import descriptors_for_file
from gcrts.asset_tim import EditableTim, decode_tim, encode_tim


@dataclass(frozen=True)
class EncodingBudget:
    original_size:int; raw_encoded_size:int; final_size:int|None; safe:bool; detail:str


class AssetProject:
    def __init__(self, source: bytes, disc_path: str):
        self.source=bytes(source);self.disc_path=disc_path
        self.records=discover_streams(self.source,32 if "MENUDAT" in disc_path.upper() else 15)
        self.descriptors=descriptors_for_file(self.source,disc_path)
        self._edits:dict[int,EditableTim]={}

    @classmethod
    def open(cls,path:str|Path,disc_path:str):return cls(Path(path).read_bytes(),disc_path)
    def descriptor(self,asset_id:str)->AssetDescriptor:return next(d for d in self.descriptors if d.id==asset_id)
    def tim(self,block:int)->EditableTim:return self._edits.get(block) or decode_tim(self.records[block].decoded)
    def set_tim(self,block:int,tim:EditableTim)->None:self._edits[block]=tim
    def export_png(self,block:int,path:str|Path)->None:self.tim(block).export_png(path)
    def composite_image(self,members:list[int]|tuple[int,...])->Image.Image:
        images=[self.tim(block).to_image() for block in members]
        if not images:raise ValueError("composite requires at least one member")
        if len({image.height for image in images})!=1:raise ValueError("composite members must have equal heights")
        output=Image.new("RGBA",(sum(image.width for image in images),images[0].height))
        x=0
        for image in images:output.alpha_composite(image,(x,0));x+=image.width
        return output
    def export_composite_png(self,members:list[int]|tuple[int,...],path:str|Path)->None:self.composite_image(members).save(path,"PNG")
    def replace_composite_png(self,members:list[int]|tuple[int,...],source:str|Path|Image.Image)->None:
        image=source.convert("RGBA") if isinstance(source,Image.Image) else Image.open(source).convert("RGBA")
        expected=self.composite_image(members).size
        if image.size!=expected:raise ValueError(f"PNG dimensions {image.size} do not match composite {expected}")
        replacements={};x=0
        for block in members:
            tim=self.tim(block);crop=image.crop((x,0,x+tim.width,tim.height));replacements[block]=tim.import_palette_preserving_png(crop);x+=tim.width
        self._edits.update(replacements)
    def replace_png(self,block:int,path:str|Path)->None:self.set_tim(block,self.tim(block).import_palette_preserving_png(path))
    def text_overlay(self,block:int,text:str,x:int,y:int,foreground_index:int=1,font_path:str|None=None,font_size:int=14,clear_existing:bool=False)->None:
        tim=self.tim(block)
        if tim.indices is None:raise ValueError("text overlay requires indexed TIM")
        mask=Image.new("1",(tim.width,tim.height));draw=ImageDraw.Draw(mask)
        font=ImageFont.truetype(font_path,font_size) if font_path else ImageFont.load_default()
        draw.text((x,y),text,font=font,fill=1,stroke_width=0)
        indices=bytearray(tim.indices)
        if clear_existing:
            transparent=next((i for i,value in enumerate(tim.palette) if value==0),None)
            if transparent is None:raise ValueError("asset palette has no transparent BGR555 entry")
            indices[:]=bytes((transparent,))*len(indices)
        for py in range(tim.height):
            for px in range(tim.width):
                if mask.getpixel((px,py)):indices[py*tim.width+px]=foreground_index
        self.set_tim(block,tim.with_indices(bytes(indices)))
    def budget(self,block:int)->EncodingBudget:
        desc=self.descriptors[block];raw=encode_stream(encode_tim(self.tim(block)));required=desc.container.compressed_size
        if desc.encoding_policy.size_mode==SizePolicy.UNKNOWN:return EncodingBudget(required,len(raw),None,False,"UNKNOWN policy blocks writing")
        if len(raw)>required:return EncodingBudget(required,len(raw),None,False,f"BLOCKED: exceeds budget by {len(raw)-required} bytes")
        if desc.encoding_policy.size_mode==SizePolicy.EXACT_CONSUMED_SIZE:
            try:final=pad_to_exact_size(raw,required)
            except ValueError as error:return EncodingBudget(required,len(raw),None,False,f"BLOCKED: {error}")
            return EncodingBudget(required,len(raw),len(final),True,f"SAFE: exact-size expansion adds {required-len(raw)} bytes")
        return EncodingBudget(required,len(raw),len(raw),True,"SAFE")
    def build(self)->bytes:
        output=bytearray(self.source)
        for block,tim in self._edits.items():
            desc=self.descriptors[block];budget=self.budget(block)
            if not budget.safe:raise ValueError(f"block {block}: {budget.detail}")
            encoded=encode_stream(encode_tim(tim))
            if desc.encoding_policy.size_mode==SizePolicy.EXACT_CONSUMED_SIZE:encoded=pad_to_exact_size(encoded,desc.container.compressed_size)
            start=desc.container.compressed_offset;output[start:start+desc.container.compressed_size]=encoded
        return bytes(output)
    def restore(self,block:int|None=None)->None:
        if block is None:self._edits.clear()
        else:self._edits.pop(block,None)
    def restore_composite(self,members:list[int]|tuple[int,...])->None:
        for block in members:self._edits.pop(block,None)

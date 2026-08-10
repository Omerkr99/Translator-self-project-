"""Read-only parser for PSYQ ordering-table packets in a 2 MiB RAM snapshot."""
from __future__ import annotations
import struct
from gcrts.gpu_asset_correlation import GpuPrimitive

def _u32(ram,address):return struct.unpack_from("<I",ram,address&0x1fffff)[0]
def _s16(value):value&=0xffff;return value-0x10000 if value&0x8000 else value
def _xy(word,offset):return _s16(word)+offset[0],_s16(word>>16)+offset[1]
def _uv(word):return word&255,(word>>8)&255
def _bounds(points):
    xs=[p[0] for p in points];ys=[p[1] for p in points];return min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)
def _uv_bounds(points):
    xs=[p[0] for p in points];ys=[p[1] for p in points];return min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)

def parse_ot(ram:bytes,root:int,frame_id:int=0,draw_offset=(0,0)):
    address=root&0x1fffff;seen=set();result=[]
    while address!=0x1fffff and address not in seen and len(seen)<10000:
        seen.add(address);header=_u32(ram,address);count=header>>24;next_address=header&0xffffff
        if count:
            words=[_u32(ram,address+4+i*4) for i in range(count)];command=words[0]>>24
            points=uvs=None;tpage=clut=0
            if 0x2c<=command<=0x2f and count>=9:
                points=[_xy(words[i],draw_offset) for i in (1,3,5,7)];uvs=[_uv(words[i]) for i in (2,4,6,8)];clut=words[2]>>16;tpage=words[4]>>16
            elif 0x3c<=command<=0x3f and count>=12:
                points=[_xy(words[i],draw_offset) for i in (1,4,7,10)];uvs=[_uv(words[i]) for i in (2,5,8,11)];clut=words[2]>>16;tpage=words[5]>>16
            elif 0x24<=command<=0x27 and count>=7:
                points=[_xy(words[i],draw_offset) for i in (1,3,5)];uvs=[_uv(words[i]) for i in (2,4,6)];clut=words[2]>>16;tpage=words[4]>>16
            elif 0x34<=command<=0x37 and count>=9:
                points=[_xy(words[i],draw_offset) for i in (1,4,7)];uvs=[_uv(words[i]) for i in (2,5,8)];clut=words[2]>>16;tpage=words[5]>>16
            if points and uvs:
                u,v,uw,vh=_uv_bounds(uvs);result.append(GpuPrimitive(frame_id,0x80000000|address,command,tpage,clut,u,v,uw,vh,_bounds(points)))
        address=next_address&0x1fffff
    return result

def draw_offset_from_environment(ram:bytes,root:int):
    header=_u32(ram,root);count=header>>24
    for i in range(count):
        word=_u32(ram,root+4+i*4)
        if word>>24==0xe5:
            x=word&0x7ff;y=(word>>11)&0x7ff
            return (x-2048 if x>=1024 else x,y-2048 if y>=1024 else y)
    return (0,0)

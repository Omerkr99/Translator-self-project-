import struct
import pytest
from PIL import Image
from gcrts.asset_tim import *

def fixture_4bpp():
    tim=EditableTim(0,4,2,bytes([0,1,1,0,1,0,0,1]),None,(0x0000,0x7fff)+tuple([0]*14),0,480,0,0)
    return tim

def test_tim_4bpp_binary_roundtrip_and_palette_preservation():
    original=fixture_4bpp();decoded=decode_tim(encode_tim(original))
    assert decoded==original
    assert decoded.usage_counts()[:2]==[4,4]

def test_tim_8bpp_and_16bpp_roundtrip():
    t8=EditableTim(1,2,1,b"\0\1",None,tuple(range(256)),0,0,0,0)
    t16=EditableTim(2,2,1,None,(0,0x7fff),(),0,0,0,0)
    assert decode_tim(encode_tim(t8))==t8
    assert decode_tim(encode_tim(t16))==t16

def test_png_export_preserves_zero_color_transparency(tmp_path):
    path=tmp_path/"x.png";fixture_4bpp().export_png(path);image=Image.open(path).convert("RGBA")
    assert image.getpixel((0,0))[3]==0 and image.getpixel((1,0))[3]==255

def test_nonzero_palette_index_can_be_transparent():
    tim=EditableTim(0,4,1,bytes([0,1,0,1]),None,(0x7fff,0)+tuple([0]*14),0,0,0,0)
    image=tim.to_image()
    assert image.getpixel((0,0))[3]==255 and image.getpixel((1,0))[3]==0

def test_palette_preserving_import_rejects_unknown_color():
    image=Image.new("RGBA",(4,2),(1,2,3,255))
    with pytest.raises(ValueError,match="not present"):fixture_4bpp().import_palette_preserving_png(image)

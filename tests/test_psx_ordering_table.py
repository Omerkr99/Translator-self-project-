import struct
from gcrts.psx_ordering_table import parse_ot,draw_offset_from_environment
def put(ram,address,words,next_=0xffffff):
    struct.pack_into("<I",ram,address,(len(words)<<24)|next_)
    for i,word in enumerate(words):struct.pack_into("<I",ram,address+4+i*4,word)
def test_parse_real_shape_gt4_for_block9():
    ram=bytearray(2*1024*1024);words=[0x3c8c8cc8,0x00180028,0x7a406000,0x008c8cc8,0x00180068,0x000a6040,0x003c3cc8,0x00380028,0x00008000,0x003c3cc8,0x00380068,0x00008040];put(ram,0x1000,words)
    p=parse_ot(bytes(ram),0x80001000,55)[0];assert (p.command,p.tpage,p.u,p.v,p.uv_width,p.uv_height,p.screen_bounds)==(0x3c,10,0,96,64,32,(40,24,64,32))
def test_environment_draw_offset_is_signed():
    ram=bytearray(2*1024*1024);put(ram,0x100,[0xe5078000]);assert draw_offset_from_environment(bytes(ram),0x100)==(0,240)

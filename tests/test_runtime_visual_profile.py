from pathlib import Path
import struct
from gcrts.runtime_visual_provider import RuntimeVisualProvider
def test_prog_ot_roots_require_exact_loaded_code_profile():
    exe=Path(__file__).parents[1]/"sdb_main_menu_asset"/"PROG.EXE";data=exe.read_bytes();base=struct.unpack_from("<I",data,0x18)[0];start=0x80049630;offset=0x800+start-base;ram=bytearray(2*1024*1024);provider=RuntimeVisualProvider([])
    assert provider._roots(bytes(ram))[1]==[]
    ram[start&0x1fffff:(start&0x1fffff)+0x4c]=data[offset:offset+0x4c]
    assert provider._roots(bytes(ram))[1]==[0x80076a24,0x80076a64,0x80075770,0x800757b0]

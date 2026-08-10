import pytest
from gcrts.asset_compression import *
from gcrts.cdb_codec import decompress

@pytest.mark.parametrize("data",[b"ABCD"*50,b"A"*100+bytes(range(100)),bytes(range(256))*3,b"0123456789"*500])
def test_encode_roundtrip(data):
    encoded=encode_stream(data)
    assert decompress(encoded)==data

def test_exact_size_expansion_preserves_decoded_data():
    data=b"A"*30+b"hello world"*8
    encoded=encode_stream(data)
    expanded=pad_to_exact_size(encoded,len(encoded)+20)
    assert len(expanded)==len(encoded)+20
    assert decompress(expanded)==data

def test_exact_size_rejects_oversize():
    with pytest.raises(ValueError):pad_to_exact_size(b"\x00A\xff",2)

def test_discover_streams_tracks_consumed_offsets():
    a=encode_stream(b"AAA");b=encode_stream(b"BBBB")
    records=discover_streams(a+b,2)
    assert [(r.block,r.offset,r.consumed_size,r.decoded) for r in records]==[(0,0,len(a),b"AAA"),(1,len(a),len(b),b"BBBB")]

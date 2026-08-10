from gcrts.asset_descriptor import *

def sample(policy=SizePolicy.EXACT_CONSUMED_SIZE):
    return AssetDescriptor("a","A","Game",AssetSource("disc_file","X.BIN;1"),ContainerLocation("streams",0,0,10,20),ImageMetadata("TIM_4BPP_INDEXED",8,8,16),EncodingPolicy(policy,10 if policy==SizePolicy.EXACT_CONSUMED_SIZE else None),capabilities=AssetCapabilities(reencode=policy!=SizePolicy.UNKNOWN))

def test_descriptor_serialization_roundtrip_and_unknown_fields():
    value=sample().to_dict();value["future_field"]={"safe":"ignored"}
    restored=AssetDescriptor.from_dict(value)
    assert restored==sample() and restored.validate()==[]

def test_unknown_policy_blocks_reencode_capability():
    base=sample(SizePolicy.UNKNOWN)
    bad=AssetDescriptor(**{**base.__dict__,"capabilities":AssetCapabilities(reencode=True)})
    assert any("UNKNOWN" in error for error in bad.validate())

def test_exact_policy_must_match_consumed_size():
    d=sample();d=AssetDescriptor(**{**d.__dict__,"encoding_policy":EncodingPolicy(SizePolicy.EXACT_CONSUMED_SIZE,9)})
    assert d.validate()

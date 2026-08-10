from gcrts.runtime_probe import RecordedRuntimeProbe,RuntimeObservation
from gcrts.runtime_asset_tracker import RuntimeAssetTracker
from gcrts.runtime_content_resolver import RuntimeContentResolver

class Index:
    def resolve_runtime_signature(self,prefix,compressed_size,size):
        from gcrts.runtime_content import CanonicalAssetIdentity,RuntimeConfidence
        return (CanonicalAssetIdentity("category.photos",block=9),RuntimeConfidence.LIVE_STRUCTURAL_MATCH) if (prefix,compressed_size,size)==("abcd",617,2080) else (None,RuntimeConfidence.UNKNOWN)

def test_recorded_decode_observation_resolves_block9_and_preserves_pointers():
    event=RuntimeObservation("DECOMPRESS",42,{"source_ptr":0x1000,"compressed_size":617,"compressed_prefix":"abcd","decoded_ptr":0x2000,"decoded_size":2080,"caller":0x80001234})
    tracker=RuntimeAssetTracker();instance=RuntimeContentResolver(tracker,[Index()]).consume(next(RecordedRuntimeProbe([event]).observations()))
    assert instance.asset_id=="category.photos" and instance.decoded_ptr==0x2000 and tracker.events[-1].frame_id==42

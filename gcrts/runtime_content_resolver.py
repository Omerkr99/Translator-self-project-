"""Consumes transport observations and resolves them into tracker instances."""
from gcrts.runtime_content import RuntimeConfidence

class RuntimeContentResolver:
    def __init__(self,tracker,fingerprint_indexes):self.tracker=tracker;self.indexes=tuple(fingerprint_indexes)
    def consume(self,observation):
        self.tracker.begin_frame(observation.frame_id)
        if observation.kind!="DECOMPRESS":return None
        fields=observation.fields;identity=confidence=None
        for index in self.indexes:
            identity,confidence=index.resolve_runtime_signature(fields["compressed_prefix"],fields["compressed_size"],fields["decoded_size"])
            if identity:break
        instance=self.tracker.loaded(identity.asset_id if identity else None,compressed_ptr=fields["source_ptr"],confidence=confidence or RuntimeConfidence.UNKNOWN,caller=fields.get("caller"))
        return self.tracker.decompressed(instance.runtime_instance_id,decoded_ptr=fields["decoded_ptr"],decoded_size=fields["decoded_size"],asset_id=identity.asset_id if identity else None,confidence=confidence)

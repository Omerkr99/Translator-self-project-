# Asset Inspector Architecture

The implemented dependency direction is:

```text
Tk Asset Browser / asset_cli
        -> AssetProject
        -> AssetDescriptor + AssetRegistry
        -> compression adapter -> decoded TIM bytes
        -> TIM adapter -> indexed/direct pixels
        -> safe workspace / temporary patch provider
```

UI modules contain no TIM parsing or compression-token logic. `AssetProject`
coordinates format-independent operations and enforces descriptor size policy.
`PcsxReduxPatchProvider` is temporary-only; no persistent disc builder exists.

Current modules:

- `asset_descriptor.py`: typed schema, capabilities, status and size policies.
- `asset_compression.py`: discovery, decode, deterministic encode, exact sizing.
- `asset_tim.py`: editable TIM 4/8/16bpp model, CLUT and PNG operations.
- `asset_registry.py`: Twilight Syndrome manually verified descriptors.
- `asset_project.py`: container editing, budgets and safe reconstruction.
- `asset_workspace.py`: immutable-source copies, outputs, hashes and journal.
- `pcsx_patch.py`: PCSX-Redux temporary patch/clear boundary.
- `asset_inspector_ui.py`: Tk browser and inspector.
- `asset_cli.py`: automation over the same backend.

SDB2.0, SDB2.2, MS4 and GP4 remain unsupported placeholders by policy; no
speculative decoder is present.

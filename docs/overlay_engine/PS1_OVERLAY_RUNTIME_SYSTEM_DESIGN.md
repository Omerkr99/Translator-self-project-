# PS1 Overlay & Runtime Manipulation Engine

System Design Document (SDD) — Architecture, Patch Model, Emulator Integration, and Toolkit Integration

Project: PS1 Localization Toolkit / Twilight Syndrome reference implementation

## 1. Design Goals

- Provide a permanent internal runtime layer that becomes part of a modified game image and can render/synchronize localization content from inside the game.

- Provide a separate external emulator overlay for development, QA, synchronization experiments, screenshots, and diagnostics.

- Keep both overlays driven by one shared Runtime Context and Overlay Action model so tests can move from external proof to internal proof without rewriting scenarios.

- Keep BIOS, game image, emulator, save-state, and adapter-specific information outside the distributed Toolkit and supplied/configured by the user.

- Make the architecture reusable for future PS1 game adapters while allowing deep Twilight Syndrome-specific hooks and profiles.

## 2. Top-Level Architecture

```text
+-------------------------- User Inputs ---------------------------+
| Game Disc Image | BIOS Path | Emulator | Saves | Overlay Pack   |
+------------------------------+----------------------------------+
|
v
+-----------------------+
| Toolkit Project Model |
+-----------+-----------+
|
+------------------+------------------+
|                                     |
v                                     v
+----------------------------+       +-----------------------------+
| External Runtime Service   |       | Internal Patch Builder      |
| - Emulator Adapter         |       | - Adapter/Profile Resolver  |
| - Context Resolver         |       | - Hook Planner              |
| - External Overlay Window  |       | - Payload Linker/Allocator  |
| - Host Audio               |       | - Disc/Image Rebuilder      |
| - Screenshot/Test Runner   |       | - Patch Manifest            |
+-------------+--------------+       +--------------+--------------+
|                                     |
v                                     v
Running Emulator                       Patched Game Image
|                                     |
+------------------+------------------+
v
Evidence / Validation Store
```

## 3. Two-Overlay Model

| Aspect | External Overlay | Internal Overlay |
| --- | --- | --- |
| Runs where? | Host OS, beside/over emulator output | Inside PS1 game runtime from patched code/data |
| Primary purpose | QA, debugging, screenshots, fast timing experiments | Permanent localization/runtime manipulation |
| Needs game image modification? | No | Yes |
| Can prove game itself was modified? | No | Yes |
| Audio | Easy host-side synchronized playback | Future native audio path or asset replacement |
| Movie subtitles | Can be prototyped early | Needs validated movie-time/post-frame hook |
| Failure risk | Low | Higher; must fail-open and be reversible |

## 4. External Overlay Architecture

### 4.1 Components

- EmulatorManager: starts or attaches to the emulator process.

- EmulatorAdapter: normalized interface for memory, breakpoints, screenshots, save states, timing, and optional audio controls.

- PCSXReduxAdapter: first implementation using the project's existing GDB remote workflows and Web API where available.

- RuntimeContextResolver: converts raw emulator/game observations into a normalized RuntimeContext.

- ExternalOverlayRenderer: transparent desktop overlay/HUD aligned to emulator output; supports text, subtitles, debug panels, and visual test markers.

- HostAudioBridge: plays synchronized WAV/other host audio for proof-of-timing tests without claiming PS1-native replacement.

- LiveTestRunner: runs scripted scenarios, requests screenshots, evaluates conditions, and writes evidence bundles.

### 4.2 Emulator Adapter Interface

```text
class EmulatorAdapter:
capabilities() -> EmulatorCapabilities
launch(config) -> Session
attach(config) -> Session
pause()
resume()
read_memory(addr, size) -> bytes
write_memory(addr, data)
set_breakpoint(addr)
clear_breakpoint(addr)
screenshot() -> Image
load_state(path)
get_frame_counter() -> Optional[int]
get_audio_controls() -> Optional[AudioControl]
shutdown()
```

Each adapter advertises capabilities. A test may require MEMORY_READ + SCREENSHOT but not BREAKPOINTS; unsupported capabilities yield UNSUPPORTED rather than false failure.

## 5. Internal Overlay Architecture

### 5.1 Persistent Payload

The internal overlay is built as a small PS1-side runtime payload inserted into safe executable or allocated game data space, with one or more hooks from game code. The exact storage location is adapter-specific and must be validated against each executable/overlay layout.

```text
Patched Game Boot / Executable Load
|
v
OverlayBootstrap()
|
+--> validate magic/version/config
+--> install or activate runtime state
+--> register per-frame / event hook
|
v
OverlayKernelTick()
|
+--> read RuntimeContext mirror
+--> update timers/actions
+--> select renderer backend
+--> emit GPU/text/audio actions
```

### 5.2 Internal Modules

| Module | Responsibility |
| --- | --- |
| OverlayBootstrap | Initialize persistent state; verify payload/config version; enter safe mode if invalid. |
| OverlayKernel | Small deterministic per-frame/event scheduler. |
| RuntimeContextMirror | PS1-side compact structure containing mode, scene/movie IDs, timer/frame, active action IDs. |
| ActionScheduler | Start/stop timed overlays and event-triggered actions. |
| TextBackend | Reuse validated game text renderer where possible. |
| GpuOverlayBackend | Future generic primitive/textured-quad renderer for contexts where game text renderer is unavailable. |
| MovieOverlayBackend | Future post-frame composition hook; feature-gated until movie timing/render path is proven. |
| AudioBackend | Initially event markers only; later native playback/replacement after validated write path. |
| Health/SafeMode | Watchdog flags, disable switch, and fail-open policy. |

## 6. Hook Strategy

Hooks must be chosen in descending order of safety and evidence:

1. Use an already-live-confirmed high-level game render/update function when available.

1. Use an executable-specific per-frame function identified through static/runtime evidence.

1. Use a lower-level GPU submission hook only when the higher-level route cannot work and ordering is understood.

1. For movies, require a hook after movie frame upload/composition and before display/flip; do not assume the normal gameplay renderer survives movie overlay residency.

| Critical movie constraint: The current audit explicitly says movie-time source, PS1-side movie render hook, and VRAM write/composition path are not yet proven. MovieOverlayBackend must remain disabled until those prerequisites are individually validated. |
| --- |

## 7. Payload Placement & Game Image Patching

| Design concern | Approach |
| --- | --- |
| Where payload lives | Prefer unused executable/code cave only after static verification; otherwise add/expand a dedicated file/region and patch loader logic. Never assume free space. |
| Executable growth | Track file size, load address, BSS/heap overlap, sector alignment, and file-system metadata. |
| Hooks | Record original instruction bytes; replace with J/JAL/trampoline as architecture permits; preserve delay-slot semantics. |
| Long jumps | Use a trampoline when target cannot be reached safely with direct branch form. |
| Data/config | Embed compact overlay package metadata plus text/action tables, with version/magic and bounds checks. |
| Disc rebuild | Update image/file extents only through a deterministic builder aware of the game's loader assumptions. |
| Distribution | Prefer patch files against user-owned source image; do not redistribute original game/BIOS data. |

## 8. Overlay Package Format

```text
OverlayPackage
header:
magic
format_version
target_game_id
target_adapter_version
build_id
resources:
strings
subtitle_tracks
images/tiles (optional)
event maps
audio event metadata
actions:
trigger
target_context
start
duration/end
priority
backend
payload_ref
validation:
bounds
hashes
required capabilities
```

## 9. Runtime Context Architecture

```text
RuntimeContext
game_id
executable_id
mode: BOOT | MENU | GAMEPLAY | DIALOGUE | MOVIE | UNKNOWN
chapter_id?
scene_id?
dialogue_id?
movie_id?
audio_asset_id?
renderer_profile?
frame_counter?
time_source?
confidence[]
```

The host resolver may know more than the PS1-side payload. The internal payload receives only the compact subset necessary to schedule actions. Adapter-specific detectors feed the common model.

## 10. External/Inner Overlay Coordination

```text
Same Test Scenario
|
+--> External backend
|      ShowText("TOOLKIT TEST", 3s)
|      Capture host screenshot
|
+--> Internal backend
Schedule action ID 0x0021
PS1 renders text
Capture framebuffer
```

This shared scenario model is central: the external overlay is the fast proof environment; the internal overlay is the final game-resident implementation. The same desired behavior should be testable through both backends.

## 11. BIOS, Emulator, and Game Configuration

| Config area | Fields |
| --- | --- |
| Game | disc_image_path, optional cue_path, expected_serial, region, source_hash |
| BIOS | bios_path, optional expected hash, region compatibility |
| Emulator | adapter_type, executable_path, launch_args, gdb_host/port, api_host/port, window matching rules |
| Runtime | auto_launch, auto_attach, save_state_path, memory_card_path, timeout policies |
| Overlay | external enabled, internal enabled, HUD mode, default test sentence, screenshot directory |
| Build | workspace, output image, patch format, adapter/profile version, reproducible build options |

Configuration stores paths and metadata only. BIOS and disc contents are never copied into distributable Toolkit assets.

## 12. Screenshot & Evidence Pipeline

```text
Test Runner
|
+--> resolve context
+--> schedule overlay action
+--> wait until visible condition
+--> capture:
|      host screenshot
|      emulator/framebuffer screenshot (when supported)
|      runtime context JSON
|      action log
|      memory/build hashes
+--> evaluate assertions
+--> produce EvidenceBundle
```

| Evidence item | External proof | Internal proof |
| --- | --- | --- |
| Overlay screenshot | Host/composited screenshot | Framebuffer/emulator screenshot showing in-game rendering |
| Runtime log | Required | Required |
| Build hash | Optional | Required |
| Patch manifest | N/A | Required |
| Backend marker | EXTERNAL_HOST | INTERNAL_PS1 |

## 13. Live Demo Suite

| Demo | Expected result | Backend priority |
| --- | --- | --- |
| Generic gameplay sentence | English sentence appears for 3–5 s from arbitrary supported gameplay state | External first, then Internal |
| Persistent watermark | Small overlay remains stable for ~10 s and disappears cleanly | Both |
| Dialogue synchronized caption | Caption begins on dialogue event | External first; Internal after text hook proof |
| Movie subtitle | Caption appears over known movie with stable timing | External first; Internal only after movie backend prerequisites |
| Audio synchronization | Known event triggers chosen English audio | External host audio first; native later |

## 14. Toolkit Integration

```text
ps1_localization_toolkit/
core/
binary/
mips/
disc/
evidence/
project_model/
runtime/
emulator/
base.py
pcsx_redux.py
<future_emulator>.py
context/
capture/
validation/
overlay/
model/
external/
internal/
payload/
hooks/
backends/
tests/
patching/
planner/
allocator/
image_builder/
manifest/
adapters/
twilight_syndrome/
runtime_profiles/
overlay_hooks/
render_backends/
assets/
```

## 15. Build Pipeline

1.  Validate user inputs and compute source hashes.

2.  Identify game/version and load the matching adapter/profile.

3.  Run static safety checks and produce a patch plan.

4.  Allocate payload and resource regions.

5.  Patch hooks/trampolines while preserving delay slots and original bytes.

6.  Embed overlay package/config.

7.  Rebuild the working game image deterministically.

8.  Emit patch package + manifest + modified working image if the user requested it.

9.  Launch the configured emulator with user-supplied BIOS and output image.

10.  Run smoke tests and capture an EvidenceBundle.

## 16. Failure & Recovery Design

| Failure | Behavior |
| --- | --- |
| Wrong game/version | Abort writes; allow read-only inspection. |
| Unknown hook address | Mark UNSUPPORTED; never patch guessed address. |
| Payload collision | Abort build and emit allocation report. |
| Internal overlay crash/invalid config | Safe-mode bypass when reachable; preserve clean rebuild path. |
| Emulator connection failure | External test fails cleanly; built image remains valid artifact. |
| Movie backend unavailable | External subtitles may run; internal movie overlay stays disabled. |

## 17. Security / Integrity / Legal Boundaries

- No BIOS distribution or embedded BIOS blobs.

- No original copyrighted game image distribution.

- Patch artifacts should contain only differences/metadata necessary to transform a user-owned source.

- Every write operation requires a recognized adapter/profile and source hash or explicit expert override.

- Original image remains immutable; all modifications occur in a build workspace.

## 18. Implementation Phases

| Phase | Deliverable | Exit criterion |
| --- | --- | --- |
| O0 | External overlay foundation | PCSX-Redux launch/attach + context HUD + timed English sentence + screenshot. |
| O1 | Shared OverlayAction model + test runner | Same scenario executes through external backend with evidence bundle. |
| O2 | Internal gameplay payload prototype | Patched image boots and internally renders a timed English sentence in one confirmed gameplay context. |
| O3 | Persistent internal packaging | Payload/hooks survive reboot/reload and build is reproducible from clean image. |
| O4 | Cross-context gameplay coverage | Additional executable/renderer profiles selected dynamically. |
| O5 | External movie subtitle timing | Known movie detected and host subtitle timeline stays synchronized. |
| O6 | Internal movie backend research | Movie time source + safe post-frame hook + framebuffer proof are individually confirmed. |
| O7 | Internal movie subtitle | English subtitle visible in PS1 framebuffer during movie without breaking playback. |
| O8 | Audio synchronization/replacement expansion | Host sync first; PS1-native replacement only after validated asset write/rebuild path. |

## 19. Current Known Constraints from Readiness Audit

- Gameplay overlay is a substantially more realistic first internal proof than movie overlay.

- A PS1-native movie subtitle backend is not yet a simple integration task: movie-time source, post-frame hook, and write/composition path are still unknown.

- The existing automated suite is strong as a regression net but has zero live-emulator tests; the new overlay subsystem should deliberately add repeatable live evidence bundles.

- Game-specific addresses and runtime profiles must move into adapters rather than leak into generic runtime services.

## 20. Definition of Done for Overlay Engine v1

1.  A user creates a project by supplying a game image, BIOS path, and emulator configuration.

2.  The external overlay can attach/launch, identify runtime context, show a timed English message, play optional host audio, and capture evidence.

3.  The internal builder produces a reproducible patched game working image plus patch manifest/package.

4.  At least one gameplay renderer/profile can show a timed English message entirely from inside the PS1 runtime after reboot/reload.

5.  External and internal scenarios use the same OverlayAction/TestScenario definitions.

6.  Unsupported movie/audio-native features are visibly gated and never misreported as completed.

7.  PCSX-Redux is supported through a dedicated adapter and the architecture permits additional emulator adapters without modifying overlay core logic.

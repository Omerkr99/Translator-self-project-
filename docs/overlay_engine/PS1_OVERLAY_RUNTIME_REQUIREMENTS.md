# PS1 Overlay & Runtime Manipulation Engine

Software/System Requirements Specification (SRS) — External Overlay + Internal Game-Resident Overlay

Project: PS1 Localization Toolkit / Twilight Syndrome reference implementation

## 1. Purpose

Define the functional, technical, integration, safety, packaging, and validation requirements for two complementary overlay systems that will become a first-class subsystem of the future PS1 Localization Toolkit.

- External Overlay: a host-side overlay and test harness synchronized with an emulator, used for diagnostics, demonstrations, live screenshots, subtitle/audio timing tests, and automated PASS/FAIL evidence collection.

- Internal Overlay: a persistent PS1-side runtime payload integrated into the game image itself. It must survive reboot/reload, execute from patched game code, and render or trigger localization content from inside the game rather than from the host desktop.

| Licensing boundary: The Toolkit must never redistribute Sony BIOS files or copyrighted game disc images. The user supplies a legally obtained BIOS path and a game disc image/path. The Toolkit may produce patches or a modified working copy, but must preserve an original untouched input. |
| --- |

## 2. Scope

The subsystem shall support a development progression from emulator-side validation to game-resident manipulation:

```text
User BIOS + Game Disc Image + Emulator
|
v
Toolkit Project Loader
|
Runtime Context Resolver
/             \
v               v
External Overlay     Internal Overlay Builder
(test/QA/HUD)        (patch + embedded payload)
\               /
\             /
v           v
Evidence / Screenshot / Runtime Validation
```

## 3. Required User Inputs

| Input | Required? | Purpose | Rules |
| --- | --- | --- | --- |
| Game disc image (BIN/CUE, ISO where valid, or supported source format) | Yes | Source for analysis, patching, asset discovery, and final modified build | Never overwrite the original. Verify hashes before and after operations. |
| PS1 BIOS file/path | Required for emulator workflows when emulator requires it | Allows accurate emulation/boot | User-supplied only; Toolkit stores path/reference, not the BIOS contents. |
| Emulator installation/path | Yes for live tests | Launch/connect/debug/capture | PCSX-Redux first-class; other emulators through adapter interface. |
| Game region/version metadata | Preferred | Select correct adapter/profiles and avoid wrong addresses | May be detected from disc metadata but should be user-reviewable. |
| Save state / memory card / save slot | Optional | Jump to known test scenarios | Must not be required for basic boot and overlay smoke tests. |
| Translation/overlay package | Optional | Text, images, subtitle timelines, audio events, debug HUD configuration | Must be versioned and validated against the target project. |

## 4. External Overlay Requirements

### 4.1 Core Functional Requirements

| ID | Requirement |
| --- | --- |
| EXT-001 | Connect to a running emulator or launch a configured emulator process. |
| EXT-002 | Receive runtime context: executable/overlay identity, gameplay/menu/movie state, dialogue state, known movie ID, known audio asset/event, and renderer profile where available. |
| EXT-003 | Render host-side text, subtitle, image, debug HUD, timers, and test status without modifying the game image. |
| EXT-004 | Play synchronized host-side audio for proof-of-timing tests; allow original audio to remain, be attenuated, or be muted only when emulator support exists. |
| EXT-005 | Capture screenshots with timestamp, runtime context, expected overlay action, actual state, and evidence metadata. |
| EXT-006 | Support scripted test packs that can run from arbitrary game locations and attempt a safe generic overlay proof. |
| EXT-007 | Record every state transition and overlay event to a machine-readable evidence log. |
| EXT-008 | Expose a visible developer HUD mode and a clean presentation/demo mode. |

### 4.2 Emulator Adapter Requirements

| ID | Requirement |
| --- | --- |
| EMU-001 | Define a stable EmulatorAdapter interface independent of PCSX-Redux. |
| EMU-002 | PCSX-Redux adapter shall support GDB remote memory read/write/breakpoint workflows and any available Web API functions used by the project. |
| EMU-003 | Adapters shall declare capabilities (memory read, memory write, breakpoints, screenshot, save-state load, pause/resume, audio control, frame counter). |
| EMU-004 | If an emulator lacks a capability, the Toolkit shall degrade gracefully and mark the related validation as unsupported rather than silently approximating it. |
| EMU-005 | The user shall be able to configure executable path, BIOS path, disc path, connection ports, launch arguments, and optional save-state path. |

## 5. Internal Game-Resident Overlay Requirements

The internal overlay is not a desktop overlay. It is a PS1-side runtime module installed into a modified copy of the game and invoked by patched game code.

| ID | Requirement |
| --- | --- |
| INT-001 | Produce a persistent patch artifact or modified game working image that contains the overlay runtime payload and hook changes. |
| INT-002 | Install a bootstrap/hook that runs automatically after boot or when the relevant executable/overlay loads. |
| INT-003 | Maintain an Overlay Runtime Context structure in RAM for mode, timers, current scene/movie, active text/image/audio actions, and health flags. |
| INT-004 | Support one or more rendering backends: gameplay native-text reuse, GPU primitive/textured-quad rendering, movie-safe post-frame composition when discovered. |
| INT-005 | Support timed ShowText/HideText actions and persistent watermark/debug actions. |
| INT-006 | Support subtitle tracks keyed by movie/event ID once a reliable movie time/frame source exists. |
| INT-007 | Support event-triggered audio actions through a host backend first and a PS1-native backend only after a validated injection/rebuild path exists. |
| INT-008 | Provide fail-open behavior: if overlay initialization fails, the game should continue whenever technically possible. |
| INT-009 | Provide a disable/safe-mode flag that can bypass the internal overlay without rebuilding the entire project. |
| INT-010 | Preserve original executable/data bytes needed for reversible patch generation and validation. |

## 6. Internal Patch/Build Requirements

| ID | Requirement |
| --- | --- |
| PAT-001 | Never modify the user's source image in place. Build in a project workspace and generate a separate output. |
| PAT-002 | Maintain a patch manifest containing original hash, target hash, changed files/sectors, hooks, allocated code/data regions, and adapter version. |
| PAT-003 | Prefer deterministic patch packages (e.g., xdelta/PPF or equivalent) where practical so copyrighted source data is not distributed. |
| PAT-004 | Validate executable size, alignment, load address, relocation assumptions, and disc-sector consequences before writing. |
| PAT-005 | Detect collisions between injected payload/code caves and existing game assets/code. |
| PAT-006 | Support rollback/rebuild from the clean source image at any time. |
| PAT-007 | Emit a build report with all modifications and evidence links. |

## 7. Runtime Context Resolver Requirements

| ID | Requirement |
| --- | --- |
| CTX-001 | Continuously resolve current executable/overlay identity. |
| CTX-002 | Resolve coarse runtime mode: boot/menu/gameplay/dialogue/movie/unknown. |
| CTX-003 | Attach adapter-specific scene/chapter/movie/audio identifiers when confidence permits. |
| CTX-004 | Every resolved claim shall include a confidence/evidence tier; unknown is a valid state. |
| CTX-005 | The overlay system must not depend on a specific save slot or scene to initialize. |
| CTX-006 | Renderer/backend selection must be driven by context and capabilities, not hardcoded global assumptions. |

## 8. Overlay Content Model

```text
OverlayAction
id
trigger
target_context
start_condition
duration/end_condition
priority
backend_preference
payload:
Text | Image | SubtitleTrack | AudioEvent | DebugHUD | ScreenshotRequest
fallback_policy
evidence_policy
```

| Content Type | External Overlay | Internal Overlay |
| --- | --- | --- |
| Text | Required | Required |
| Subtitle timeline | Required | Required after movie timing source is validated |
| Image / logo / debug panel | Required | Optional/phase 2 |
| Host audio | Required for sync proof | N/A |
| PS1-native audio injection/replacement | N/A | Future capability after audio write/rebuild path exists |
| Screenshot request | Required | Triggered externally; internal runtime can set markers |

## 9. Screenshot & Live Validation Requirements

| ID | Requirement |
| --- | --- |
| VAL-001 | A smoke test shall be runnable from an arbitrary normal gameplay location. |
| VAL-002 | The external overlay shall display an English test sentence for a configured duration and capture at least one screenshot during visibility. |
| VAL-003 | The internal overlay shall eventually display an English test sentence inside the PS1 framebuffer and capture the framebuffer result as evidence. |
| VAL-004 | Movie tests shall not be marked supported until a safe movie-time/frame synchronization source and post-frame hook are validated. |
| VAL-005 | Each validation result shall include target build hash, emulator adapter, BIOS reference/hash if user permits hashing, runtime context, screenshot path, event log, and PASS/FAIL/UNSUPPORTED. |
| VAL-006 | Tests shall distinguish external-host overlay success from internal-game overlay success. |

## 10. Non-Functional Requirements

| Category | Requirement |
| --- | --- |
| Reliability | Overlay failure must not corrupt source project data; builds are reproducible from clean inputs. |
| Performance | External HUD should not materially affect emulation; internal hooks must be bounded and avoid per-frame heavy scanning. |
| Portability | PCSX-Redux is first-class, but emulator integration must be adapter-based. |
| Observability | All actions, hooks, context transitions, errors, and build changes are logged. |
| Safety | Unknown addresses/profiles must block writes by default. Read-only observation is allowed with explicit UNKNOWN status. |
| Licensing | No BIOS, ROM/disc image, or copyrighted game data is bundled with the Toolkit. |
| Maintainability | Game-specific addresses/tables live in adapters, not core runtime code. |

## 11. Acceptance Criteria

1. External overlay can launch/connect to PCSX-Redux using user-supplied emulator, BIOS, and disc paths.

1. From an arbitrary supported gameplay location, an English overlay sentence appears for N seconds, disappears, and a screenshot/evidence bundle is produced.

1. A patched working copy can boot with the internal overlay payload present and with the overlay disabled/enabled by configuration.

1. At least one supported gameplay context shows an internally rendered English sentence visible in framebuffer capture.

1. The internal overlay survives reload/reboot of the modified game image because its payload and hooks are part of the built image, not injected only into transient RAM.

1. Movie subtitle capability remains feature-gated until its synchronization/render hook is proven; external movie subtitles may be used earlier for timing tests.

1. All builds are reversible from a clean source image and produce a patch manifest.

## 12. Source-Audit Constraints Incorporated

The current project audit reports that automated tests are overwhelmingly synthetic, that gameplay overlay readiness is materially higher than movie-overlay readiness, and that no movie-time render hook or PS1-side movie composition path is yet proven. Therefore this specification deliberately requires staged capability flags rather than pretending movie authoring is already solved.

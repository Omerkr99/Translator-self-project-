# Overlay Engine: Grounding the Spec in Real Code

`PS1_OVERLAY_RUNTIME_REQUIREMENTS.md` (SRS) and
`PS1_OVERLAY_RUNTIME_SYSTEM_DESIGN.md` (SDD) already incorporate this
project's own `docs/status/TOOLKIT_READINESS_AUDIT.md` findings
(§12/§19 of the SDD cite it near-verbatim). This document is the next
step the audit itself called for: mapping every major spec component
against what actually exists in `gcrts/` today, building only what's a
genuine gap, and reusing what's already `CONFIRMED_LIVE` rather than
re-deriving it.

## What already existed and needed no new code

| Spec component | Real module | Status |
|---|---|---|
| GDB memory read/write (EMU-002) | `gcrts.gdb_client.GdbClient` (this session, split out of `live_extract.py`) | `CONFIRMED_LIVE` — used throughout this project's audio/movie investigations |
| Screenshot capture | `gcrts.screen_capture.PcsxVramCaptureProvider` | `CONFIRMED_LIVE` |
| Executable/overlay identity (CTX-001) | `gcrts.overlay_identity.identify_overlay` | `CONFIRMED_LIVE` |
| Movie state (part of CTX-002/CTX-003) | `gcrts.movie_detection.classify_movie_state` | `CONFIRMED_LIVE` for detection; `STATIC_CODE_MATCH`/`UNKNOWN` for several chapter mappings |
| Text render hook candidate | `gcrts.renderer1_runtime.py` | `CONFIRMED_LIVE`, one executable only |
| Live text write path (INT-007's "host backend first" precedent, TextBackend candidate) | `gcrts.live_injection.py` | Implemented, never proven end-to-end through a boot (audit §5.3) |
| Save-state loading | PCSX-Redux Web API `/api/v1/state/load?slot=N`, used ad hoc throughout this project | `CONFIRMED_LIVE` |

## What was built this session (Stage 1 of the staged plan below)

The spec's own architecture (SDD §4, §14) calls for an `EmulatorAdapter`
interface, a concrete `PCSXReduxAdapter`, and a `RuntimeContextResolver`
producing a `RuntimeContext` with per-field confidence. None of these
existed as such — they're new, but built entirely as thin wrappers
around the already-`CONFIRMED_LIVE` pieces above, not new reverse
engineering:

- **`gcrts/gdb_client.py`** (new) — the generic GDB remote-protocol
  client, split out of `gcrts/live_extract.py` per the readiness
  audit's own blocker #3. Also consolidates breakpoint/continue/
  register-read methods that three separate investigation scripts had
  each re-implemented as ad hoc subclasses. Caught and fixed a real
  bug during consolidation: a naive "skip 'O' console packets" filter
  would have also skipped the literal `"OK"` acknowledgment reply
  (both start with the letter `'O'`) — fixed by checking that the
  remainder is valid, non-empty, even-length hex, which `"K"` fails.
  7 tests (`tests/test_gdb_client.py`), including one that exercises
  this exact disambiguation.
- **`gcrts/evidence.py`** (new) — the shared `Confidence` tier enum and
  `Evidence`/`Claim` dataclasses, per the readiness audit's blocker #5
  and matching the exact JSON shape sketched in that audit's own §11.
  Adopted incrementally, not a migration — existing domain enums
  (`MovieMatchConfidence`, `VerificationSource`, `PatchProfileStatus`)
  are untouched. 7 tests (`tests/test_evidence.py`).
- **`gcrts/emulator_adapter.py`** (new) — the `EmulatorAdapter`
  abstract interface and `EmulatorCapabilities`/`EmulatorCapability`
  model, matching SDD §4.2's pseudocode.
- **`gcrts/pcsx_redux_adapter.py`** (new) — the concrete
  `PCSXReduxAdapter`. Deliberately advertises only `MEMORY_READ`,
  `MEMORY_WRITE`, `BREAKPOINTS`, `SCREENSHOT`, `SAVE_STATE_LOAD`, and
  `PAUSE_RESUME` — `FRAME_COUNTER` and `AUDIO_CONTROL` are NOT claimed,
  per EMU-004, because no real mechanism for either has been proven in
  this project (the readiness audit's own finding). `load_state` takes
  a `slot: int`, not the interface pseudocode's generic path — grounded
  in what the real Web API actually does. 7 tests
  (`tests/test_pcsx_redux_adapter.py`), all against a fake GDB client
  and monkeypatched HTTP, no live emulator required.
- **`gcrts/runtime_context.py`** (new) — `RuntimeContext` and
  `RuntimeContextResolver` per SDD §9/SRS CTX-001..006. Composes
  `overlay_identity` + `movie_detection`, nothing new detected. Honest
  about its own limits, stated in the module docstring rather than
  discovered later: it can tell you which executable is resident and
  whether a movie is active (both real), but the finer MENU/GAMEPLAY
  distinction is an explicitly `INFERRED` heuristic (`PROG.EXE` →
  likely menu, `CAP*.EXE` → likely gameplay) based on one observed
  screenshot this project already has, not a systematic study; `DIALOGUE`
  resolves to `UNKNOWN` rather than a guess, per CTX-004's own "unknown
  is a valid state" principle. 6 tests (`tests/test_runtime_context.py`).

**Net this stage: 27 new tests, all passing, full suite at 1008 (was
981).** No live emulator required for any of them — they use fake/
injected transports, consistent with this project's own established
testing convention.

## What's still a genuine gap (not built this session, and why)

- **`ExternalOverlayRenderer`** (an actual transparent, always-on-top
  desktop window positioned over the emulator's own window) — real OS-
  level UI work (click-through, always-on-top, window-position
  tracking), qualitatively different from the wrapper modules above.
  Deliberately deferred to its own stage rather than attempted
  speculatively in the same pass as the foundational plumbing.
- **`LiveTestRunner` / `EvidenceBundle` writer** — depends on the
  renderer existing first (there's nothing to screenshot-and-assert
  against yet).
- **`HostAudioBridge`** — straightforward (this project's own
  `gcrts.output_audio_capture` already proves host-side audio I/O
  works), but not needed until a timing-proof scenario exists to drive
  it.
- **Everything under "Internal Overlay"** (SDD §5, §7, §14's
  `overlay/internal/`, `patching/`) — this is real new engineering
  (bootstrap/hook installation into patched game code, a patch
  manifest/rebuild pipeline) with no existing project code to wrap.
  Per the SDD's own Phase ordering (O0 before O2), and per the
  readiness audit's own priority (prove the *external* gameplay overlay
  path before attempting anything game-resident), this is correctly a
  later stage, not a Stage 1 gap.

## Staged build order (adapted from SDD §18's O0–O8, grounded in the above)

```text
Stage 1 — Foundation (DONE this session)
  gcrts/gdb_client.py, gcrts/evidence.py, gcrts/emulator_adapter.py,
  gcrts/pcsx_redux_adapter.py, gcrts/runtime_context.py.
  Exit criterion: EmulatorAdapter interface + one working concrete
  adapter + a RuntimeContext resolver, all tested without a live
  emulator. -- MET.

Stage 2 (= SDD's O0) — External overlay rendering + smoke test (DONE this session)
  Built gcrts/evidence_bundle.py, gcrts/external_overlay_renderer.py,
  gcrts/live_test_runner.py, and scripts/run_overlay_smoke_test.py.
  Exit criterion: SRS VAL-001/VAL-002 satisfied, live, once. -- MET:
  ran scripts/run_overlay_smoke_test.py against the real running
  PCSX-Redux instance. Result: PASS. Real evidence, not a synthetic
  test: RuntimeContextResolver correctly identified PROG.EXE resident
  (CONFIRMED_LIVE) and mode=MENU (INFERRED, exactly as documented); a
  real transparent Tk window displayed "TOOLKIT TEST" on screen (visible
  in evidence/stage2_smoke/host_screenshot.png -- floating over
  whatever window was in front, since the renderer doesn't yet track
  the emulator window's exact position, a known, documented Stage 2
  limitation, not a bug); a real emulator VRAM screenshot was captured
  in parallel (evidence/stage2_smoke/emulator_screenshot.png, showing
  the actual game content at that moment -- a chapter title card,
  consistent with the resolved MENU mode); a full EvidenceBundle was
  written to evidence/stage2_smoke/evidence.json. 8 new tests
  (gcrts.evidence_bundle, gcrts.live_test_runner), all against fakes,
  full suite 1016 passed -- none of the 8 required a live emulator or
  display, only the one manually-run smoke test did, matching this
  project's own established boundary between tested orchestration
  logic and manually-verified live/GUI behavior.

Stage 3 (= SDD's O1) — Shared OverlayAction model (DONE this session)
  Built gcrts/overlay_action.py (OverlayAction + all 6 payload kinds
  from SRS §8 -- only TextPayload has a real runner; the other five
  are declared but report UNSUPPORTED if run, never silently
  approximated) and gcrts/overlay_action_runner.py (the one generic
  executor). gcrts/live_test_runner.py's Stage 2 function is now a
  thin wrapper that builds an OverlayAction and delegates to it --
  existing Stage 2 tests pass unchanged, proving the refactor is
  behavior-preserving. scripts/run_overlay_smoke_test.py now
  constructs the scenario as an OverlayAction directly.
  Exit criterion: the same scenario definition produces the same
  EvidenceBundle shape as Stage 2's hand-written version. -- MET:
  re-ran the live smoke test (now data-driven) against the same
  running PCSX-Redux instance. Result: PASS, with an EvidenceBundle
  structurally identical to Stage 2's (same runtime_context resolution,
  same event_log pattern, same screenshot pair) -- saved to
  evidence/stage3_smoke/. 14 new tests (overlay_action,
  overlay_action_runner), all against fakes; full suite 1030 passed.

Stage 4 (= SDD's O2-O4) — Internal gameplay payload (STARTED this session; real, honest, partial progress)
  A first assumption here was wrong and caught before building on it:
  `renderer1_runtime.py` was assumed to be the render hook, but reading
  its actual code shows it only REPOSITIONS records the game is
  already drawing (moves existing characters' X/Y) -- it has no
  mechanism to inject NEW content. The real candidate turned out to be
  the already-existing script-buffer pipeline
  (`gcrts.live_injection.inject_units_live`, built for the text-editor
  workbench, never previously proven to render anything) -- exactly
  `docs/status/TOOLKIT_READINESS_AUDIT.md` blocker #1's own subject.

  Live experiment against save slot 4 (`CAP1.EXE`, real active
  dialogue): the dialogue auto-advances in real time once a state
  loads, fast enough that a naive read-modify-write sequence races the
  game and lands on the wrong line. Pausing the CPU immediately after
  load (`EmulatorAdapter.pause()`) removes the race entirely -- inject
  while frozen, resume, screenshot shortly after. Result, reproduced
  twice: the injected English text ("Morning Kimika how are you")
  rendered legibly through the game's own renderer and font
  (`evidence/stage4_text_injection_proof/after.png` clearly shows
  "rning Kimika ho", a substring of the injected sentence, in the
  actual classroom scene) -- the first time in this project's history
  that injected text has been confirmed to actually render in-game.
  Formalized as `scripts/prove_live_text_injection.py`.

  **What this does NOT prove, stated precisely rather than implied**:
  this is a live GDB RAM write, wiped by any save-state reload or
  reboot -- it proves only the "renders visibly" half of blocker #1,
  not "survives reboot." That half needs real disc/executable
  patching (SRS PAT-001..007), a distinct subsystem that doesn't exist
  in this project at all yet, and is real new engineering, not a
  wrapper over anything built so far.
  Exit criterion (SRS acceptance criteria 3-5, i.e. survives a real
  patched-image reboot): NOT YET MET -- this stage proved the
  rendering mechanism works at all, which was itself unproven and a
  necessary prerequisite; the patch/rebuild/persistence subsystem is
  the remaining, larger piece of Stage 4.

Stage 5+ (= SDD's O5-O8) — Movie subtitle, audio
  Explicitly gated (SRS §12, SDD §19) behind movie-time source and
  VRAM-write-path research the readiness audit rated Low readiness.
  Not attempted until those specific prerequisites are individually
  proven, matching this whole project's standing rule against
  overclaiming.
```

Stages 1, 2, and 3 are all complete as of this document, each with a
real, live, once-run proof rather than just passing tests. Stage 4 (an
internal, game-resident payload) is the next concrete piece of work,
and is real new reverse-engineering territory (a real hook point in a
patched executable), not a wrapper over existing modules like Stages
1–3 were — it should stay its own dedicated pass, not attempted as an
extension of the plumbing above.

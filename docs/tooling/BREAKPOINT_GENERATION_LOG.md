# Breakpoint Generation Log

Structured log of the emulator-state-controller's breakpoint sessions
for the Task D "renderer live proof" work. Raw JSONL entries are
written live to
`scratchpad/breakpoint_generation_log.jsonl` (session-scratch, not
committed) by `scratchpad/estate.py`; this file summarizes the
methodology and the concrete generations run this round.

## Format

Each armed breakpoint and each classified stop produces one JSON line:

```json
{"event": "arm", "generation": 12, "addr": "0x8004500c"}
{"generation": 12, "expected_pc": ["0x8004500c", "0x8007b250"], "actual_pc": "0x8007b250", "reason": "software_breakpoint", "validated": true}
```

A stop is only ever acted on when `validated: true` — i.e. `actual_pc`
is a member of the current generation's `expected_pc` set. Every
other stop (a stale notification, a focus-loss "Idle" resume echo, a
leftover trap from a previous generation) is logged with
`validated: false` and otherwise ignored by the caller.

## Generations run this round

| Generation purpose | Armed addresses | Outcome |
|---|---|---|
| Direct call-site search (`final_precise_trial.py`) | `0x8004500c`, `0x8007b294` (func exit) | 0 valid hits across three attempts (each 200-250s) — this exact breakpoint pair never fired even once despite active dialogue on screen |
| Direct call-site search, proven pairing (`final_precise_trial_v2.py`, `combined_trial2.py`, `halt_at_text_gte_v6.py`) | `0x8004500c`, `0x8007b250` | Reliably fires during **plain** (no-portrait) dialogue scenes — found real on-screen candidates repeatedly: X=103/Y=171, X=30/Y=190, X=89/Y=190, and a 500-hit run this round. Fires **zero** times during portrait-inset dialogue scenes over multiple 60-250s windows |
| Caller discovery (`discover_caller.py`) | `0x8007b250` alone (no call-site filter) | 0 hits over 60s during an active portrait-inset scene — proves the shared instruction itself is unused for that dialogue type, not just reached from an unrecorded caller |
| OT-walk fallback (`ot_full_proof.py`, `find_main_ot.py`) | `0x80076818` (DrawOTag impl) | Fires ~8 times per frame, cycling through the same 8 addresses, all near-empty (`total_prims` 0-1) across 80+ consecutive hits — this DrawOTag call is used for minor/effect layers, not the main scene+dialogue OT |

## Key methodological fix validated this round

Earlier attempts using `FUNC_EXIT` (`0x8007b294`, the GTE builder's `jr
$ra`) alongside `CALL_SITE` produced zero hits repeatedly. Switching
the second breakpoint to `STORE_INSN` (`0x8007b250`), which is
independently proven to fire reliably, immediately started producing
hits again in the same play session. The two breakpoints are
functionally close together in the same short leaf function, so this
was not expected — it is recorded here as an open, unexplained
discrepancy rather than papered over.

## Landmark validation snapshots (byte-for-byte, via `mips_jal_decoder`)

Recorded via `scratchpad/validate_profile.py`, re-run after every
process relaunch and every chapter/overlay transition this round:

```
CALL_SITE          0x8004500c: 89ec010c  OK
GTE_BUILDER_ENTRY  0x8007b224: 000080c8  OK
STORE_INSN         0x8007b250: 00000ce9  OK
FUNC_EXIT          0x8007b294: 0800e003  OK  (jr $ra, 0x03e00008)
DRAWOTAG_WRAPPER   0x800767f4: e8ffbd27  OK
DRAWOTAG_IMPL      0x80076818: d0ffbd27  OK
CALL_SITE decode -> target=0x8007b224 (OK), return=0x80045014 (OK)
```

One real drift was caught and correctly aborted-on: immediately after
a fresh chapter start (before entering actual gameplay), every one of
these addresses read back as all-zero bytes — the relevant code module
was simply not resident yet (still on a menu screen using different
code). No write was attempted; the session waited for confirmation of
being in actual gameplay, re-validated, and only then proceeded.

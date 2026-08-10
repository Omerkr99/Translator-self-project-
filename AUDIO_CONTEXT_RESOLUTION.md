# Audio Context Resolution — Why a ScriptUnit Resolves to Its XAPACK

Answers the causal question `SCRIPT_AUDIO_ASSOCIATION.md` left open:
*why* does a given `sound_or_voice_cue` script occurrence resolve to the
specific physical file it does? New module: `gcrts/audio_context.py`.
**Now fully closed**, down to a literal, static, embedded filename
string — a stronger result than the milestone that started this thread
expected to find.

## Headline result

**The "127" inline parameter every prior pass tracked was never the
real per-line selector.** The `sound_or_voice_cue` control word's own
low byte (`raw_word & 0xff`) is — live-confirmed, and directly
correcting an earlier session's own misreading of the same data
(`BACKLOG_INVESTIGATION_RESULTS.md`'s Stage C trace captured this exact
value and dismissed it as an unrelated per-frame tick counter; a live
breakpoint this session, reading the script buffer's own control word
at the same instant, confirmed it's the selector, not a tick).

**What looked like a "handler function pointer" dispatch table is
actually a data table.** The first pass through this investigation
found a 2-level table lookup terminating in what appeared to be two
different function addresses (`0x80046c20`/`0x80046c38`) and stopped
there, honestly flagging the handlers' internal logic as untraced. Full
disassembly of that address range revealed it isn't code at all — it's
a literal, embedded, null-padded string table:

```
b'XAPACK08\0\0\0\0XAPACK07\0\0\0\0XAPACK06\0\0\0\0XAPACK05\0\0\0\0
   XAPACK04\0\0\0\0XAPACK03\0\0\0\0XAPACK02\0\0\0\0XAPACK01\0\0\0\0
   XAPACK00\0\0\0\0'
```

nine 12-byte entries at `0x80046C20`–`0x80046C88`. What was previously
called `handler_function_addr` was a pointer INTO this string table, not
a code address — there is no handler function to trace into.

## Complete, confirmed causal chain

Every value below was read from live memory — not inferred from code
shape:

```
selector = sound_or_voice_cue_word & 0xff          (e.g. 25, 26, 28 -- all live-confirmed)
table1_entry = 0x8009CFDC + selector * 5           (5-byte stride records)
xapack_number = byte at table1_entry               (25->8, 26->6, 28->8 -- the XAPACK FILE NUMBER, directly)
table2_entry = 0x8009CF10 + xapack_number * 4       (4-byte stride -- pointers into the string table)
string_ptr = u32 at table2_entry
filename = null-terminated string at string_ptr    ("XAPACK08"/"XAPACK06" -- read directly)
```

`table1`'s byte is not an abstract "category" — it IS the XAPACK file
number. Confirmed for **all 9 possible values (0–8)**, not just the two
originally observed: reading every `table2[N]` pointer and the string
it points to shows `table1_value == N` names `XAPACK0N.BIN` every time,
zero exceptions.

## Validation

Live-confirmed across three real selector values now (not just two):

| Selector | table1 value | Resolved filename | Live `event.source_file` | Cross-check |
|---|---|---|---|---|
| 25 | 8 | `XAPACK08` | `DAT/XA1/XAPACK08.BIN` | MATCH |
| 26 | 6 | `XAPACK06` | `DAT/XA1/XAPACK06.BIN` | MATCH |
| 28 | 8 | `XAPACK08` | `DAT/XA1/XAPACK08.BIN` | MATCH |

The "cross-check" column is `gcrts.audio_context.cross_validate_source`
— comparing this selector-table resolution against the completely
independent, previously-built LBA-position-based resolver
(`AUDIO_CUE_RESOLUTION.md`'s `gcrts.xa_disc_index.resolve_lba_to_file`).
These two mechanisms share no code path — one reads a script control
word and walks static tables, the other reads a live playback position
and looks it up against the disc's own ISO9660 records. Their agreement
on all three live samples is real, independent corroboration that both
are correctly understood, not a tautology.

## Scope limit — honestly reported, do not overclaim

**This is not a globally valid selector→file map across arbitrary
selector values.** Reading `table1[N]` for the full range N=0–63 found
only a narrow window (roughly 24–28) gives values in the valid 0–8
range; every other tested selector produces a clearly-invalid byte (9,
20, 29, 37, 62, ...). This means the table is correct specifically for
the selector values THIS scene's script actually dispatches (three of
which, 25/26/28, are now independently live-confirmed; 24 and 27 are
structurally consistent — same valid-looking window — but not
independently observed live), not a context-free lookup valid for any
byte value. `resolve_audio_context` reflects this: a table1 value above
8 downgrades confidence to `LIVE_VERIFIED_PARTIAL` and does not attempt
to resolve a filename from it.

## What remains open

- Why this particular window of selector values (24–28ish) is the
  "live" one for this scene, and how the table is organized beyond it
  (per-scene sections? a much larger table this project only sampled a
  slice of?) — not investigated, genuinely open.
- Whether `set_mode_ce4`/`set_flag_d10` (the other control codes
  appearing in both compared `ScriptUnit`s) participate in selecting
  *which* table window is active, versus this being fixed regardless of
  preceding commands — the two compared units showed no differing
  low-byte values on any control code except the sound cue itself, but
  this doesn't rule out an EARLIER (outside either unit) setup command
  establishing scene-level state.
- How the resolved filename string is actually turned into a file
  handle/read operation downstream (a standard PSY-Q `open()`-style call
  is the obvious guess, but not traced).

## Runtime integration

`RuntimeVisualProvider.last_audio_context`, `RuntimeSnapshot.active_audio`'s
`"audio_context"` field (present even when `UNKNOWN`) plus a new
`"source_cross_validated"` boolean (`True`/`False`/`None`) at the event
level. The Visual Inspector's audio panel shows the selector, resolved
filename, and a `MATCH`/`MISMATCH` line against the independent
position-based resolver.

## Tests

16 tests in `tests/test_audio_context.py` (13 for the core resolver,
including a regression covering all 9 valid `table1` values and the
out-of-range scope-limit behavior, plus 3 for `cross_validate_source`).
Full suite: 452 → **478 passed**.

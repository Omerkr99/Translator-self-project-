# MIPS Patch Plan — Alternative Text Engine, Phase 6

**Design only. No bytes have been written to the emulator. No MIPS code
exists in this repository.** Per the master prompt's Phase 6 instruction
("Review the design before writing bytes") and Phase 7's separate,
not-yet-reached scope ("Install through GDB in a live emulator session").
Also per Phase 5's conclusion (`MEMORY_MAP_FINDINGS.md`): no permanent
memory region has been confirmed safe for the dispatcher/descriptor code
this plan calls for, so this remains a paper design, not something ready
to install.

## A live-verification finding that changed this plan mid-design

The original plan (based on static analysis from the earlier blast-radius
investigation) was to hook the single call site that invokes the wrap
function — reported by Ghidra as `jal 0x8004a370` at `0x80048e50`, inside
`FUN_80048e18`. Before writing this plan down as fact, that address was
re-checked against the currently-running live session (a single safe
memory read, no breakpoint):

```
live bytes at 0x80048e48: 0x0c011366  ->  jal 0x80044d98
```

**Not a match.** The live JAL is at `0x80048e48` (not `0x80048e50`), and
targets `0x80044d98` (not `0x8004a370`) — a completely different
function. Whatever scene/overlay is currently loaded does not have the
same code at that address as the static `CAP0.EXE` file analyzed earlier.
This is exactly the overlay-variance risk `MEMORY_MAP_FINDINGS.md` (13.3)
already flagged as real, now confirmed to affect code addresses too, not
just data.

**However**, the wrap function's own address checked out exactly as
expected:

```
live bytes at 0x8004a370: sw $s0, 0x18($sp)     -- matches static analysis
live bytes at 0x8004a374: addu $s0, $a0, $zero  -- matches static analysis
```

**Conclusion driving this plan**: `FUN_8004a370`'s own address is stable
across whatever's currently loaded; its caller's address is not. The hook
should target the wrap FUNCTION's entry, not any specific call site — this
also means one hook location works regardless of which of the 5
narrative call sites (or which overlay) reached it, without needing to
re-derive or re-verify a caller address per context.

*Caveat, stated plainly: this is two data points (the static file and one
live session), not a survey across all ~10 overlay executables found in
Phase 5. Re-verifying this specific address against each overlay before
relying on it is still open work, not assumed to hold universally.*

## The hook site, precisely (fully live-verified, not just from the decompile)

Reading a wider window around the function entry live turned up the full
prologue, including one detail the earlier decompile transcription didn't
carry: the actual frame-allocation instruction sits one word before the
address previously labeled "the function start":

```
0x8004a36c: addiu $sp, $sp, -0x20     ; allocate a 32-byte frame (previous function's RA/NOP ends right before this)
0x8004a370: sw    $s0, 0x18($sp)      ; save caller's $s0
0x8004a374: addu  $s0, $a0, $zero     ; s0 = param_1  (equivalently: move $s0, $a0)
0x8004a378: sw    $ra, 0x1c($sp)      ; save return address
0x8004a37c: lui   $v0, 0x8003         ; -- function body begins here --
```

### A real bug this design review caught before it could become a live crash

The naive choice — patch the FIRST instruction (`0x8004a370`) with a jump
to the dispatcher — is wrong. A MIPS jump's delay slot is always the
NEXT instruction in memory, which would be `0x8004a374`
(`addu $s0, $a0, $zero`). That instruction would still execute (delay
slots always do), but the instruction it was supposed to follow —
`sw $s0, 0x18($sp)`, saving the CALLER's original `$s0` — would never
run, because it's the one being overwritten. The result: the caller's
`$s0` is silently lost, and whatever the epilogue later restores from
that stack slot would be wrong data, corrupting an unrelated register
somewhere else in the call stack. This is exactly the class of bug the
master prompt's section 14 asks this phase to catch ("record register
liveness... determine delay-slot behavior") — found here on paper,
before any byte was ever written.

**Corrected hook site: `0x8004a374`** (the SECOND instruction, `addu $s0,
$a0, $zero`), not the first. Reasoning: `sw $s0, 0x18($sp)` (instruction
1) executes normally, unmodified, before the hook ever fires. The jump's
delay slot then lands on instruction 3 (`sw $ra, 0x1c($sp)`) — which has
no data dependency on the overwritten `addu`, so it's safe to let it run
as-is in the delay slot. The dispatcher's own first action must replicate
the displaced instruction's effect (`$s0 = $a0`) before doing anything
else, since nothing else will.

## Preserved instructions and where they go

| Original instruction | What happens to it |
|---|---|
| `sw $s0, 0x18($sp)` (0x8004a370) | Untouched — executes normally before the hook fires. |
| `addu $s0, $a0, $zero` (0x8004a374) | OVERWRITTEN with `j <dispatcher>`. Its effect (`$s0 = $a0`) must be the dispatcher's own first instruction. |
| `sw $ra, 0x1c($sp)` (0x8004a378) | Untouched, but now serves double duty as the delay slot for the injected jump — executes automatically, unmodified. |

## Register / stack plan

By the time the dispatcher gains control (i.e. after the injected jump's
delay slot has run):
- `$s0` still holds the CALLER's original value (saved to `$sp+0x18` by
  the untouched first instruction) — the dispatcher has not yet
  clobbered it, but also hasn't set it to `param_1` yet (that's the
  displaced instruction it must replay first).
- `$ra` has ALREADY been saved to `$sp+0x1c` (by the delay slot) — safe
  to use `$ra` for a nested call from the dispatcher, since the caller's
  original value is already preserved on the stack, not lost.
- `$a0` still holds `param_1` (the layout struct pointer), untouched.
- The 32-byte frame (`$sp` to `$sp+0x1c` used so far by the two saves) has
  `0x20 - 0x1c - 4 = 0` bytes of headroom left in THIS specific frame —
  i.e. none. Any dispatcher-local scratch space needs its OWN stack frame
  (a further `addiu $sp,$sp,-N` on entry, deallocated before returning
  control), not slots borrowed from this one.

**Open, not yet verified**: exactly which OTHER registers (`$a1`-`$a3`,
`$t0`-`$t9`) are live/dead at this exact point (i.e. safe for the
dispatcher to clobber without saving) has not been traced through the
full decompile. The dispatcher's own prologue should conservatively save
anything it uses via its own stack frame rather than assume any register
beyond the three above is free — this project's own strict rule ("do not
claim ... without evidence") applies here as much as to memory regions.

## Return path (falling through to original behavior)

If the dispatcher determines no `CUSTOM_ENGINE` descriptor applies (the
common case today, since no unit is actually consumed this way yet), it
must:
1. Execute `addu $s0, $a0, $zero` (the displaced instruction).
2. Jump to `0x8004a37c` (`lui $v0, 0x8003` — the original function body's
   real first instruction), resuming normal execution exactly where it
   would have continued had the hook never fired.

This is the master prompt's section 15 fallback requirement made
concrete for this specific hook: `ORIGINAL`/`HOST_FITTED` behavior is
preserved byte-for-byte from this point on, every time the dispatcher
declines to act.

## Dispatcher pseudocode (section 15)

```
dispatcher:
    s0 = a0                          ; replay the displaced instruction

    descriptor_ptr = find_descriptor_for(a0)   ; ** mechanism TBD, see below **
    if descriptor_ptr == 0:
        goto fallback                ; no CUSTOM_ENGINE plan for this unit

    if not validate_descriptor(descriptor_ptr):
        goto fallback                ; magic/version/bounds check failed -- never trust blindly

    render_from_descriptor(descriptor_ptr)     ; see parser pseudocode below
    return                                     ; jr ra (ra already valid -- saved by the delay slot)

fallback:
    j 0x8004a37c                     ; resume original flow, delay slot: (original instruction 3 already ran)
```

**Open, not yet designed**: `find_descriptor_for(a0)` — how the dispatcher
locates a CUSTOM_ENGINE descriptor for the specific text currently being
rendered. Nothing in this project's live-RAM layout currently associates
a script unit with a descriptor buffer; this needs its own small protocol
(e.g. a known fixed address holding "descriptor present + pointer",
written by the same injection tooling that already writes the script
buffer). Left undesigned here rather than guessed at, since it depends on
choosing where the descriptor itself lives — which depends on the still-
unresolved memory question from Phase 5.

## Descriptor parser pseudocode (matches `gcrts.layout_descriptor` exactly — see `CUSTOM_LAYOUT_DESCRIPTOR.md`)

```
validate_descriptor(ptr):
    if read32(ptr) != "CLD1":              return false
    version      = read16(ptr+4)
    if version != 1:                        return false
    flags        = read16(ptr+6)
    line_count   = read16(ptr+8)
    if line_count > 64:                     return false     ; MAX_LINES
    page_transition = read8(ptr+16)
    reserved        = read8(ptr+17)
    if reserved != 0:                        return false
    if page_transition > 2:                 return false
    ; (bounds re-checked against actual buffer length are a decoder-side
    ;  concern in the reference Python implementation; a MIPS parser
    ;  reading directly from live RAM has no separate "buffer length" to
    ;  check against and must instead trust the region it was told is
    ;  valid by whatever wrote it there -- an open trust boundary this
    ;  design doesn't resolve, flagged rather than hand-waved.)
    return true

render_from_descriptor(ptr):
    line_count = read16(ptr+8)
    lines_base = ptr + 18                  ; HEADER_SIZE
    chars_base = lines_base + line_count * 10   ; LINE_RECORD_SIZE

    for i in 0..line_count-1:
        rec = lines_base + i*10
        start_char_index = read16(rec+0)
        char_count       = read16(rec+2)
        x                = read16(rec+4)   ; ALREADY alignment-resolved -- see CUSTOM_LAYOUT_DESCRIPTOR.md
        y                = read16(rec+6)
        ; alignment (rec+8) is informational only -- not needed to render correctly

        cursor_x = x
        for j in 0..char_count-1:
            code = read16(chars_base + (start_char_index+j)*2)
            ; reuse the EXISTING, already-proven glyph pipeline --
            ; do NOT duplicate glyph lookup/decompression/blit (section 11):
            width = glyph_table_lookup(code)          ; same table this project reverse-engineered (DAT_80093b38 / atlas.table_entry)
            draw_glyph(code, cursor_x, y)             ; call the game's OWN existing glyph-blit routine
            cursor_x = cursor_x + width
```

## What this phase deliberately did not do

- No bytes written anywhere, live or otherwise.
- No code-cave search redone (Phase 5's conclusion stands: none confirmed
  safe yet) — this plan describes WHERE the hook and dispatcher would go
  in terms of behavior, not a concrete address for the dispatcher's own
  code, since that's exactly the unresolved Phase 5 question.
- `find_descriptor_for()`'s actual mechanism, full register liveness
  beyond the three registers confirmed above, and per-overlay
  verification of the `0x8004a370` hook address are all explicitly left
  open rather than guessed at.

## Phase 7 — installed live, verified working

Everything above this section was pure design. This section records what
actually happened once it was installed.

**Memory**: a wider re-scan (not just the two Phase 5 regions) turned up
a much larger candidate: `0x801a0000`, a 30,720-byte zero run. Confirmed
safe with the same marker-write methodology across TWO independent
rounds of real gameplay (the operator explicitly confirmed real play
happened between each write and each check, not an instant re-read) —
see `MEMORY_MAP_FINDINGS.md`'s Phase 7 update. Per the master prompt's
13.5, this is a development-only, this-run-only finding, not a claim
about permanent safety or safety in any other overlay.

**What was installed** — an intentionally minimal "always fallback" stub,
a pure mechanism test with zero functional change to the game, exactly
the fallback path this document's dispatcher pseudocode already
described:

```
0x801a0000: addu $s0, $a0, $zero   ; 00808021 -- the displaced instruction, replayed
0x801a0004: j    0x8004a37c        ; 080128df -- resume original flow
0x801a0008: nop                    ; 00000000 -- delay slot for the j above
```

**The hook patch** — the single 4-byte change to live control flow:
```
0x8004a374: j 0x801a0000   ; 08068000 -- was 00808021 (addu $s0,$a0,$zero)
```
Original bytes (`21808000` in little-endian hex) saved to a standalone
restore script before this was written, per this project's established
practice of never taking an action without a reversal path ready first.

**Verification**: emulator responsiveness checked immediately before and
after the write (both clean). The operator then advanced dialogue —
triggering the hooked function on a real, new scene (a nighttime bridge,
with a speaker-name-tagged Japanese line) — and confirmed it rendered
with zero visible difference from unpatched behavior, at a normal 59
FPS. This confirms, for the first time with live evidence rather than
just careful reasoning: the hook site is correct, the delay-slot handling
is correct, the displaced instruction's replay is correct, and the resume
address is correct. Every register-liveness assumption in this
document's design section held up against real execution.

**What this does NOT yet prove**: this is the FALLBACK path only —
`descriptor_ptr == 0` is effectively hard-coded (the stub never looks for
one), so none of the dispatcher's real branch, the descriptor parser, or
`find_descriptor_for()` (still explicitly undesigned above) have been
exercised live. The next real step is extending this same stub to
actually check for and parse a `gcrts.layout_descriptor`-format buffer,
not declaring victory on the strength of the fallback path alone.

## Phase 7 correction — the "fallback-only" verification was a false positive

The paragraph above claims Phase 7's fallback-only stub was "verified
working" because the game rendered fine after installing it. **That
claim needs to be retracted.** It was never actually established that the
hook site was executed at all — "zero visible regression" is equally
consistent with the hook never firing, which is trivially true if
`FUN_8004a370`'s prologue simply isn't reached. This distinction was
missed at the time and only surfaced later, while debugging why an
extended, branch-on-real-descriptor stub's diagnostic marker refused to
ever be set.

**What actually happened, in order:**

1. An extended stub (check `descriptor_ptr`, validate the `CLD1` magic,
   set a diagnostic marker on success) was designed, hand-verified
   instruction-by-instruction, and installed at the same `0x8004a374`
   hook site proven in Phase 7. Both a regression test (`pointer=0`) and
   a real-descriptor test (`pointer` set to a valid encoded descriptor)
   left the marker at 0 — the real test was expected to set it to 1 and
   didn't.
2. A live diagnostic read confirmed the hook bytes, the stub bytes, the
   pointer slot, and the descriptor's magic bytes were ALL intact and
   correct in memory — ruling out data corruption.
3. A canary write inserted as the stub's very first, unconditional
   action (no dependency on anything, no branch before it) also never
   fired. This ruled out a logic bug in the branch/magic-check code —
   if the stub were ever entered at all, this write could not be
   skipped.
4. A second canary tap was added at `FUN_8004a370`'s TRUE entry point
   (`0x8004a36c`, not just the `+8` hook offset), requiring displacing
   and correctly replaying its first two instructions (`addiu
   $sp,$sp,-0x20` then `sw $s0,0x18($sp)`) to avoid a delay-slot hazard
   identical in kind to the one already documented above (the physically
   next instruction after a jump always executes as its delay slot,
   regardless of the jump's intended target). This canary ALSO never
   fired, across further real gameplay — proving the entire function,
   not just this one instruction slot, was not being called at all
   during that stretch of play, despite dialogue continuing to render
   normally on screen throughout.
5. Cross-checking `gcrts.layout_validation`'s module docstring confirmed
   `FUN_8004a370` genuinely is the correct per-character wrap-decision
   function — independently reverse-engineered via a live GDB breakpoint
   in earlier work, with detailed structural confirmation (the exact
   wrap formula, live-captured struct values, real per-glyph advance
   widths). `gcrts.render_paths` further confirmed dialogue only has one
   render path in this project, ruling out "a different textbox
   implementation is used for speaker-tagged lines" as an explanation.
   So the function identification itself was not the problem.
6. The operator then loaded a save state (`quicksave`/`quickload`) to get
   a controlled, reproducible test. This immediately revealed the real
   cause of the broader puzzle (though not, on its own, of step 4's
   specific mystery): **the code at this address range had shifted**.
   Re-reading a wide window showed the surrounding function boundary
   moved — `jr $ra; nop` (a function return) now sits at
   `0x8004a368`/`0x8004a36c`, and a new function starts cleanly at
   `0x8004a370` with a LARGER frame (`addiu $sp,$sp,-0x30` vs. `-0x20`)
   and THREE saved registers (`$s0`,`$s1`,`$s4`) instead of one — the
   same general shape, shifted 4 bytes, with more locals. The scratch
   region at `0x801a0000`, previously confirmed safe across two rounds
   of gameplay, was now full of unrelated live data (199/256 non-zero
   bytes in the first 256-byte sample) — also no longer free.
   **This is the overlay/layout-variance risk `MEMORY_MAP_FINDINGS.md`
   already flagged as real but untested — now directly observed, not
   theoretical.** It fully explains why a save-state load wipes a patch,
   but does NOT by itself explain why the function went uncalled during
   the earlier, stable (non-reloaded) play session in steps 1–4 — that
   narrower mystery remains formally unresolved, though it's now
   moot for shipping purposes (see below).
7. A fresh candidate region was found and re-verified safe via the same
   marker-write methodology, across two independent rounds of gameplay
   (the second done with the emulator left running continuously through
   a scene in auto-play, at the operator's suggestion, to allow rapid
   re-checks): `0x801ac370`, a 76,944-byte zero run.
8. A canary-only stub was rebuilt for the shifted addresses (entry now
   `0x8004a370`; hook point `0x8004a378`, two instructions in, same
   delay-slot-safety reasoning as the original design — its natural
   delay-slot successor `sw $s1,0x1c($sp)` has no dependency on anything
   not yet set) and installed fresh. Polled once every 3 seconds while
   the scene ran live, **the canary fired within about 3–6 seconds of
   install** (`cafebabe` observed at the expected address) — the first
   direct, positive proof this session that the hook mechanism actually
   executes, rather than sitting dormant. The game continued rendering
   normally throughout.
9. The full branch-on-descriptor stub was then rebuilt for the same
   shifted addresses, with one instruction added: a `nop` inserted
   immediately after each `lw` and before the register it loaded is
   used (closing off a suspected MIPS R3000 load-delay-slot hazard —
   never confirmed as the actual cause of steps 1–4's failure, but cheap
   to close off given the uncertainty). Tested exactly as originally
   planned: `pointer=0` regression (marker stayed 0, correct) followed
   by `pointer` set to a real, valid `CLD1`-magic descriptor (**marker
   became 1**, correct) — both while the scene continued running live,
   with zero visible regression confirmed by the operator both times.

**Conclusion**: the branch-on-real-descriptor mechanism (null check,
magic validation, diagnostic-marker success path) is now proven working
with live evidence, for this specific loaded state. The Phase 7 "always
fallback" milestone is retroactively unverified — it was never actually
exercised — but this fresh, more careful test supersedes it and covers
strictly more ground (both the fallback AND success branches, not just
fallback). Two things remain explicitly open, per this project's own
"don't guess, don't overclaim" discipline: (a) why the function went
uncalled during the specific earlier play session in steps 1–4, distinct
from the overlay-shift explanation that covers the quickload case, and
(b) whether this hook survives across the OTHER ~9 overlay executables
without per-overlay re-verification — still not attempted, exactly as
`MEMORY_MAP_FINDINGS.md` already cautioned.

## Phase 8 — per-executable patch profiles (framework only)

The master prompt asks this phase to "expand to all five narrative call
sites or the proven common caller. Add executable-specific profiles."
Phase 7's own history — a "working" patch that was later shown to have
never fired, followed by direct proof that a save-state reload shifts
addresses and invalidates a previously-safe scratch region — makes the
"executable-specific profiles" half of that instruction non-negotiable:
nothing in this project may assume one executable's verified addresses
apply to another, or even to the same executable after a reload.

**What this phase built**: `gcrts/mips_patch_profile.py`, a data model
and registry, not a live patch of anything new:

- `PatchProfile` — one record per executable, holding hook/resume/stub
  addresses, the displaced instruction, a code fingerprint for
  identifying which executable is actually loaded, and a `status` that
  distinguishes UNVERIFIED / ADDRESSES_HYPOTHESIZED /
  HOOK_INSTALLED_UNCONFIRMED / LIVE_CONFIRMED_THIS_SESSION /
  STALE_NEEDS_REVERIFICATION — collapsing this to one boolean is exactly
  the mistake that produced the false-positive Phase 7 claim.
- `new_unverified_registry()` — one honest UNVERIFIED entry per known
  executable name (`CAP0-4.EXE`, `CAPX.EXE`, `MYOKO.EXE`, `MRIKA.EXE`,
  `MNINO.EXE`, `MPRO.EXE` — the set this project has actually observed
  strings for in README.md/MEMORY_MAP_FINDINGS.md, explicitly not
  claimed complete).
- `record_live_confirmation()` — the only way to mark a profile
  confirmed, requiring the caller to already have observed a canary
  fire, not just a byte-readback match.
- `hypothesize_from_verified()` — builds an explicitly-untested guess
  for a new executable by shifting a confirmed profile's addresses (the
  exact kind of shift observed this session, function boundary +4
  bytes), while deliberately NOT carrying over the scratch-region size
  or fingerprint bytes, since those are exactly what this session
  observed NOT to survive a reload unchanged.
- `identify_loaded_executable()` — matches a live memory read against
  every profile's fingerprint, so a future workflow can detect which
  executable is actually loaded before installing anything, rather than
  assuming.
- `mark_stale()` — downgrades a confirmed profile back to
  needs-reverification (call after any reload/quickload).
- `save_registry()` / `load_registry()` — JSON persistence, so a
  confirmed profile survives between sessions instead of being
  rediscovered from scratch or, worse, trusted from stale memory.

**What was actually confirmed live this session**, saved to
`mips_patch_profiles.json` at the repo root: one profile, deliberately
NOT labeled as any specific `CAP*.EXE`/character executable, because no
identification step was ever run to determine which one was loaded —
only the shifted address layout was observed after the quickload. It is
recorded under the honest name
`"UNIDENTIFIED_SESSION_2026-07-27"` with `hook_addr=0x8004a378`,
`resume_addr=0x8004a380`, and the fingerprint bytes read from
`0x8004a370` (`d0ffbd27`, i.e. `addiu $sp,$sp,-0x30`) — enough for
`identify_loaded_executable()` to recognize this same loaded state again
if it recurs, but not enough to claim it's any named executable.

**What Phase 8 explicitly did NOT do**, because it requires the operator
to actually reach each scenario in-game — something this module can't
do on its own:

- No live verification was attempted for any of the five narrative
  executables by name (`MYOKO.EXE`, `MRIKA.EXE`, `MNINO.EXE`, `MPRO.EXE`,
  or whichever fifth one exists — this project has not independently
  confirmed there are exactly five or which five).
- No live verification was attempted for `CAP0-4.EXE`/`CAPX.EXE`.
- `identify_loaded_executable()` has not been run against any of these
  in a live session — it's tested only against fakes in
  `tests/test_mips_patch_profile.py`.
- The "proven common caller" alternative the master prompt offers (patch
  a single shared function all five narrative paths call through,
  instead of five separate per-executable patches) was not investigated
  — doing so would require comparing the call graph across at least two
  different narrative executables live, which hasn't happened.

### Phase 8 negative finding — the "original" address layout has never fired

A second narrative chapter (a different character, confirmed by the
operator to be a genuinely new scenario, not a reload of the same save)
was reached in-game and tested with the exact same methodology: found
and two-round-verified a fresh scratch region (`0x8019f588`, 33,400
zero bytes), confirmed the wrap-function prologue, installed a
canary-only stub at the hook site, polled while dialogue was confirmed
visibly on screen (a speaker-tagged line, screenshot captured) and
actively advancing.

**The canary never fired — 15 checks over 45 seconds, hook and stub
bytes both re-verified intact throughout.** Original bytes restored
immediately after.

What makes this worth a dedicated section rather than a one-line note:
the code at this hook site matched the **original, unshifted** layout
exactly — `addiu $sp,$sp,-0x20` at `0x8004a36c`, a single `$s0` save,
hook at `0x8004a374` — byte-for-byte the same pattern the very first
static analysis of `CAP0.EXE` found, and the same pattern this
project's Phase 6/7 design was originally built against. That pattern
has now failed to fire **twice**: once earlier this session (before the
mid-session quickload, steps 1-4 of the Phase 7 correction above) and
again here, on a different character's chapter. Meanwhile the
**shifted** layout (`addiu $sp,$sp,-0x30` at `0x8004a370`, three saved
registers, hook at `0x8004a378`) has fired within 3-6 seconds **both**
times it was tried.

This is a 0-for-2 (original layout) vs. 2-for-2 (shifted layout) split,
not noise. The most likely reading:
whatever function lives at the "original" layout's address is not
actually the one driving real-time character rendering for CURRENT
dialogue, despite matching static analysis and despite an EARLIER,
separate investigation (`gcrts.layout_validation`'s breakpoint-based
wrap-formula research) having apparently confirmed a call through this
same conceptual function. The two are not necessarily in conflict --
that breakpoint research may well have been run against an executable
whose code happened to have the "shifted" shape, not this "original"
one, without that distinction having been tracked at the time. Chasing
this further would require a fresh breakpoint-based investigation (the
only technique that gives a definitive call/no-call answer rather than
an inference from a fixed hook address), which carries the same freeze
risk `MEMORY_MAP_FINDINGS.md`'s 13.2 already documented and was
explicitly declined for this session. Recorded honestly as
`CONFIRMED_NOT_FIRING` in `mips_patch_profiles.json` under
`UNIDENTIFIED_SECOND_CHARACTER_2026-07-27` rather than silently retried
or hand-waved.

**Concrete next step, for whenever each scenario is reachable in-game**:
load that character's chapter, run `identify_loaded_executable()` against
the saved registry (confirming it's genuinely a new, unrecognized
executable rather than a repeat), re-run this session's exact
methodology (find + two-round-verify a scratch region, locate the
wrap-function prologue, install a canary-only stub, confirm it fires
live), then call `record_live_confirmation()` and `save_registry()` to
add that executable to `mips_patch_profiles.json` — never by editing the
JSON by hand or by copying another executable's addresses without
re-running the live canary check.

### Phase 8 follow-up — narration-vs-dialogue investigated, superseded by a broader pattern

A follow-up investigation tried to narrow down *why* the original layout
never fires, hypothesizing it might be specific to narration vs.
character dialogue (motivated by `gcrts.layout_validation`'s own
docstring noting its historical breakpoint verification was done on
"the one narration textbox instance"). Four more live tests followed,
across both layouts:

1. **Shifted layout, pure narration** (chapter 0, reloaded fresh, canary
   reset, played through an entire narration segment before checking):
   canary stayed at 0. First negative result for the shifted layout,
   which had fired in every prior test.
2. **Shifted layout, real-time poll across the narration→dialogue
   transition** (fresh reload, continuous 3-second polling starting
   right at a narration screen): fired at the 15-second mark -- but the
   operator confirmed the screen still showed narration at that moment,
   not dialogue. This directly contradicts a clean "narration never
   fires it" reading from test 1.
3. **Original layout, a third dialogue-only test** (chapter 1 loaded
   fresh from a quicksave at the actual start of the chapter, continuous
   3-second polling for a full 120 seconds = 40 checks): confirmed
   dialogue on screen throughout, hook/stub bytes re-verified intact at
   the end. Canary never fired.
4. An in-game stall occurred mid-investigation (emulator auto-paused,
   apparently by a PCSX-Redux focus-loss setting, not by anything this
   project's tooling did) followed by a period where the game "wasn't
   progressing" even after unpausing. **Diagnosed by restoring the
   original hook bytes and confirming the stall persisted with NO patch
   installed at all** -- ruling this project's memory writes out as the
   cause before continuing. Resolved by the operator directly (window
   focus / input, not a GDB-side issue).

**Conclusion**: the narration-vs-dialogue hypothesis does not hold up
cleanly (test 2 fired mid-narration; test 1's narration did not) --
text-type alone doesn't predict whether the hook fires. The pattern that
DOES hold up across every test this session: **the shifted layout has
fired in every test it was given (now 4-for-4, including mid-narration),
while the original layout has fired in none (now 0-for-3, all
confirmed-dialogue -- no narration was ever encountered in an
original-layout session to complete that missing cell)**. The most
likely explanation remains that these are two genuinely different
compiled functions sharing a similar prologue shape rather than the same
function behaving differently by content type -- something a future
breakpoint-based investigation could confirm definitively, but which
this session declined to pursue given the known freeze risk. Both
negative-finding notes and this reasoning are persisted in
`mips_patch_profiles.json`.

**Practical implication for this tool going forward, independent of
resolving the "why"**: matching a function's address and prologue SHAPE
to what static analysis found in one executable is demonstrably not
sufficient evidence that the same shape is the live render path in
another compiled executable. Only a live canary-fire test is -- exactly
the discipline `PatchProfile`'s status ladder (`UNVERIFIED` /
`ADDRESSES_HYPOTHESIZED` / `LIVE_CONFIRMED_THIS_SESSION` /
`CONFIRMED_NOT_FIRING`) was built to enforce. Any future per-executable
onboarding for this project's tooling should assume nothing from a
prologue match alone.

## Position-override design research (live custom renderer, continued)

With renewed explicit confirmation to proceed on the deferred live
position-override work, the confirmed-working (shifted-layout)
`FUN_8004a370` was disassembled live via `capstone` (a full 1024-byte,
256-instruction window from its entry) rather than guessed at from the
partial decompile snippets quoted in `gcrts.layout_validation`'s
docstring. This is real, confirmed structure, not static analysis of a
different executable — read directly from the same live session already
proven to fire.

**Position record layout, now fully confirmed**: 14-byte (`0xe`) records
in an array based at `$s0` (== `param_1`, the function's first
argument), indexed by the global `DAT_800a4cd8` (current record index).
The multiply-by-14 the docstring's decompile snippet described is not a
single `mult` instruction but a compiler-optimized shift/subtract/shift
sequence appearing at every record-address computation:
```
sll $v0, $vN, 3      ; v0 = vN * 8
subu $v0, $v0, $vN    ; v0 = vN*8 - vN = vN*7
sll $v0, $v0, 1        ; v0 = vN*7*2 = vN*14
addu $v0, $v0, $s0      ; v0 = records_base + index*14
```
Within a record: **X at offset +8, Y at offset +0xA** (both `ushort`).

**Multiple, not one, X/Y write sites exist** — this is the finding that
changes the shape of the design:

| Address | What it writes | When |
|---|---|---|
| `0x8004a3f8` / `0x8004a420` | X / Y, from `param_2` fields + `DAT_800a4d13` | `DAT_800a4d11==1` early-return path (`STALE_POSITION_MEANINGS`, already documented) |
| `0x8004a45c` / `0x8004a4d8` | X / Y, copied from a REFERENCE record at index `DAT_800a4cee` | first character of a fresh textbox (`DAT_800a4cd8==0`) |
| `0x8004a4b0` / `0x8004a4d8`(shared) | X / Y, copied from the PREVIOUS record (`current-1`) | not the first character |
| **`0x8004a50c`** | **X = old_X + `DAT_80094d20` (spacing) + char_width (`param_2+6` byte)** | **the normal per-character cursor-advance — the common case** |
| `0x8004a5bc` / `0x8004a5ec` | X / Y, wrap-reset formula (`bVar1+sVar4+param_2[0]` / `old_Y+line_advance`) | line doesn't fit (`sltu` budget check fails at `0x8004a568`/`0x8004a62c`) |

All paths converge at a **common exit, `0x8004a658`**, which does
bookkeeping (resets `DAT_800a4d10`/`DAT_800a4d11` to a sentinel `0xff`,
resets `DAT_800a4d13` to 0, stores the current glyph's cached
width into `DAT_80094d20` for the next call's spacing) before the
epilogue restores saved registers and returns. `$s0` (the records base)
is still valid at this point — it isn't restored until `0x8004a698`,
after the hook site.

**Why this matters for the override design**: overriding just the
per-character write at `0x8004a50c` (the naive first idea) would leave
every OTHER path — first-character seeding, wrap-reset, the
`DAT_800a4d11` stale-position path, and the two forced-wrap/centering
variants gated by `DAT_800a4d10` — still writing the GAME's own computed
X/Y. That would produce visibly inconsistent results: correct positions
mid-line, wrong ones at every line start or wrap. Patching five-plus
internal write sites individually, each with its own register-liveness
and delay-slot review, is a large increase in surface area and risk
compared to anything installed so far this session.

**The lower-risk alternative, and the one Phase 6's original pseudocode
already pointed at**: hook the single **common exit** (`0x8004a658`)
instead of any individual write site. At that point, `DAT_800a4cd8`
(current index) and `$s0` (records base) are both still valid,
regardless of which internal path just ran — so a dispatcher could
simply overwrite `records_base + index*14 + 8` / `+0xA` with values from
the active `CUSTOM_ENGINE` descriptor, unconditionally, right before the
epilogue. This needs no per-path patching and can't miss a code path,
because every path already funnels through this one point.

**What this does NOT yet resolve, and is the concrete next task**:
Phase 6's `render_from_descriptor` pseudocode always intended to call
the glyph-blit routine (`FUN_8004aa08`) directly with editor-chosen
X/Y — bypassing this position-records mechanism entirely — rather than
overriding values inside `FUN_8004a370`. Which approach is actually
correct depends on a question not yet answered: **does `FUN_8004aa08`
read its draw position FROM the position-records array itself, or does
it accept X/Y as direct arguments from its caller?** If the former,
overriding the record (as designed above) is necessary and sufficient.
If the latter, overriding the record here is unnecessary work — the
real interception point would be wherever `FUN_8004aa08` is called with
the position it's about to draw at, a completely different function
this session has not yet disassembled. This must be answered with the
same live-disassembly rigor as above before writing a single byte of
either design — not assumed.

Also unresolved: how a specific call to `FUN_8004a370` (one per
character, driven by the game's own `DAT_800a4cd8` counter) would be
correlated with a position inside an editor's `CUSTOM_ENGINE` descriptor
(which is organized by line, not by a flat character-advance counter).
`param_2` (the per-textbox layout struct pointer, `$s1`) is a plausible
candidate key for "which textbox is this" — stable per textbox,
distinct across textboxes — but this has not been tested.

### `FUN_8004aa08`'s actual caller found — the design assumption above does not hold

A live scan of the entire code segment (`0x80045000`-`0x800a4000`) for
the exact JAL instruction encoding targeting `0x8004aa08` found exactly
**one** caller: `0x8004a9cc`, inside a previously-unexamined function
starting at `0x8004a8c0` (`FUN_8004a8c0`). Disassembling it in full
(clean, capstone-verified, no garbled instructions) shows it is NOT a
simple pass-through of the wrap function's cursor position. Its first
parameter is the same records-base pointer (`$s0 = param_1`, same
convention as `FUN_8004a370`), but what it actually computes and writes
to record offsets **+0 and +2** (the fields `FUN_8004aa08` reads and
right-shifts by 2 before blitting) is:

```
DAT_800a4cdc = (DAT_800a4cdc + 1) mod 256          ; a free-running 0-255 counter, unrelated to DAT_800a4cd8
ratio        = 64 / (param_3[8] >> 2)               ; param_3 = a THIRD parameter, a different struct than FUN_8004a370's param_2
quotient, remainder = divmod(DAT_800a4cdc, ratio)
record[DAT_800a4cd8].offset0 = (remainder * param_3[8]) & 0xffff      ; written BEFORE calling FUN_8004aa08
record[DAT_800a4cd8].offset2 = (quotient  * param_3[0xa]) & 0xffff     ; written BEFORE calling FUN_8004aa08 (delay slot)
record[DAT_800a4cd8].offset4 = FUN_8004aa08(...)'s return value        ; written AFTER the call
```

This is **not** "copy the cursor-advance X/Y computed by `FUN_8004a370`
into the blit-time fields" — it's a free-running frame/animation counter
(`DAT_800a4cdc`, incrementing every call regardless of character or
line, wrapping at 256) combined with a ratio derived from a *different*
struct's fields, feeding two divisions. This has the shape of a
per-character reveal, shimmer, or blink-timing effect (something that
changes smoothly over successive calls independent of which character
or line is being drawn), not a coordinate transform. Confirmed as a
genuinely different, not-yet-understood computation — not assumed.

**What this means for the position-override design**: the working
hypothesis in the section above (hook `FUN_8004a370`'s common exit,
override `record[idx].{+8,+0xA}`, and expect that to reach the blitter)
is now known to be **insufficient**. `FUN_8004aa08` reads `{+0,+2}`, and
whatever writes those fields is `FUN_8004a8c0`, a third function with
its own separate inputs and its own separate per-frame counter,
apparently unrelated to the wrap function's cursor math. Overriding
`FUN_8004a370`'s output would not, on the evidence gathered so far,
change where anything actually gets drawn. The real interception point
— if this analysis holds up — is inside or around `FUN_8004a8c0`
(or its own caller, not yet identified), not `FUN_8004a370`.

**Given the scope this has grown to** — three functions now
disassembled live (`FUN_8004a370`, `FUN_8004aa08`, `FUN_8004a8c0`),
a wrong initial hypothesis caught only by continuing to verify rather
than stopping at the first plausible-looking answer, and at least one
more open question (who calls `FUN_8004a8c0`, and what `param_3`
actually represents) before a safe hook point can even be proposed —
this is exactly the kind of expanding, uncertain territory the original
"defer the position-override work" decision was meant to guard against.
No bytes have been written. This section stops at analysis, and the
next move (keep disassembling toward a concrete design, or stop here and
treat this as a documented foundation for a future, separately-scoped
session) is a decision point, not something to keep pushing through
alone.

### Breakpoint-based inspection attempted, found non-functional this session

With explicit confirmation to accept the known freeze risk, a
single-shot breakpoint methodology was built (`Z0` set once, block for
the first natural stop-reply, read state, `z0` remove, single `c`
resume — deliberately NOT the repeated set/continue/re-trap loop that
caused the documented freeze pattern in earlier sessions) to directly
observe `DAT_800a4cdc`, the position record's raw bytes, and `$s0`
(records-array base) at the exact moment `FUN_8004a8c0` returns from
calling `FUN_8004aa08`.

Mid-investigation, the operator's computer reset, taking down the
emulator entirely. It was relaunched (`pcsx-redux.exe`, found at
`C:\PCSXRedux\drop\binaries\vsprojects\x64\ReleaseWithClangCL\`, with
the game ISO at `C:\PCSXRedux\game\game.cue`, using the project's own
`pcsx.json` config which already has `emulator.Debug.GdbServer=true` on
port 3333) and the operator navigated back into a scene matching the
confirmed-working shifted layout.

**The breakpoint never fired — five consecutive attempts, all timing
out** — including after ruling out timing/coordination as the cause
(confirmed via plain polling that `DAT_800a4cdc`/`DAT_800a4cd8` DID
change between attempts, meaning rendering was genuinely happening) and
including a sanity check at `FUN_8004a370`'s own entry address, which
canary tests earlier this session PROVED fires constantly — that
breakpoint also never hit. This rules out both "wrong address" and
"nothing was rendering" as explanations. The most likely cause: this
freshly-relaunched emulator instance's GDB stub either needs an
initialization/handshake sequence this project's minimal hand-rolled
client doesn't send, or its software-breakpoint (`Z0`) implementation
has a real limitation not previously exercised (`m`/`M` memory
read/write, used constantly all session, are a completely different
code path from instruction breakpoints in most GDB stub
implementations). Not diagnosed further, since doing so would mean
guessing at the emulator's own internals rather than this project's
code — out of scope here.

**Net effect on the position-override investigation**: it is blocked on
tooling, not on understanding. The remaining open question --
does `DAT_800a4cdc`-based formula in `FUN_8004a8c0` track independently
from `FUN_8004a370`'s cursor math, or do they end up correlated in
practice -- needs either (a) working breakpoints (a different emulator
session, or a corrected GDB client handshake), or (b) a register-read
capability that doesn't depend on breakpoints (not currently available
-- `g` without a preceding stop would sample whatever function happens
to be running at a random instant, not reliably this one).

### Breakpoints fixed, and the open question resolved with real data

Two bugs in this project's hand-rolled GDB client (`gdb_proper_client.py`
in the scratchpad, not part of `gcrts/`) were the actual cause of every
prior breakpoint timeout, not an emulator-side limitation:

1. **Missing protocol acknowledgment.** `qSupported`'s reply advertises
   `QStartNoAckMode+`, meaning ack-mode is ON by default and every reply
   needs a `+` sent back — this client never sent one.
2. **The target starts halted on a fresh connection and needs an
   explicit `c` to run at all.** The earlier assumption ("the first hit
   arrives on its own, no continue needed") only holds for a connection
   that was already free-running from earlier in that same session, not
   a brand-new connection after a relaunch. Diagnosed by testing a
   breakpoint at `FUN_8004a370`'s own entry — an address canary tests
   already proved fires constantly — which ALSO timed out until an
   explicit `c` was sent immediately after `Z0`, at which point it hit
   instantly.
3. A separate, unrelated bug then surfaced once breakpoints started
   working: `_next_packet()` returns `bytes`, but both `read_memory()`
   and the register-parsing helper assumed a `str` reply and called
   `.startswith("E")` / `bytes.fromhex()` directly on it, raising
   `TypeError`. Fixed by decoding to `str` first in both places.

With all three fixed, a clean single-shot breakpoint at `0x8004a9d4`
(the point right after `FUN_8004a8c0` returns from calling
`FUN_8004aa08`, both record writes and the blit call already done)
captured two real hits:

| | index (`DAT_800a4cd8`) | counter (`DAT_800a4cdc`) | cursor X,Y (+8,+0xA) | blit-raw X,Y (+0,+2) | blit X,Y after `>>2` |
|---|---|---|---|---|---|
| hit 1 | 0 | 0 | 10, 152 | 0, 0 | 0, 0 |
| hit 2 | 26 | 43 | 64, 190 | 176, 32 | **44, 8** |

`$s0` (records base) was `0x800a3dd0` both times — matching the
"layout struct at `0x800a3dd0`" address already on record from an
earlier, separate investigation (`MEMORY_MAP_FINDINGS.md` line 31),
confirming this is the same structure, now with its role in this
mechanism newly connected.

**This directly answers the open question**: at hit 2, cursor-X=64 vs.
blit-X=44, cursor-Y=190 vs. blit-Y=8 — clearly NOT the same quantity,
confirming (not just hypothesizing) that `FUN_8004a8c0`'s
`DAT_800a4cdc`-driven formula is a genuinely separate mechanism from the
wrap function's cursor accumulation, not a copy or simple transform of
it. The magnitude of hit 2's blit-Y (8) is far too small to be an
accumulated multi-line cursor position, and doesn't move in lockstep
with the character index (26) or the cursor's own Y (190) — consistent
with the earlier hypothesis that this is some kind of secondary visual
effect (a per-character animation, shimmer, or similar) layered
independently of the main cursor-driven glyph placement, rather than
the primary text-position mechanism itself. This was NOT fully
determined (what exactly it visually produces is still open), but the
core structural question — "are these the same position, computed
twice" — is now settled: they are not.

**Implication for the position-override design**: this reinforces
that overriding `FUN_8004a370`'s cursor fields (`+8`/`+0xA`) alone,
as this section's earlier hypothesis proposed, would likely leave
whatever `FUN_8004a8c0`/`FUN_8004aa08` actually draws unaffected — since
that path computes its own values independently, not by reading `+8`/
`+0xA`. Confirming exactly what needs to be overridden (and where) to
control final on-screen position remains open, but is now known to
require engaging with `FUN_8004a8c0`'s own mechanism specifically, not
just `FUN_8004a370`'s. Still no bytes written; still no live override
installed. The debugging-tooling fix above (ack handling + explicit
continue after `Z0`) is itself a durable, reusable improvement to
`gdb_proper_client.py` for any future breakpoint-based work on this
project.

### Eight consecutive samples reveal `FUN_8004a8c0`'s fields are a tile/cache index, not a screen position

With breakpoints now reliable, a bounded (max-8-hit, not unbounded)
multi-hit sample was taken across the first 8 characters of a fresh
line:

| hit | idx | `DAT_800a4cdc` | cursor (X,Y) | blit raw (X,Y) | blit shifted (X,Y) |
|---|---|---|---|---|---|
| 1 | 0 | 0 | 10, 152 | 0, 0 | 0, 0 |
| 2 | 1 | 1 | 26, 152 | 16, 0 | 4, 0 |
| 3 | 2 | 2 | 38, 152 | 32, 0 | 8, 0 |
| 4 | 3 | 3 | 52, 152 | 48, 0 | 12, 0 |
| 5 | 4 | 4 | 64, 152 | 64, 0 | 16, 0 |
| 6 | 5 | 5 | 78, 152 | 80, 0 | 20, 0 |
| 7 | 6 | 6 | 92, 152 | 96, 0 | 24, 0 |
| 8 | 7 | 7 | 106, 152 | 112, 0 | 28, 0 |

Cursor-X advances by the actual proportional glyph width each time
(16, 12, 14, 12, 14, 14, 12 — real, varying font metrics, consistent
with everything already confirmed about this font). Blit-X-raw
advances by an **exact, fixed 16** every single hit, completely
independent of glyph width, and blit-Y stays at exactly 0 throughout.

Solving `FUN_8004a8c0`'s formula (`ratio = 64/(param_3[8]>>2)`,
`quotient,remainder = divmod(DAT_800a4cdc, ratio)`, `blit_X_raw =
remainder*param_3[8]`, `blit_Y_raw = quotient*param_3[0xa]`) against
this data: blit-X-raw = counter×16 exactly, for every counter value
0-7 — only consistent with `param_3[8] = 16` and therefore `ratio =
64/4 = 16`. Since the counter never reached 16 in this sample, the
quotient (row) stayed 0 throughout, matching the observed constant
blit-Y. (This also explains why the earlier single sample at
`idx=26, cdc=43` showed `blit_X_raw=176=11×16` — `43 mod 16 = 11` —
and `blit_Y_raw=32=2×16` if `param_3[0xa]=16` too, i.e. `43 div 16 =
2`: fully consistent with the same 16-wide grid, just further into
its second row.)

**This is the signature of a fixed-stride grid/tile index — 16 cells
per row — not a screen pixel position.** A real cursor position, tied
to proportional glyph widths, would never advance by an identical fixed
amount every character regardless of which character it is. This
strongly suggests `FUN_8004a8c0`/`FUN_8004aa08` populate some kind of
rolling cache, staging buffer, or texture-atlas cell (16 cells per row,
wrapping into additional rows as `DAT_800a4cdc` grows past 16) —
independent of where the glyph is ultimately composited to the visible
screen, which is controlled by the wrap function's own proportional
cursor tracking (`+8`/`+0xA`) instead.

**What this means for the position-override design, updated again**:
neither hypothesis investigated so far (override `FUN_8004a370`'s
cursor fields, or override `FUN_8004a8c0`'s blit-position fields) is
confirmed as the correct interception point for controlling final
on-screen position. The wrap function's cursor is real and
proportional but per this session's evidence is read by neither
confirmed blit path; `FUN_8004a8c0`'s fields are real and observed but
now look like an unrelated grid-indexed cache, not a screen position.
**Where the FINAL, actual on-screen pixel position comes from is still
not identified** — it may be a fourth, not-yet-disassembled function
that reads the wrap cursor directly, or reads from whatever cache
`FUN_8004a8c0` populates, or something else entirely. This is now a
clearly-scoped, concrete open question for a future session, not
something to keep guessing at inline.

### Empirical confirmation: neither field is the primary on-screen text position

Rather than keep reasoning from static disassembly alone, both
hypotheses above were tested directly: pause at a live breakpoint hit,
overwrite one field with an obviously different value, resume, and
screenshot to see the actual visual effect.

**Test 1 — overwrite the wrap function's cursor-X (`+8`)**: broke at
`0x8004a9d4` (after the character had already been fully processed,
including the blit call), changed `+8` from 10 to 220, resumed, and
screenshotted immediately. **No visible change** in the rendered dots.
Consistent with the disassembly finding that `FUN_8004aa08` never
reads `+8`/`+0xA` at all.

**Test 2 — overwrite `FUN_8004a8c0`'s blit-position field (`+0`),
first attempt**: broke at the same `0x8004a9d4` return point and
changed `+0` from 144 to 800. **Also no visible change.** This result
initially looked like it ruled out `+0` too — but a methodology bug
was caught before drawing that conclusion: `0x8004a9d4` is the
*return* point from `FUN_8004aa08` — by the time execution reaches
it, the blit call has already read `+0`/`+2` and already drawn to
VRAM. Modifying the record afterward can't retroactively change a
frame that's already been rendered; it only affects whichever future
call next reuses that same record slot. Both "no visible change"
results from this return-point breakpoint are therefore inconclusive
by construction, not genuine negatives.

**Test 2, corrected — same field, broken BEFORE it's consumed**: moved
the breakpoint to `FUN_8004aa08`'s own entry (`0x8004aa08`), before it
reads `+0`/`+2` at all (at entry, the records-base pointer is in `$a0`,
not `$s0` — `$s0` isn't set up until partway through this function's
own prologue for a different purpose, a decompression scratch buffer).
Changed `+0` from 192 to 800, resumed, screenshotted immediately.

**This time there WAS a visible effect**: the resulting frame shows a
lone, disconnected `・` (a stray dot) floating separately to the left
of the actual dialogue line ("サト：ユカリちゃん、あたし感じるよ　この
校舎"), clearly displaced from where it should logically connect to
the rest of the text. Critically, **the main dialogue text itself
rendered completely normally** — correctly positioned, no visible
shift or corruption in the actual sentence.

**Conclusion, now backed by direct empirical evidence, not just
formula-solving**: `+0`/`+2` does feed into something that gets drawn
to the screen (the stray-dot artifact proves that), but it is
demonstrably NOT the mechanism controlling the position of the live,
currently-typing dialogue text — that stayed perfectly normal
throughout. This matches the "rolling cache / stale leftover slot"
hypothesis from the disassembly analysis: corrupting one cell of a
16-wide grid buffer produced a corrupted leftover artifact, not a
shifted live character. **Both of the two candidate fields tested this
session (`FUN_8004a370`'s cursor, `FUN_8004a8c0`'s blit-position) are
now empirically ruled out as the primary live text-position mechanism.**
The real mechanism remains unidentified. Emulator state was left
unmodified after each test (no breakpoint or hook remains installed;
the corrupted record cell self-heals as normal rendering continues
and reuses that slot).

### Third candidate chain fully traced and resolved — also not the screen-position source

A follow-up round fully disassembled the remaining unexplored chain
(`FUN_8004aae8` → `FUN_8007ad74`/`FUN_8007acdc` → an indirect call
through a function-pointer table at `0x8009d448`) that this document's
prior section left as "the leading candidate." Full details, field-by-
field, are in `DIALOGUE_GPU_PACKET_MAP.md` and
`INDIRECT_RENDER_TARGETS.md`; summary:

- The indirect call resolves (function pointer read live, target
  disassembled live) to a standard PS1 BIOS A0-table trampoline
  calling function `0x3f`.
- Its first argument is a fixed address (`0x80046e90`) which, read
  live, contains the literal string `"tpage: (%d,%d,%d,%d)\n   clut:
  (%d,%d)\n  clip (%3d,%3d)-(...)"`. **This is a debug-mode printf
  logging GPU primitive attributes, not a primitive-submission
  mechanism** — confirmed via live string content, not inferred from
  the bit-packing shape alone.
- `FUN_8004aae8`, `FUN_8007ad74`, and `FUN_8007acdc` are all
  attribute-packing/logging helpers (tpage/clut/clip bitfield packing),
  not writers of a plain screen-destination X/Y.
- The double-buffering alternative this raised (is the earlier-ruled-
  out `FUN_8004a8c0` cache write actually a currently-invisible back
  buffer?) was tested via 5 rapid screenshots (~180ms apart, ~800ms
  total) after the same live modification — no delayed appearance of a
  moved glyph occurred. Not supported; the original ruling stands with
  more confidence, now that it's been actively tested against this
  alternative.

**Net result: all three mechanisms investigated across this session's
position-tracing work are now ruled out or reclassified as
cache/logging/attribute-only.** The real screen-destination writer for
dialogue text remains unidentified. See `EXPERIMENT_PLAN.md` for the
precise next step (search for other callers of the GPU-upload
primitive `0x800786b8`, and a direct scan for any consumer of the wrap
function's `+8`/`+0xA` cursor fields outside `FUN_8004a370` itself).

## Phase 9 — editor-controlled live layout (software-only groundwork; live custom renderer explicitly deferred)

The master prompt's Phase 9: "Connect: editor layout plan → binary
descriptor → live injection → custom renderer. Validate left alignment
before centering." This section covers the first three links, built as
software this session. The fourth link — a live MIPS custom renderer
that actually draws glyphs at editor-specified positions instead of the
game's own computed ones — is the position-override work explicitly
deferred earlier in this project (see the Phase 7 AskUserQuestion
decision: "Safe version now" over the position-override branch). That
choice stands; nothing below installs it, and it should not be installed
without a renewed, separate confirmation given the same reasoning that
applied then still applies now: it requires a multiply to compute a
position-record address and touches globals whose exact bit-width isn't
independently confirmed.

**What's newly resolved this phase**: Phase 6's design left
`find_descriptor_for(a0)` explicitly undesigned — "nothing in this
project's live-RAM layout currently associates a script unit with a
descriptor buffer." This session's own live debugging work
(re-diagnosing why the Phase 7 stub never fired) ended up building and
proving exactly this protocol as a side effect: a fixed `pointer_slot`
address the dispatcher `lw`s, holding either 0 (no descriptor, fall
through) or a live RAM address of a validated `CLD1` buffer. That is now
formalized as `PatchProfile.pointer_slot_addr` /
`.descriptor_region_addr` (`gcrts/mips_patch_profile.py`), and the
Python-side write path — encode the unit's `EditorLayoutPlan`, write the
descriptor bytes, then the pointer, each verified by readback before the
next step — is `gcrts/layout_descriptor_injection.py`
(`build_descriptor_injection_plan` + `inject_descriptor_live`). It
refuses to build a plan against anything but a
`LIVE_CONFIRMED_THIS_SESSION` profile, and refuses to inject a
descriptor too large for the profile's reserved region — both fail
closed with a clear error rather than silently writing something wrong.

**What this explicitly does NOT do**: cause any pixel to render
differently. The only live-confirmed consumer of `pointer_slot_addr` is
Phase 8's diagnostic-branch stub, which validates the magic and sets a
marker — it does not call `render_from_descriptor`, does not call
`draw_glyph`, and does not exist for any executable beyond this
session's one unidentified profile. Running
`inject_descriptor_live()` against a live session right now would
stage real position data in memory, but nothing currently reads that
data to draw anything — matching the "stop before installing anything
that touches real position data" scope for this phase.

**Open design question surfaced while reviewing this, not resolved**:
Phase 6's `render_from_descriptor` pseudocode (above) assumes the
dispatcher can loop over every line/character of a textbox and call
`draw_glyph` per character, then return, from a SINGLE hook fired once.
But the confirmed hook point (`FUN_8004a370`-equivalent) is itself
called ONCE PER CHARACTER by the master render loop
(`FUN_800481b0` — see `gcrts.layout_validation`'s module docstring) as
part of the game's own normal per-character wrap/advance cycle. A real
custom renderer therefore has two structurally different options,
neither designed in detail yet:

1. **Per-character interception**: keep the hook firing once per
   character (as it does today), and on the FIRST character of a
   CUSTOM_ENGINE textbox, have the dispatcher draw the ENTIRE descriptor
   in one shot and then force the game's own loop to skip forward past
   every character it would otherwise have drawn one-by-one — requiring
   the dispatcher to know how many characters to skip and how the
   game's own loop counter/cursor state needs to look afterward so nothing
   downstream (page transition, "wait for input" detection) breaks.
2. **Full loop takeover**: replace the call from `FUN_800481b0` to
   `FUN_8004a370` entirely for the duration of one CUSTOM_ENGINE textbox,
   handing control back only once the descriptor's last character is
   drawn — requiring a hook at `FUN_800481b0` itself (a different,
   not-yet-analyzed function) rather than its callee, with its own
   register-liveness and delay-slot review from scratch (Phase 6's
   register/stack plan was built specifically for `FUN_8004a370`'s own
   prologue and does not transfer).

Neither option's register-liveness, delay-slot safety, or interaction
with `DAT_800a4d10`-`DAT_800a4d13` (the forced-wrap/stale-position state
`gcrts.control_position_risk` already documents) has been worked through.
This is flagged as the concrete next design task for whenever live
custom-rendering work is explicitly re-authorized — not something to
guess at now.

**Also not yet confirmed**: `FUN_8004aa08`'s (the glyph-blit routine)
calling convention at the MIPS register level. `gcrts.glyph_atlas` and
`gcrts.layout_software_preview` reverse-engineered its DATA format and
output behavior thoroughly enough to build a correct software preview,
but that was done by reading and simulating its logic in Python, not by
confirming which registers a live MIPS caller must load before jumping
into it. A real dispatcher's `draw_glyph(code, cursor_x, y)` pseudocode
step depends on knowing this exactly, and doesn't yet.

**Per the master prompt's own instruction for this phase** ("Validate
left alignment before centering"): whenever live custom-rendering work
resumes, the recommended order is a single LEFT-aligned, single-line
descriptor first (no centering math, no multi-line cursor bookkeeping),
confirmed rendering correctly, before attempting CENTER_BLOCK or
multi-line layouts.

## Position-override design research, continued (later session) — full mode dispatch mapped

A later session round picked this thread back up against a
DIFFERENT loaded profile (this session's own independently-mapped
chapter-1 overlay, not the profiles named above — the game's code
layout drifted mid-scene multiple times, without any quickload; see
`MASTER_RENDER_MODE_MAP.md`'s "Layout drift log"). Rather than re-derive
piecemeal, this round fully mapped the per-character render-mode
dispatch (modes 0/1/2/3) and live-tested every reachable candidate
X/Y-write site. Full detail in the two new dedicated documents,
`MASTER_RENDER_MODE_MAP.md` and `VISIBLE_DIALOGUE_COMPOSITION_PATH.md`;
headline results:

- Confirmed, in a second independently-compiled overlay, that the same
  "off-screen glyph-cache upload" pattern this document already
  documented (`FUN_8004aa08`'s destination rect) recurs almost exactly
  (`X=328,Y=320,W=4,H=16` vs. the original's `X=320+,Y=256,W=4,H=16`) —
  real cross-validation that this is a genuine, stable engine
  convention, not a one-overlay coincidence.
- **Mode 2 was found to naturally perform the same "walk records array,
  collect valid Y values" operation this document's Phase 9 section
  associated with mode 3** — and, unlike mode 3, fires reliably during
  ordinary play. Real, non-empty Y-values (152, 171) were captured for
  the first time this session, with `152` independently matching this
  project's own long-established real on-screen Y constant from the
  very first live captures (`TEXT_POSITION_TRACE_LOG.md`'s event set A).
- A new candidate write site was found OUTSIDE the mode-handler
  entirely, in the master render loop's own post-call processing
  (`0x8003AAAC`) — writing the same records-array `+8`/`+0xA` fields
  with real coordinate-shaped values. Its live-modification test could
  not be completed: the write recomputes more frequently than a
  modify-then-screenshot round trip can outpace. This is recorded as
  genuinely inconclusive, not ruled out — an important distinction this
  document's own Phase 7 history already established the hard way
  (`"game renders fine" is not evidence a hook fired`; the same
  discipline applies here to `"no visible effect" is not evidence
  a write is irrelevant if the modification couldn't be confirmed
  to persist`).
- A reusable, unit-tested JAL/return-address decoder
  (`gcrts.mips_jal_decoder`, see `MIPS_JAL_DECODER.md`) was built this
  round specifically because hand-computing this arithmetic caused real
  delays at least three times across this project's live investigation
  work. Future sessions extending this document's own hook/dispatcher
  design should use it rather than re-deriving JAL targets by hand.

**Position-override design status, updated**: still not installed, per
the same "Safe version now" decision this document has maintained
throughout. The concrete next task is narrower than before: trace
candidate D's source struct (`0x800A38D4`) backward to find what writes
it, and test THAT for a live position-override effect before designing
any hook around it.

# Movie/`.STR` Runtime Detection

Resolves this project's single largest blocked thread
(`CURRENT_SYSTEM_STATUS.md`'s own "Recommended next milestone"):
identifying when the game is playing a `.STR` movie, and which one --
without tracing internal DMA arguments.

## Why the earlier plan was wrong

The original plan (`BACKLOG_INVESTIGATION_RESULTS.md`) was to retarget
a live DMA-channel-kickoff trace (`dma_channel_start`, `PROG.EXE`'s own
copy at `0x80052760`) at whichever overlay is actually resident during
movie playback. Five hypotheses along that line were ruled out or
blocked across earlier sessions. But this session's own audio
investigation had already found the deeper problem with that whole
direction: address-level internal tracing repeatedly hits overlay-
identity walls (`CAP0.EXE`/`CAP1.EXE` turned out to be resident during
regular gameplay, not the assumed `PROG.EXE`), and the method that
actually resolved audio identification abandoned internal tracing
entirely in favor of observable evidence.

The same fix applies here directly, and it's simpler than retargeting
anything: `gcrts.overlay_identity` already catalogs a **separate**
movie-player executable family (`MPRO`/`MOVER`/`MKUBI`/`MNINO`/`MOP`/
`MRIKA`/`MYOKO.EXE`, `0x80100000-0x8012c800`) — architecturally
distinct from the `CAP*.EXE` chapter/scene family the DMA-retarget plan
would have looked at. Since this family's entire purpose is playing
movies, its mere residency is itself the movie-playback signal. No new
tracing was needed — the tool to answer this question already existed.

## Live confirmation

Ran the real opening movie (`OP.STR`) while polling
`identify_overlay()` at 0.5s intervals (`scripts/live_overlay_watch.py`,
plain memory reads, no exec breakpoints): `MOP.EXE` was detected
resident within 0.15s of starting the poll and stayed resident for the
full ~90s observed (with one brief single-poll "UNKNOWN" blip at
t=51.7s, most likely a scene-internal transition within the movie
itself, not the movie ending — `OP.STR` at 47.7MB is comfortably longer
than 90 seconds of playback). Confirmed by direct observation that the
opening movie was genuinely playing on screen the whole time.

## The filename correlation, and a correction caught before it shipped

The real `DAT/MOVIE/` files (LBA/size read directly from the disc,
`gcrts.movie_detection.MOVIE_CATALOG`) line up with the movie-player
executable names by prefix for 5 of 7 (`MKUBI`<->`KUBI.STR`,
`MNINO`<->`NINO.STR`, `MOP`<->`OP.STR`, `MPRO`<->`PRO.STR`,
`MYOKO`<->`YOKO.STR`). A first version of `gcrts.movie_detection`
mapped all five individually — but `gcrts.overlay_identity.
KNOWN_OVERLAYS` only lists literal standalone names for executables
with a *unique* code signature. `MPRO.EXE`/`MYOKO.EXE` share one
signature and `MKUBI.EXE`/`MNINO.EXE`/`MRIKA.EXE` share another
(near-identical generic harnesses), so `identify_overlay()` can only
ever return the combined `"X.EXE (or Y.EXE)"` string for those five —
never the individual standalone name the first version mapped. That
would have been dead code, silently never matching anything for 4 of
the 5 "confirmed" pairings. Caught by a test asserting the mapping
against the real `KNOWN_OVERLAYS` values before it was committed, not
discovered live.

Only `MOP.EXE` and `MOVER.EXE` are independently reachable as
standalone `identify_overlay()` results. Honest current state:

| Overlay result | Candidate file(s) | Confidence |
|---|---|---|
| `MOP.EXE` | `OP.STR` | `CONFIRMED_LIVE` |
| `MOVER.EXE` | `GAI.STR` or `KIKU.STR` | `AMBIGUOUS` |
| `"MPRO.EXE (or MYOKO.EXE)"` | `PRO.STR` or `YOKO.STR` | `AMBIGUOUS` |
| `"MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)"` | `KUBI.STR` or `NINO.STR` | `AMBIGUOUS` |

`gcrts.movie_detection.classify_movie_state()` reports the real
candidate set honestly in every case, never guessing down to one file
when the overlay signature can't distinguish them.

## Wired into `RuntimeSnapshot`

`RuntimeSnapshot.active_movie` is no longer an always-empty placeholder
field. `RuntimeVisualProvider.scan()` calls `identify_overlay()` against
the same RAM buffer it already fetched (no second live read, same
pattern as `_cdrom_driver_map`), caches the result as
`last_movie_detection`, and `capture_runtime_snapshot` populates
`active_movie` from it — present only while a movie-player overlay is
actually resident, `None` otherwise.

## Tests

10 new tests (`gcrts.movie_detection`), all pure/synthetic — including
a regression test that would have caught the dead-code mapping bug
above (`test_every_confirmed_or_named_file_exists_in_catalog`, plus the
individual `MKUBI.EXE`-style standalone-name tests that now correctly
fail if reintroduced). Full suite: 952 passed, no regressions.

## Disambiguating the ambiguous groups: console text, not RAM-diffing

The planned next step was to capture the movie-player overlay's own
RAM during two different movies and diff them to find the
distinguishing data. That turned out to be unnecessary. Save slot 6
was reloaded (via the same `/api/v1/state/load` call already used
throughout this project) with a GDB breakpoint pre-armed at the movie
overlay's real entry PC (`0x80102654`, read directly off the console
trace below) so the capture would land exactly on the movie's load,
not sometime after. It fired within a fraction of a second of the
reload -- this session's earlier 90s/240s/240s polling-based
`live_overlay_watch.py` windows had all missed the movie for exactly
that reason: it loads and reverts fast enough that a 0.5s poll
interval can straddle it entirely.

The PS1 kernel prints its own literal debug line every time it loads
an executable -- forwarded live over GDB's asynchronous `O` console
packets, the same mechanism this project's GDB tooling already skips
around when reading replies (`docs/audio/...` -- see
`_read_reply_skip_console`). For a regular load it's
`Load Exec : \NAME.EXE;1`; for this movie-player family specifically
it's `MovieLoad Exec : \NAME.EXE;1`. The captured text for slot 6's
movie:

```
MovieLoad Exec : \MPRO.EXE;1
CD_init:addr=800a3108
pc = 80102654
t_addr = 80100000
t_size = 0002c800
EXEC!
```

This names `MPRO.EXE` directly and unambiguously -- at the very same
moment `identify_overlay()` itself could only report the combined
`"MPRO.EXE (or MYOKO.EXE)"` string for the resident overlay's code
signature. `gcrts.movie_detection.parse_exec_load_name()` extracts the
literal filename from this text, and
`resolve_ambiguous_group_via_console_text()` cross-checks it against
`AMBIGUOUS_GROUP_MEMBERS`/`EXE_NAME_TO_MOVIE_FILE` to confirm which
specific file within an ambiguous group is loaded, never guessing when
the parsed name doesn't actually belong to the group being asked about
or has no name-correlated file at all (e.g. `MRIKA.EXE`).

This doesn't remove the underlying architectural ambiguity --
`identify_overlay()`'s RAM-signature match still can't distinguish
`MPRO.EXE` from `MYOKO.EXE` on its own, and `RuntimeSnapshot.
active_movie` (populated purely from that signature match during
normal play) still reports the combined name. What it adds is a real,
tested, reusable secondary confirmation path for any live capture
session that's also watching the GDB console stream: this session's
own use of it confirms `MPRO.EXE` (not `MYOKO.EXE`) triggers from save
slot 6, and per the filename-correlation hypothesis that points to
`PRO.STR` (not `YOKO.STR`) -- one confidence step above the group's
prior undifferentiated `AMBIGUOUS` state, though not yet
`CONFIRMED_LIVE`, since the movie reverted before any `.STR` sector
data was actually observed streaming.

## Finding all trigger points efficiently: static disassembly

Live-triggering every remaining movie by luck doesn't scale --  a full
sweep of all 10 existing save slots against the two remaining
ambiguous groups found zero instant triggers, and letting each one run
freely for 30s after load didn't catch anything either (unlike save
slot 6, which happened to be saved right at the trigger boundary).
Rather than requiring a human to stumble into each trigger point live,
this session went looking for the selection logic itself, directly in
the disc's own executables.

Every `CAP*.EXE`/`CAPX.EXE` chapter executable embeds an **identical**
10-entry table of movie-player executable names (`gcrts.iso9660` read
each file directly off the real disc), plus its own copy of a generic
"load movie by index" dispatcher function -- found by locating each
file's own copy of the `"MovieLoad Exec : %s"` format string (the
exact debug text captured live earlier), then walking backward to that
function's own entry point (its `addiu $sp, $sp, -N` prologue). The
table itself holds three names that don't exist as real files on disc
at all (`MCAVE.EXE`, `MSB.EXE`, `MGOKI.EXE`) -- presumably cut
content, left in the shared table but never shipped as files.

Scanning each chapter file's own code for `jal` call sites targeting
its own dispatcher, with an immediate constant loaded into the second
argument in the branch-delay slot, found real, hardcoded per-chapter
choices:

| Chapter | movie_id | Resolves to |
|---|---|---|
| `CAP0.EXE` | 8 | `MPRO.EXE` |
| `CAP1.EXE` | 1 (two call sites) | `MKUBI.EXE` |
| `CAP4.EXE` | 4 | `MRIKA.EXE` |
| `CAP4.EXE` | 2 | `MNINO.EXE` |

`CAP0.EXE`'s result is now `CONFIRMED_LIVE`, upgraded from a static
match: a GDB breakpoint planted directly at `CAP0.EXE`'s own dispatcher
entry (`0x8006E5E4`) fired during a real save-slot-6 load, with `$a1`
read live as exactly `8`, and the live pointer-table bytes matching the
disc image byte-for-byte. This also **disproved an earlier wrong
hypothesis** from this same investigation -- that `CAP0.EXE` "hands
off" to `CAPX.EXE` to perform the actual load, based on an earlier
console-log capture that happened to show `CAPX.EXE` resident near the
movie trigger. A breakpoint planted at `CAPX.EXE`'s own dispatcher
entry during the identical scenario never fired at all, even while the
movie fully played -- proving `CAPX.EXE`'s dispatcher plays no part in
this load. See `docs/renderer/MOVIE_LOADER_ARCHITECTURE.md` for the
full architecture investigation this correction came out of, including
why that earlier adjacency was a coincidence, not a real handoff.

**Two mistakes caught and corrected before trusting this result:**
first, the pointer table the dispatcher indexes into was assumed to
list names in the same order as the string table right next to it --
reading the table's actual pointer values against each string's real
address showed it's the *reverse* order, which would have silently
mapped every `movie_id` to the wrong file. Second, that corrected
per-index mapping was assumed to hold identically across every
chapter file without checking -- it does (verified independently per
file), but that was confirmed, not assumed.

**A real, honest limitation, not papered over:** `CAPX.EXE` has
exactly one such hardcoded call site too (`movie_id=9` ->
`MYOKO.EXE`) -- deliberately *not* added to
`gcrts.movie_detection.STATIC_MOVIE_TRIGGERS`, because it contradicts
the live-confirmed `MPRO.EXE` result for that same `CAPX.EXE`
residency window. `CAPX.EXE`'s real per-invocation `movie_id` for the
slot-6 case must come from a runtime value written by whichever
chapter handed off to it, not always this one constant. `CAP2.EXE` and
`CAP3.EXE` had zero such call sites at all -- either they don't
trigger a movie this way, or (like `CAPX.EXE`) they resolve it at
runtime. Per this whole project's standing rule, none of this --
including the corroborated `CAP0.EXE` result -- gets marked
`CONFIRMED_LIVE`; `STATIC_CODE_MATCH` is a distinct, honest confidence
tier, a prediction from real code, not a witnessed result.

**Tested live, found not-instant:** loading save slots 4 and 8 (both
independently confirmed resident in `CAP1.EXE` via `identify_overlay()`)
and watching for 30s each did not trigger `MKUBI.EXE` -- unlike slot
6, these saves aren't positioned right at the trigger boundary, so
reaching it needs real navigation forward within that chapter, not
just time passing.

## What's next

- **Play slots 4/8 (or any other `CAP1.EXE`/`CAP4.EXE` save) forward**
  to their actual trigger point with the console-text listener armed,
  to upgrade the `CAP1.EXE`->`MKUBI.EXE` and `CAP4.EXE`->`MRIKA.EXE`/
  `MNINO.EXE` predictions from `STATIC_CODE_MATCH` to `CONFIRMED_LIVE`.
- **Find `CAPX.EXE`'s runtime selector** -- the memory location whichever
  calling chapter writes into before handing off to `CAPX.EXE` --
  which would let every `CAPX.EXE`-routed movie be predicted the same
  way, including `MOVER.EXE`'s pairing.
- **Confirm the actual `.STR` file content**, not just the exe name,
  by reading real sector data during one of these movies (reusing this
  project's own established LBA resolution work) -- the same standard
  audio identification was ultimately held to.
- This directly unblocks the Subtitles thread's dependency on Movies
  having a stable, addressable event ID.

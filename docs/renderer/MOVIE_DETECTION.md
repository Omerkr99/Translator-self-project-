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

## What's next

- **Distinguish within the ambiguous groups.** The most direct next
  signal: the actual `.STR` sector data being read while one of these
  overlays is resident (reusing this project's own established LBA
  resolution work) would immediately disambiguate all three groups,
  the same way audio identification was ultimately resolved by
  checking real content, not just code identity.
- **Confirm `MOVER.EXE`/`MRIKA.EXE`'s file pairing** (`GAI.STR` vs.
  `KIKU.STR`) specifically, since those are the only two files with no
  name-correlation hypothesis at all yet.
- This directly unblocks the Subtitles thread's dependency on Movies
  having a stable, addressable event ID.

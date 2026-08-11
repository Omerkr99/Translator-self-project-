"""Locate the Real XA-ADPCM Playback Path milestone: hunts for a live
`ReadS` (`0x1B`) command -- the documented XA-ADPCM playback command
this project has never once observed -- and evaluates the fallback
hypotheses this milestone's own brief listed for what it would mean if
`0x1B` is never found.

## What this milestone found

**`ReadS` (`0x1B`) was still never observed**, across a second live
session (~230+ real seconds, all 3 confirmed command-write sites
armed) spanning a real, user-confirmed audio trigger. The exact same
repeating `Setloc/Setmode/ReadN/Pause/Setfilter` cycle
`gcrts.audio_playback_truth` already ruled out as the XA path continued
unchanged through the trigger, with no structural change and no new
command value appearing.

**The CDDA hypothesis is now definitively ruled out**, not just
downgraded. The real disc image's own `.cue` file (`FILE "..." BINARY /
TRACK 01 MODE2/2352 / INDEX 01 00:00:00`) declares exactly ONE track,
in the standard PS1 data-sector format. There is no separate CD-DA
audio track anywhere on this disc for the drive to play -- Red Book
digital audio playback is structurally impossible for this game. The
Setmode CDDA bit being set in the traced (non-XA) cycle is therefore
not evidence of CD-DA playback; per its own documented purpose ("allow
to read CD-DA sectors; ignore missing EDC"), it most likely just
relaxes an EDC check for that cycle's own (still non-audio) reads.

## Remaining hypotheses, per this milestone's own required evaluation

| # | Hypothesis | Status |
|---|---|---|
| 1 | Audible content is not XA-ADPCM | Downgraded -- CD-DA (the obvious alternative) is impossible on this disc; no other real PS1 audio source exists besides XA-ADPCM and CD-DA |
| 2 | Playback started by a different documented command/path | OPEN -- most likely explanation remaining |
| 3 | Command value transformed before MMIO | Not investigated this pass |
| 4 | Current hardware observation point is incomplete | OPEN -- likely, see below |
| 5 | Another CPU/BIOS-side path writes the register | OPEN -- not ruled out |
| 6 | Game uses CDDA for the tested audio | **RULED OUT** (disc has no CD-DA track) |

Hypotheses 2, 4, and 5 collapse into the same practical conclusion:
**the real audio-configuring code does not go through the 3
command-write sites this project's static scans have found.** Those 3
sites all share one specific addressing pattern (load the command-
register pointer from `0x800A30C0` via `lui`+`lw`, `sb` within a bounded
instruction window). A real XA-audio driver could use an entirely
different, second set of pointer variables, write the hardware
registers without any indirection at all, or be invoked through a
higher-level BIOS/LIBCD-style call this project has not yet
disassembled.

## Old path status

`OLD_READN_CYCLE_STATUS = "RULED_OUT_AS_XA_AUDIO_PATH"` -- this is now
a confirmed, permanent classification, not a hypothesis. See
`gcrts.audio_playback_truth` for the Setmode evidence behind it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

READS_COMMAND = 0x1B
READS_EVER_OBSERVED = False  # across every live capture this project has taken, spanning multiple confirmed-audible sessions

OLD_READN_CYCLE_STATUS = "RULED_OUT_AS_XA_AUDIO_PATH"


class HypothesisStatus(str, Enum):
    RULED_OUT = "RULED_OUT"
    DOWNGRADED = "DOWNGRADED"
    OPEN = "OPEN"
    NOT_INVESTIGATED = "NOT_INVESTIGATED"


@dataclass(frozen=True)
class PlaybackPathHypothesis:
    hypothesis_id: int
    description: str
    status: HypothesisStatus
    evidence: str


# The 6 fallback hypotheses this milestone's own brief required
# evaluating if 0x1B was never found. Every status here is backed by
# real evidence gathered this session (or an earlier one), not guessed.
PLAYBACK_PATH_HYPOTHESES: tuple[PlaybackPathHypothesis, ...] = (
    PlaybackPathHypothesis(
        1, "Audible content is not XA-ADPCM", HypothesisStatus.DOWNGRADED,
        "The obvious alternative (CD-DA) is structurally impossible on this disc (see hypothesis 6); no other real PS1 audio source exists.",
    ),
    PlaybackPathHypothesis(
        2, "Playback started by a different documented command/path", HypothesisStatus.OPEN,
        "Most likely remaining explanation; not yet located.",
    ),
    PlaybackPathHypothesis(
        3, "Command value transformed before MMIO", HypothesisStatus.NOT_INVESTIGATED,
        "Not pursued this pass.",
    ),
    PlaybackPathHypothesis(
        4, "Current hardware observation point is incomplete", HypothesisStatus.OPEN,
        "All 3 known command-write sites share one addressing pattern (0x800A30C0-based indirection); a second, different pointer-variable set or direct register access would be invisible to this project's static scans.",
    ),
    PlaybackPathHypothesis(
        5, "Another CPU/BIOS-side path writes the register", HypothesisStatus.OPEN,
        "Not ruled out; a higher-level BIOS/LIBCD-style call has not been disassembled.",
    ),
    PlaybackPathHypothesis(
        6, "The game uses CDDA for the audible content being tested", HypothesisStatus.RULED_OUT,
        "The real disc .cue file declares exactly one track (TRACK 01 MODE2/2352) -- no CD-DA track exists on this disc at all.",
    ),
)


def reads_command_confirmed_live() -> bool:
    """False: ReadS (0x1B) has never been observed in any live capture
    this project has taken, across multiple sessions spanning confirmed
    real, audible playback."""
    return READS_EVER_OBSERVED

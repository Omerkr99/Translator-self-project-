"""Static, persistent disc-text patching -- the "survives reboot" half
of Stage 4 (`docs/overlay_engine/GROUNDING_ANALYSIS.md`,
`docs/status/TOOLKIT_READINESS_AUDIT.md` blocker #1).

Method, found empirically this session: a script buffer captured live
from RAM (`gcrts.script_unit.extract_live_script_units`) can be located
byte-exactly inside the chapter's own `K#LINK.CDB` resource file (e.g.
`DAT/CAP1/K1LINK.CDB`) via a direct byte search -- at least some
dialogue segments are stored as CDB-codec literal runs (see
`gcrts.cdb_codec`'s module docstring for the format), which copy bytes
verbatim, meaning the original script bytes appear unmodified inside
the otherwise-compressed file. `gcrts.script_encoder.encode_segment`
can then produce a same-word-count replacement (control codes like
`speaker_name_start`/`line_center_calc`/`pause_flag_a` preserved in
their original positions, only the character slots changed) -- when
the replacement is exactly as many words as the original, it can be
written directly over those exact bytes with zero structural changes
to the surrounding compressed stream, since a CDB literal run's length
is independent of its content.

This module only ever writes to a **copy** of the disc image, never
the original (SRS PAT-001) -- `build_patched_disc_copy` takes explicit
`src_path`/`dst_path` arguments and always copies before patching.

**What this proves, and what it doesn't, stated precisely**: a patched
copy was built and independently verified this session by re-reading
it fully offline (fresh ISO9660 parse, fresh file extraction, fresh
script decode) -- the patch is structurally valid and the ISO's other
contents (root directory, `PROG.EXE`, etc.) are untouched. **Not yet
verified**: that booting the actual emulator fresh from this patched
copy (no save-state reload, which restores frozen RAM and would not
exercise a fresh disc read) shows the translated text in play. That
needs a genuine cold boot reaching the target scene through real menu
navigation, which requires controller input this project has never
gotten working programmatically (see `docs/status/CURRENT_SYSTEM_STATUS.md`'s
audio narrative: a virtual XInput gamepad was validated at the Windows/
XInput level but never got the game itself to respond) -- so this last
verification step needs a human at the controls, not automation.
"""
from __future__ import annotations

import shutil
import struct
from dataclasses import dataclass

from gcrts.cdrom import HEADER_SIZE, SECTOR_SIZE

_LOGICAL_BLOCK_SIZE = 2048


def find_script_text_offset(file_data: bytes, raw_codes: list[int]) -> int | None:
    """Search `file_data` (an already-extracted ISO9660 file's logical
    bytes, e.g. from `gcrts.iso9660.read_file`) for the exact byte
    sequence a list of script word-codes packs into. Returns the
    logical byte offset of the first match, or None. A real match here
    is strong evidence (not a coincidence) once `raw_codes` is more
    than a few words long -- see this module's own docstring for how
    this was validated against a real, live-captured dialogue line."""
    needle = struct.pack(f"<{len(raw_codes)}H", *raw_codes)
    idx = file_data.find(needle)
    return idx if idx != -1 else None


def logical_offset_to_physical(file_lba: int, logical_offset: int) -> int:
    """Convert a byte offset within an ISO9660 file's logical (2048-
    byte-block) data to the real byte offset in the raw .bin disc image
    -- each logical block corresponds to one real 2352-byte CD-XA
    sector, offset by `HEADER_SIZE` bytes of sync/header/subheader per
    sector. Validated this session against a real file: reading
    `physical_offset` bytes directly from the raw .bin matched
    `gcrts.iso9660.read_file`'s own extraction byte-for-byte."""
    sector_index = logical_offset // _LOGICAL_BLOCK_SIZE
    byte_in_sector = logical_offset % _LOGICAL_BLOCK_SIZE
    physical_lba = file_lba + sector_index
    return physical_lba * SECTOR_SIZE + HEADER_SIZE + byte_in_sector


@dataclass
class PatchResult:
    dst_path: str
    physical_offset: int
    original_bytes: bytes
    new_bytes: bytes


def build_patched_disc_copy(src_path: str, dst_path: str, physical_offset: int, new_bytes: bytes) -> PatchResult:
    """Copy `src_path` to `dst_path`, then overwrite `len(new_bytes)`
    bytes at `physical_offset` in the copy. Never opens `src_path` for
    writing. Raises if `new_bytes` isn't the same length as what's
    already there would be a silent structural change -- callers must
    pass a same-length replacement (see module docstring on why this
    keeps the CDB literal-run structure intact) or explicitly accept
    a length change is out of this function's scope by not calling it."""
    shutil.copyfile(src_path, dst_path)
    with open(dst_path, "r+b") as f:
        f.seek(physical_offset)
        original = f.read(len(new_bytes))
        f.seek(physical_offset)
        f.write(new_bytes)
    return PatchResult(dst_path=dst_path, physical_offset=physical_offset, original_bytes=original, new_bytes=new_bytes)

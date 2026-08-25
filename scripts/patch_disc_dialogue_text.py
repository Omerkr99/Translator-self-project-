"""End-to-end static disc-text patch: find a live dialogue line's exact
disc-source bytes, build a same-word-count translated replacement, and
write a patched disc-image copy -- formalizing the ad hoc method found
this session (see `gcrts.disc_text_patch`'s module docstring for the
full technical account).

This is a STATIC-ONLY operation once the source `raw_codes` are known
-- it optionally captures them live from a running emulator (so the
target text doesn't have to be hand-transcribed), but everything after
that (disc search, re-encoding, patching) touches only the disc image
copy, never a live process.

Only ever writes to `--dst-disc` after copying `--src-disc` there
first -- never opens the source disc image for writing.

Usage (capturing the target line live from a running emulator):
    python -m scripts.patch_disc_dialogue_text \
        --slot 4 --unit-index 0 --text "Hi Kimika" \
        --cap-dir CAP1 --klink-name K1LINK.CDB \
        --src-disc "קיבצי דמה/Twilight Syndrome - Tansaku Hen (Japan).bin" \
        --dst-disc build_workspace/patched_discs/patch1.bin
"""
from __future__ import annotations

import argparse
import sys

import gcrts.iso9660 as iso
from gcrts.disc_text_patch import build_patched_disc_copy, find_script_text_offset, logical_offset_to_physical
from gcrts.editable_script import to_editable
from gcrts.script_decoder import decode_script
from gcrts.script_encoder import encode_segment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", type=int, required=True, help="save-state slot with the target dialogue live")
    parser.add_argument("--unit-index", type=int, required=True)
    parser.add_argument("--text", required=True, help="translated replacement text")
    parser.add_argument("--cap-dir", required=True, help="e.g. CAP1")
    parser.add_argument("--klink-name", required=True, help="e.g. K1LINK.CDB")
    parser.add_argument("--src-disc", required=True)
    parser.add_argument("--dst-disc", required=True)
    parser.add_argument("--gdb-port", type=int, default=3334)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args(argv)

    import urllib.request

    from gcrts.pcsx_redux_adapter import PCSXReduxAdapter
    from gcrts.script_unit import extract_live_script_units

    # Pause immediately after load for a deterministic snapshot -- the
    # dialogue in at least some scenes auto-advances in real time, so
    # capturing without pausing first gets a timing-dependent, non-
    # repeatable segmentation (found the hard way this session: the
    # same slot/index pair returned a 12-word unit in one capture and
    # a 19-word unit in another, purely from elapsed wall-clock time
    # between the state load and the capture call).
    adapter = PCSXReduxAdapter(gdb_port=args.gdb_port, api_base_url=args.api_base_url, connect=True)
    try:
        urllib.request.urlopen(f"{args.api_base_url}/api/v1/state/load?slot={args.slot}", timeout=10).read()
        adapter.pause()
        units = extract_live_script_units("patch_disc_dialogue_text", port=args.gdb_port)
    finally:
        adapter.resume()
        adapter.shutdown()

    if args.unit_index >= len(units):
        print(f"unit index {args.unit_index} out of range ({len(units)} captured)", file=sys.stderr)
        return 1
    raw_codes = units[args.unit_index].raw_codes
    print(f"captured live unit {args.unit_index}: {len(raw_codes)} words, original={units[args.unit_index].original_text!r}")

    with open(args.src_disc, "rb") as f:
        raw = f.read()
    root = iso.read_root_directory(raw)
    dat = next(e for e in root if e.name == "DAT")
    dat_entries = iso.read_directory(raw, dat)
    cap_dir = next(e for e in dat_entries if e.name == args.cap_dir)
    files = iso.read_directory(raw, cap_dir)
    klink = next(e for e in files if e.name == f"{args.klink_name};1")
    file_data = iso.read_file(raw, klink)

    logical_offset = find_script_text_offset(file_data, raw_codes)
    if logical_offset is None:
        print("could not find this dialogue's raw bytes on disc -- not every line is stored as a literal run", file=sys.stderr)
        return 1
    print(f"found on-disc source: {args.klink_name} logical offset {logical_offset}")

    chunk = file_data[logical_offset : logical_offset + len(raw_codes) * 2] + b"\xff\xff"
    doc = decode_script(chunk)
    editable = to_editable(doc)
    segment = editable.segments[0]
    segment.translated = args.text
    new_words = encode_segment(segment)

    if len(new_words) != len(raw_codes):
        print(
            f"re-encoded translation is {len(new_words)} words, original is {len(raw_codes)} -- "
            "a same-length replacement is required to patch in place without restructuring the "
            "surrounding compressed stream; choose different text or a different unit",
            file=sys.stderr,
        )
        return 1

    import struct

    new_bytes = struct.pack(f"<{len(new_words)}H", *new_words)
    physical_offset = logical_offset_to_physical(klink.lba, logical_offset)
    result = build_patched_disc_copy(args.src_disc, args.dst_disc, physical_offset, new_bytes)
    print(f"patched copy written: {result.dst_path}")
    print(f"  physical offset: {result.physical_offset}")
    print(f"  original bytes: {result.original_bytes.hex()}")
    print(f"  new bytes:      {result.new_bytes.hex()}")

    # offline verification against the copy just written, independent of any live state
    with open(args.dst_disc, "rb") as f:
        verify_raw = f.read()
    verify_root = iso.read_root_directory(verify_raw)
    verify_dat = next(e for e in verify_root if e.name == "DAT")
    verify_dat_entries = iso.read_directory(verify_raw, verify_dat)
    verify_cap = next(e for e in verify_dat_entries if e.name == args.cap_dir)
    verify_files = iso.read_directory(verify_raw, verify_cap)
    verify_klink = next(e for e in verify_files if e.name == f"{args.klink_name};1")
    verify_data = iso.read_file(verify_raw, verify_klink)
    verify_chunk = verify_data[logical_offset : logical_offset + len(raw_codes) * 2] + b"\xff\xff"
    verify_doc = decode_script(verify_chunk)
    verify_editable = to_editable(verify_doc)
    print(f"offline verification (fresh read of the patched copy): {verify_editable.segments[0].original!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

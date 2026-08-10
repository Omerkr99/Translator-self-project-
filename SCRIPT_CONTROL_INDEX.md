# Script Control Index

Reusable index over observed script control words. Built by
`gcrts/control_code_index.py` (`ControlCodeIndex`, tested in
`tests/test_control_code_index.py`) — extend this tool for future
control-code research rather than writing another one-off scanner.

## How to use

```python
from gcrts.live_extract import GdbClient
from gcrts.control_code_index import ControlCodeIndex

client = GdbClient(timeout=15)
data = client.read_memory(0x801FE800, 4096)
client.close()

words = [int.from_bytes(data[i:i+2], "little") for i in range(0, len(data), 2)]
if 0xFFFF in words:
    words = words[: words.index(0xFFFF) + 1]

index = ControlCodeIndex()
index.scan_words(words, unit_id="some_scene_name")
print(index.to_markdown())   # or index.to_json()
```

Re-run against each new scene reached in-game and accumulate into one
running `ControlCodeIndex` instance to build real coverage over time.

## Snapshot: one live scene, scanned this session

| raw_word | family | subtype | parameter | meaning | occurrences | decoder_output | verified |
|---|---|---|---|---|---|---|---|
| 0x8100 | control_a | 0x0100 | 0 | set_flag_d10 | 6 | - | no |
| 0x8300 | control_a | 0x0300 | 0 | low_byte_passthrough | 1 | - | no |
| 0x8301 | control_a | 0x0300 | 1 | low_byte_passthrough | 1 | - | no |
| 0x8408 | control_a | 0x0400 | 8 | set_mode_ce4 | 4 | - | no |
| 0x8500 | control_a | 0x0500 | 0 | pause_flag_a | 2 | - | no |
| 0x8600 | control_a | 0x0600 | 0 | pause_flag_b | 1 | - | no |
| 0x8900 | control_a | 0x0900 | 0 | speaker_name_start | 1 | - | no |
| 0x8a00 | control_a | 0x0a00 | 0 | speaker_name_end | 1 | - | no |
| 0xc819 | control_b | 0x0800 | 25 | sound_or_voice_cue | 1 | - | no |
| 0xcc00 | control_b | 0x0c00 | 0 | call_FUN_8004ab98 | 1 | - | no |
| 0xce01 | control_b | 0x0e00 | 1 | call_FUN_80049e30 | 1 | - | no |
| 0xce02 | control_b | 0x0e00 | 2 | call_FUN_80049e30 | 1 | - | no |
| 0xcf00 | control_b | 0x0f00 | 0 | set_flag_0x20_and_c60 | 1 | - | no |

**Key finding**: `pause_flag_a` (`0x8500`, subtype `0x0500`) genuinely
occurs in real script data — 2 occurrences in this one scene — but
always with **parameter = 0** here. Per `MODE3_TRIGGER_INVESTIGATION.md`,
`Y_COLLECTION_MODE` requires a **nonzero** parameter (`0x8501`-`0x85FF`).
This is concrete, positive evidence the control code is real and not
rare in an absolute sense — the search should continue across more
scenes specifically looking for a nonzero-parameter occurrence, using
this same reusable tool.

## Not yet indexed

Offline CDB script resources (`K0LINK.CDB` and siblings) were not
successfully indexed this round — see `MODE3_TRIGGER_INVESTIGATION.md`'s
"Script-data search findings" for why (the directory-table format's
exact indexing scheme remains unresolved, consistent with this
project's own pre-existing documented uncertainty in `README.md`).
Extending `ControlCodeIndex` to ingest CDB-derived word streams once
that format is solved would be a natural next step — the index itself
doesn't care where words come from.

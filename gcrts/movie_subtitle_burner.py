"""Consolidates this session's manually-run, scratchpad pipeline
(decode -> burn text onto specific frames -> re-encode -> disc-patch)
into a single, reusable tool that burns an ENTIRE
`gcrts.overlay_action.SubtitleTrackPayload` into a movie -- not just
one placeholder cue. This is the actual deliverable mechanism per the
user's own correction (see the `project-fandub-goal` memory and
`docs/renderer/BURNED_IN_SUBTITLE_PIPELINE.md`, `CONFIRMED_LIVE` for
one cue this session): subtitles burned into disc-resident video data,
no host-side tooling required at playback time.

NOTE ON TIMING: cue placement here uses the movie's own internal frame
numbering (`t_offset_seconds * fps`), which was independently verified
correct by re-decoding the encoded `.str` output and confirming the
burned text lands at the exact intended frame numbers
(`evidence/burned_in_subtitle_live_playback/`). This is UNRELATED to
the ~10.7s live-playback calibration gotcha documented in
`BURNED_IN_SUBTITLE_PIPELINE.md` -- that offset only affects finding a
cue's appearance time when testing against a *live, running* emulator
via `gcrts.overlay_identity`-based real-time anchoring; it has no
bearing on this module's frame-index math, which operates purely on
the movie's own internal timeline.

The pure logic (which frames belong to which cue) is unit-tested here.
The live orchestration function (`build_burned_in_movie`) wraps
FFmpeg + `psxavenc` + real disc I/O and is manually verified only,
matching this project's established convention for live/external-tool
modules.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from PIL import Image

from gcrts.burn_in_subtitle import burn_subtitle_onto_frame
from gcrts.disc_text_patch import build_patched_disc_copy
from gcrts.movie_detection import MOVIE_CATALOG
from gcrts.movie_str_audio import extract_str_audio_wav, read_raw_str_bytes
from gcrts.movie_str_encoder import encode_str
from gcrts.overlay_action import SubtitleCue, SubtitleTrackPayload

DEFAULT_FPS = 15.0


def cue_to_frame_range(cue: SubtitleCue, fps: float = DEFAULT_FPS) -> tuple[int, int]:
    """Returns `(start_frame, end_frame)`, both 0-indexed and
    inclusive, matching the movie's own internal frame numbering (the
    same numbering FFmpeg reports via `select=eq(n,N)` when decoding
    the movie, and the same one used throughout this session's own
    live verification)."""
    start = int(cue.t_offset_seconds * fps)
    end = int((cue.t_offset_seconds + cue.duration_seconds) * fps)
    return start, end


def burn_cues_onto_frame_files(frame_paths: Sequence[str | Path], cues: Sequence[SubtitleCue], fps: float = DEFAULT_FPS) -> list[int]:
    """`frame_paths` must be ordered such that `frame_paths[i]` is
    frame `i` (0-indexed) of the decoded movie. Burns each cue's text
    onto its own frame range, overwriting those files in place.
    Returns the sorted list of frame indices that were modified, for
    verification -- callers should confirm this matches expectations
    before trusting the output, the same way this session verified by
    direct visual inspection rather than assuming the math was right."""
    modified: set[int] = set()
    for cue in cues:
        start, end = cue_to_frame_range(cue, fps)
        for i in range(start, end + 1):
            if i < 0 or i >= len(frame_paths):
                continue
            path = frame_paths[i]
            frame = Image.open(path)
            burned = burn_subtitle_onto_frame(frame, cue.text)
            burned.save(path)
            modified.add(i)
    return sorted(modified)


def build_burned_in_movie(
    disc_path: str | Path,
    movie_name: str,
    track: SubtitleTrackPayload,
    psxavenc_exe: str | Path,
    output_str_path: str | Path,
    work_dir: str | Path,
    fps: float = DEFAULT_FPS,
) -> Path:
    """Live orchestration, manually verified only (see module
    docstring). Decodes `movie_name` from `disc_path`, burns every cue
    in `track` onto its own frame range, re-muxes, re-encodes via
    `psxavenc`, and returns the path to the resulting `.str` file --
    callers patch it into a disc image copy themselves via
    `gcrts.disc_text_patch.build_patched_disc_copy` (kept separate so
    this function's own failure modes -- a bad decode, a bad encode --
    are distinguishable from a bad disc patch)."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = work_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    entry = next(e for e in MOVIE_CATALOG if e.name == movie_name)
    raw = read_raw_str_bytes(disc_path, entry.lba, entry.size)
    raw_str_path = work_dir / "raw.str"
    raw_str_path.write_bytes(raw)

    wav_path = work_dir / "audio.wav"
    extract_str_audio_wav(raw, wav_path)

    intermediate_path = work_dir / "intermediate.mkv"
    subprocess.run(
        [ffmpeg, "-y", "-f", "psxstr", "-i", str(raw_str_path), "-c:v", "ffv1", "-c:a", "pcm_s16le", str(intermediate_path)],
        check=True, capture_output=True,
    )

    frame_pattern = str(frames_dir / "frame_%05d.png")
    subprocess.run([ffmpeg, "-y", "-i", str(intermediate_path), "-vsync", "0", frame_pattern], check=True, capture_output=True)
    frame_paths = sorted(frames_dir.glob("frame_*.png"))

    modified = burn_cues_onto_frame_files(frame_paths, track.cues, fps)

    edited_path = work_dir / "edited.mkv"
    subprocess.run(
        [ffmpeg, "-y", "-r", str(fps), "-i", frame_pattern, "-i", str(wav_path),
         "-c:v", "ffv1", "-c:a", "pcm_s16le", "-map", "0:v", "-map", "1:a", str(edited_path)],
        check=True, capture_output=True,
    )

    output_str_path = Path(output_str_path)
    encode_str(psxavenc_exe, edited_path, output_str_path)

    shutil.rmtree(frames_dir, ignore_errors=True)
    return output_str_path


def patch_movie_into_disc(
    disc_path: str | Path,
    output_disc_path: str | Path,
    movie_name: str,
    new_str_path: str | Path,
) -> None:
    """Thin wrapper over `gcrts.disc_text_patch.build_patched_disc_copy`
    that looks up `movie_name`'s real LBA from `gcrts.movie_detection.MOVIE_CATALOG`
    -- kept separate from `build_burned_in_movie` so re-patching a
    disc doesn't require re-running the (slow) decode/encode step."""
    entry = next(e for e in MOVIE_CATALOG if e.name == movie_name)
    physical_offset = entry.lba * 2352
    new_bytes = Path(new_str_path).read_bytes()
    build_patched_disc_copy(str(disc_path), str(output_disc_path), physical_offset, new_bytes)

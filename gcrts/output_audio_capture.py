"""Host-side WASAPI loopback recording of the system's actual digital
audio output (not a microphone) -- captures exactly what PCSX-Redux
sends to the speakers, per the milestone's own governing principle:
"capture the exact sound that reached the speakers, then identify
where that sound exists on disc." Uses PyAudioWPatch, a WASAPI-patched
PyAudio fork with native loopback-device support on Windows.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass

import pyaudiowpatch as pyaudio

CHUNK = 1024


@dataclass
class CaptureResult:
    path: str
    sample_rate: int
    channels: int
    sample_width: int
    duration_seconds: float


def find_default_loopback_device(p: "pyaudio.PyAudio") -> dict:
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                return loopback
        raise RuntimeError("no matching loopback device found for the default output")
    return default_speakers


def record_loopback(out_path: str, duration_seconds: float) -> CaptureResult:
    """Records exactly `duration_seconds` of the system's real digital
    output (loopback), starting the instant this is called."""
    p = pyaudio.PyAudio()
    try:
        device = find_default_loopback_device(p)
        sample_rate = int(device["defaultSampleRate"])
        channels = device["maxInputChannels"]

        frames = []
        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            frames_per_buffer=CHUNK,
            input=True,
            input_device_index=device["index"],
        )
        try:
            n_chunks = int(sample_rate / CHUNK * duration_seconds)
            for _ in range(n_chunks):
                frames.append(stream.read(CHUNK))
        finally:
            stream.stop_stream()
            stream.close()

        data = b"".join(frames)
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
            wf.setframerate(sample_rate)
            wf.writeframes(data)

        actual_duration = len(data) / (sample_rate * channels * 2)
        return CaptureResult(
            path=out_path, sample_rate=sample_rate, channels=channels,
            sample_width=2, duration_seconds=actual_duration,
        )
    finally:
        p.terminate()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_path")
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()

    result = record_loopback(args.out_path, args.duration)
    print(f"wrote {result.duration_seconds:.2f}s, {result.sample_rate}Hz, {result.channels}ch to {result.path}")

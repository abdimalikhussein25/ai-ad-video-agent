"""Optional voiceover with Microsoft Edge neural voices (free, no key) via `edge-tts`."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from .models import Script

VOICES = {"en": "en-US-AndrewNeural", "so": "so-SO-UbaxNeural"}


def synthesize(script: Script, language: str, out_dir: Path) -> list[Path | None]:
    """One audio clip per scene. Returns None for scenes when TTS is unavailable."""
    try:
        import edge_tts  # optional dependency
    except ImportError:
        return [None] * len(script.scenes)

    async def run():
        paths: list[Path | None] = []
        for i, scene in enumerate(script.scenes):
            if not scene.voiceover:
                paths.append(None)
                continue
            path = out_dir / f"vo_{i}.mp3"
            await edge_tts.Communicate(scene.voiceover, VOICES[language]).save(str(path))
            paths.append(path)
        return paths

    try:
        return asyncio.run(run())
    except Exception:  # network down, voice unavailable — the video still renders silently
        return [None] * len(script.scenes)


def audio_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def fit_scenes_to_audio(script: Script, clips: list[Path | None], padding: float = 0.6) -> None:
    """Make each scene at least as long as its voiceover."""
    for scene, clip in zip(script.scenes, clips):
        if clip is not None:
            scene.seconds = max(scene.seconds, min(8.0, audio_seconds(clip) + padding))

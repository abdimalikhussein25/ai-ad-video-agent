"""`ad-agent brief.json` → out/<product>.mp4"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__
from .models import Brief, Script
from .render import render, render_poster
from .script import write_script
from .voice import fit_scenes_to_audio, synthesize


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "ad"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ad-agent", description="Turn a product brief into a 9:16 video ad.")
    p.add_argument("brief", help="path to a brief JSON file")
    p.add_argument("-o", "--out", default="out", help="output directory")
    p.add_argument("--script", help="use an existing script JSON instead of writing one")
    p.add_argument("--no-voice", action="store_true", help="skip the voiceover")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    brief = Brief.load(args.brief)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = slug(brief.product)

    if args.script:
        script, source = Script.from_dict(json.loads(Path(args.script).read_text(encoding="utf-8"))), "file"
    else:
        script, source = write_script(brief)
    print(f"✍️  Script ({source}): {len(script.scenes)} scenes", file=sys.stderr)
    for s in script.scenes:
        print(f"    [{s.style:>7}] {s.headline}", file=sys.stderr)

    audio = None
    if not args.no_voice:
        audio = synthesize(script, brief.language, out)
        if any(audio):
            fit_scenes_to_audio(script, audio)
            print("🎙️  Voiceover ready", file=sys.stderr)
        else:
            print("🎙️  No voiceover (pip install edge-tts to enable)", file=sys.stderr)

    (out / f"{name}.script.json").write_text(json.dumps(script.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    render_poster(script, brief, out / f"{name}.png")
    video = render(script, brief, out / f"{name}.mp4", audio, fps=args.fps)
    for clip in audio or []:
        if clip:
            clip.unlink(missing_ok=True)
    print(f"🎬 {video}  ({script.duration:.1f}s, 1080×1920)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

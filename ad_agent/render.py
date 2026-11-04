"""Render scenes to a 1080×1920 MP4 with kinetic typography, using Pillow + ffmpeg."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import Brief, Scene, Script

W, H = 1080, 1920
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
FONT_REGULAR = [
    "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def hex_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_frame(scene: Scene, t: float, brief: Brief, index: int, total: int) -> Image.Image:
    """t = seconds since the scene started."""
    brand, accent = hex_rgb(brief.brand_color), hex_rgb(brief.accent_color)
    is_cta = scene.style == "cta"
    bg = accent if is_cta else brand
    fg = brand if is_cta else (255, 255, 255)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # Slow-moving background circle for depth.
    r = 520 + 40 * math.sin(t * 1.2 + index)
    cx, cy = (W * (0.85 if index % 2 else 0.15)), H * 0.25 + 60 * math.sin(t * 0.8)
    shade = tuple(min(255, int(c * 1.15 + 12)) for c in bg)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=shade)

    head_font = _font(FONT_CANDIDATES, 118 if len(scene.headline) < 22 else 96)
    sub_font = _font(FONT_REGULAR, 54)

    # Headline slides up and fades in, line by line.
    lines = wrap(d, scene.headline, head_font, W - 160)
    line_h = head_font.size * 1.12
    block_h = line_h * len(lines)
    y0 = H * 0.42 - block_h / 2
    for i, line in enumerate(lines):
        p = ease_out((t - 0.12 * i) / 0.55)
        y = y0 + i * line_h + (1 - p) * 90
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((80, y), line, font=head_font, fill=(*fg, int(255 * p)))
        img.paste(layer, (0, 0), layer)

    # Accent bar grows under the headline.
    bar_p = ease_out((t - 0.3) / 0.5)
    bar_y = y0 + block_h + 30
    d.rounded_rectangle((80, bar_y, 80 + 220 * bar_p, bar_y + 16), radius=8, fill=fg if is_cta else accent)

    if scene.subtext:
        p = ease_out((t - 0.55) / 0.5)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for i, line in enumerate(wrap(ld, scene.subtext, sub_font, W - 160)):
            ld.text((80, bar_y + 60 + i * 68 + (1 - p) * 40), line, font=sub_font, fill=(*fg, int(235 * p)))
        img.paste(layer, (0, 0), layer)

    # CTA button pulses.
    if is_cta and brief.contact:
        pulse = 1 + 0.04 * math.sin(t * 6)
        bw, bh = 760 * pulse, 150 * pulse
        bx, by = (W - bw) / 2, H * 0.78
        d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=bh / 2, fill=brand)
        btn_font = _font(FONT_CANDIDATES, 64)
        tw = d.textlength(brief.contact, font=btn_font)
        d.text(((W - tw) / 2, by + (bh - 64) / 2 - 6), brief.contact, font=btn_font, fill=accent)

    # Progress dots.
    for i in range(total):
        x = W / 2 + (i - (total - 1) / 2) * 38
        d.ellipse((x - 8, 90, x + 8, 106), fill=fg if i <= index else tuple(min(255, c + 60) for c in bg))
    return img


def render(script: Script, brief: Brief, out_path: Path, audio: list[Path | None] | None = None, fps: int = 30) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required — install it from https://ffmpeg.org")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent = out_path.with_suffix(".silent.mp4")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(silent),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin
    total = len(script.scenes)
    for idx, scene in enumerate(script.scenes):
        for f in range(round(scene.seconds * fps)):
            proc.stdin.write(draw_frame(scene, f / fps, brief, idx, total).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding video")

    clips = [(c, sum(s.seconds for s in script.scenes[:i])) for i, c in enumerate(audio or []) if c is not None]
    if not clips:
        silent.replace(out_path)
        return out_path

    inputs, filters = ["-i", str(silent)], []
    for n, (clip, start) in enumerate(clips, start=1):
        inputs += ["-i", str(clip)]
        ms = int(start * 1000)
        filters.append(f"[{n}:a]adelay={ms}|{ms}[a{n}]")
    mix = "".join(f"[a{n}]" for n in range(1, len(clips) + 1))
    filters.append(f"{mix}amix=inputs={len(clips)}:normalize=0[aout]")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
         "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out_path)],
        check=True,
    )
    silent.unlink(missing_ok=True)
    return out_path


def render_poster(script: Script, brief: Brief, out_path: Path) -> Path:
    """Still frame of the first scene — handy as a thumbnail."""
    draw_frame(script.scenes[0], 2.0, brief, 0, len(script.scenes)).save(out_path)
    return out_path

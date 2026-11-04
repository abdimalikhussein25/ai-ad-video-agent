import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ad_agent.models import Brief, Scene, Script
from ad_agent.render import draw_frame, render, wrap, W, H
from ad_agent.script import write_from_template, write_with_claude

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_brief_loads_and_validates(tmp_path):
    brief = Brief.load(EXAMPLES / "brief.json")
    assert brief.product == "Nomad Cold Brew"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"product": "x", "description": "y", "brand_color": "green"}))
    with pytest.raises(ValueError):
        Brief.load(bad)


def test_template_script_en_and_so():
    en = write_from_template(Brief.load(EXAMPLES / "brief.json"))
    assert [s.style for s in en.scenes] == ["hook", "feature", "offer", "cta"]
    assert en.duration == pytest.approx(16)
    so = write_from_template(Brief.load(EXAMPLES / "brief.so.json"))
    assert so.scenes[0].headline.startswith("Ma raadinaysaa")


def test_script_rules():
    with pytest.raises(ValueError):
        Script.from_dict({"scenes": [{"style": "hook", "headline": "a"}] * 3})  # no CTA
    with pytest.raises(ValueError):
        Scene(style="dance", headline="x")
    assert Scene(style="hook", headline="x", seconds=99).seconds == 8.0


def test_claude_path_parses_and_retries():
    good = {"scenes": [{"style": "hook", "headline": "Hungry?"}, {"style": "feature", "headline": "Fast"},
                       {"style": "cta", "headline": "Order"}]}
    replies = iter(["sorry, no json", "Here you go:\n" + json.dumps(good)])

    class FakeClient:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                assert "Never invent statistics" in kwargs["messages"][0]["content"]
                return SimpleNamespace(content=[SimpleNamespace(type="text", text=next(replies))])

    script = write_with_claude(Brief.load(EXAMPLES / "brief.json"), client=FakeClient())
    assert script.scenes[-1].style == "cta"


def test_frames_have_the_right_size_and_animate():
    brief = Brief.load(EXAMPLES / "brief.json")
    scene = write_from_template(brief).scenes[0]
    a, b = draw_frame(scene, 0.0, brief, 0, 4), draw_frame(scene, 1.5, brief, 0, 4)
    assert a.size == (W, H)
    assert a.tobytes() != b.tobytes()


def test_wrap_respects_width():
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = wrap(d, "one two three four five six seven eight", d.font, 60)
    assert len(lines) > 1


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_render_short_video(tmp_path):
    brief = Brief.load(EXAMPLES / "brief.json")
    script = Script.from_dict({"scenes": [
        {"style": "hook", "headline": "Hi", "seconds": 1.5},
        {"style": "feature", "headline": "Fast", "seconds": 1.5},
        {"style": "cta", "headline": "Go", "seconds": 1.5},
    ]})
    out = render(script, brief, tmp_path / "ad.mp4", fps=6)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(out)], capture_output=True, text=True)
    assert probe.stdout.strip() == "1080,1920"

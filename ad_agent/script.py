"""Write the ad script: with Claude when an API key is present, otherwise from a template."""

from __future__ import annotations

import json
import os
import re

from .models import Brief, Script

MODEL = os.environ.get("AD_AGENT_MODEL", "claude-sonnet-5-5")

PROMPT = """You are a performance-marketing copywriter making a {duration}-second vertical (9:16) video ad.

Product: {product}
What it is: {description}
Audience: {audience}
Price: {price}
Offer: {offer}
Call to action: {cta}
Contact: {contact}
Language: {language_name}

Write 4–6 scenes. Rules:
- Scene 1 style "hook": stop the scroll in under 2 seconds — a question or a pain point.
- Middle scenes use styles "feature", "proof" or "offer". One idea per scene.
- Last scene style "cta" with the call to action{contact_rule}.
- headline: max 6 words, punchy. subtext: max 12 words. voiceover: one natural spoken sentence.
- seconds per scene between 2.5 and 5; total close to {duration}.
- Never invent statistics, awards or testimonials. Only use facts from the brief.

Reply with JSON only: {{"scenes": [{{"style": "...", "headline": "...", "subtext": "...", "voiceover": "...", "seconds": 3.5}}]}}"""


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("model did not return JSON")
    return json.loads(match.group(0))


def write_with_claude(brief: Brief, client=None) -> Script:
    if client is None:
        import anthropic  # optional dependency

        client = anthropic.Anthropic()
    prompt = PROMPT.format(
        duration=brief.duration,
        product=brief.product,
        description=brief.description,
        audience=brief.audience,
        price=brief.price or "not stated",
        offer=brief.offer or "none",
        cta=brief.cta,
        contact=brief.contact or "none",
        language_name="Somali" if brief.language == "so" else "English",
        contact_rule=f" and show the contact '{brief.contact}'" if brief.contact else "",
    )
    last_error: Exception | None = None
    for _ in range(2):  # one retry if the JSON is malformed
        msg = client.messages.create(model=MODEL, max_tokens=1200, messages=[{"role": "user", "content": prompt}])
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        try:
            return Script.from_dict(_extract_json(text))
        except (ValueError, KeyError, TypeError) as e:
            last_error = e
    raise RuntimeError(f"could not get a valid script from the model: {last_error}")


TEMPLATES = {
    "en": {
        "hook": ("Still looking for {product}?", "There's a better way."),
        "feature": ("Meet {product}", "{description}"),
        "offer": ("Only {price}", "{offer}"),
        "cta": ("{cta}", "{offer}"),
    },
    "so": {
        "hook": ("Ma raadinaysaa {product}?", "Waxaa jira hab ka fiican."),
        "feature": ("Bar {product}", "{description}"),
        "offer": ("Kaliya {price}", "{offer}"),
        "cta": ("{cta}", "{offer}"),
    },
}


def write_from_template(brief: Brief) -> Script:
    """Deterministic fallback so the tool works with no API key."""
    t = TEMPLATES[brief.language]
    fields = {k: (v or "") for k, v in brief.__dict__.items()}
    styles = ["hook", "feature"] + (["offer"] if brief.price or brief.offer else []) + ["cta"]
    per_scene = brief.duration / len(styles)
    scenes = []
    for style in styles:
        headline, sub = (part.format(**fields) for part in t[style])
        scenes.append({"style": style, "headline": headline, "subtext": sub, "voiceover": f"{headline}. {sub}".strip(" ."), "seconds": per_scene})
    return Script.from_dict({"scenes": scenes})


def write_script(brief: Brief) -> tuple[Script, str]:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return write_with_claude(brief), "claude"
        except ImportError:
            pass
    return write_from_template(brief), "template"

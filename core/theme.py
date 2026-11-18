"""Read the theme stylesheet, resolve palette tokens and check text contrast."""

import re
from pathlib import Path

from django.conf import settings

PALETTES = ["ocean", "forest", "sunset", "slate", "plum"]
MODES = ["light", "dark"]
MIN_CONTRAST = 4.5

BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
VAR_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
VAR_USE_RE = re.compile(r"var\((--[\w-]+)\)")
COLOR_MIX_RE = re.compile(
    r"color-mix\(in srgb,\s*(#[0-9a-fA-F]{3,8})\s+([\d.]+)%,\s*(#[0-9a-fA-F]{3,8})\s*\)"
)

CONTRAST_PAIRS = [
    ("text-1", "surface", "Body text on surface"),
    ("text-1", "surface-raised", "Body text on raised surface"),
    ("text-2", "surface", "Secondary text on surface"),
    ("text-2", "surface-raised", "Secondary text on raised surface"),
    ("text-3", "surface", "Faint text on surface"),
    ("accent", "surface", "Accent text on surface"),
    ("accent-contrast", "accent", "Text on accent button"),
    ("accent", "accent-soft", "Active navigation text"),
    ("ok", "ok-soft", "Success badge"),
    ("warn", "warn-soft", "Warning badge"),
    ("bad", "bad-soft", "Danger badge"),
    ("neutral", "neutral-soft", "Neutral badge"),
]


def theme_css_path() -> Path:
    return Path(settings.BASE_DIR) / "static" / "css" / "theme.css"


def parse_blocks(css_text: str):
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.S)
    blocks = []
    for selector, body in BLOCK_RE.findall(css_text):
        selector = selector.strip()
        if not selector.startswith(":root"):
            continue
        tokens = dict(VAR_RE.findall(body))
        if tokens:
            blocks.append((selector, tokens))
    return blocks


def selector_specificity(selector: str, mode: str, palette: str):
    """Return None when the selector does not apply, else its attribute count."""
    conditions = re.findall(r'\[([\w-]+)="([^"]+)"\]', selector)
    specificity = 0
    for attribute, value in conditions:
        if attribute == "data-mode":
            if value != mode:
                return None
        elif attribute == "data-palette":
            if value != palette:
                return None
        else:
            return None
        specificity += 1
    # Ignore selectors that only target other attributes (density/text size).
    remainder = re.sub(r'\[[^\]]+\]', "", selector).strip()
    if remainder != ":root":
        return None
    return specificity


def resolve_tokens(mode: str, palette: str, blocks=None):
    css_path = theme_css_path()
    if blocks is None:
        blocks = parse_blocks(css_path.read_text(encoding="utf-8"))
    applicable = []
    for index, (selector, tokens) in enumerate(blocks):
        specificity = selector_specificity(selector, mode, palette)
        if specificity is not None:
            applicable.append((specificity, index, tokens))
    applicable.sort(key=lambda item: (item[0], item[1]))
    merged = {}
    for _, _, tokens in applicable:
        merged.update(tokens)
    return merged


def parse_hex(value):
    if not value:
        return None
    match = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value.strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))


def resolve_color(name: str, tokens, seen=None):
    """Resolve a token to an RGB tuple, following var() and simple color-mix()."""
    token_name = name if name.startswith("--") else f"--{name}"
    seen = seen or set()
    if token_name in seen:
        return None
    seen.add(token_name)
    value = tokens.get(token_name)
    if value is None:
        return None
    value = value.strip()

    for _ in range(10):
        match = VAR_USE_RE.search(value)
        if not match:
            break
        replacement = resolve_color(match.group(1), tokens, seen)
        if replacement is None:
            return None
        value = (
            value[: match.start()]
            + "#{:02x}{:02x}{:02x}".format(*replacement)
            + value[match.end() :]
        )

    direct = parse_hex(value)
    if direct:
        return direct

    mix = COLOR_MIX_RE.search(value)
    if mix:
        first = parse_hex(mix.group(1))
        second = parse_hex(mix.group(3))
        if first and second:
            weight = float(mix.group(2)) / 100.0
            return tuple(
                round(first[i] * weight + second[i] * (1 - weight)) for i in range(3)
            )
    return None


def channel_luminance(channel: int) -> float:
    value = channel / 255.0
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb) -> float:
    return (
        0.2126 * channel_luminance(rgb[0])
        + 0.7152 * channel_luminance(rgb[1])
        + 0.0722 * channel_luminance(rgb[2])
    )


def contrast_ratio(first, second) -> float:
    l1 = luminance(first)
    l2 = luminance(second)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def check_all(min_contrast: float = MIN_CONTRAST):
    blocks = parse_blocks(theme_css_path().read_text(encoding="utf-8"))
    results = []
    for mode in MODES:
        for palette in PALETTES:
            tokens = resolve_tokens(mode, palette, blocks)
            for fg_name, bg_name, label in CONTRAST_PAIRS:
                fg = resolve_color(fg_name, tokens)
                bg = resolve_color(bg_name, tokens)
                if fg is None or bg is None:
                    results.append(
                        {
                            "mode": mode,
                            "palette": palette,
                            "label": label,
                            "fg": fg_name,
                            "bg": bg_name,
                            "ratio": 0.0,
                            "ok": False,
                            "missing": True,
                        }
                    )
                    continue
                ratio = contrast_ratio(fg, bg)
                results.append(
                    {
                        "mode": mode,
                        "palette": palette,
                        "label": label,
                        "fg": "#{:02x}{:02x}{:02x}".format(*fg),
                        "bg": "#{:02x}{:02x}{:02x}".format(*bg),
                        "ratio": round(ratio, 2),
                        "ok": ratio >= min_contrast,
                        "missing": False,
                    }
                )
    return results

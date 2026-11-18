import re
from pathlib import Path

from django.conf import settings

from core.theme import (
    CONTRAST_PAIRS,
    MODES,
    PALETTES,
    check_all,
    resolve_color,
    resolve_tokens,
)

COLOUR_LITERAL_RE = re.compile(
    r"(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|(?<![\w-])(?:red|blue|green|black|white|orange|purple|yellow)(?![\w-]))"
)
ALLOWED_FILES = {"theme.css"}


def test_every_palette_and_mode_passes_contrast():
    failures = [result for result in check_all() if not result["ok"]]
    assert not failures, failures


def test_contrast_matrix_is_complete():
    results = check_all()
    assert len(results) == len(MODES) * len(PALETTES) * len(CONTRAST_PAIRS)


def test_tokens_resolve_for_light_and_dark():
    for mode in MODES:
        tokens = resolve_tokens(mode, "ocean")
        assert resolve_color("text-1", tokens) is not None
        assert resolve_color("surface", tokens) is not None
        assert resolve_color("accent-soft", tokens) is not None


def _colour_literals(path: Path):
    text = path.read_text(encoding="utf-8")
    return [
        match.group(0)
        for match in COLOUR_LITERAL_RE.finditer(text)
        if not match.group(0).startswith("#main")
    ]


def test_no_hardcoded_colours_outside_theme_stylesheet():
    base = Path(settings.BASE_DIR)
    offenders = {}

    css_files = list((base / "static" / "css").glob("*.css"))
    for path in css_files:
        if path.name in ALLOWED_FILES:
            continue
        literals = _colour_literals(path)
        if literals:
            offenders[str(path.relative_to(base))] = literals

    for path in (base / "templates").rglob("*.html"):
        literals = _colour_literals(path)
        if literals:
            offenders[str(path.relative_to(base))] = literals

    for path in (base / "static" / "js").glob("*.js"):
        literals = _colour_literals(path)
        if literals:
            offenders[str(path.relative_to(base))] = literals

    assert not offenders, offenders

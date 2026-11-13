"""ui/vendor/tailwind.css is pre-built, so a Tailwind arbitrary-value class
(w-[340px], max-w-[280px], ...) that wasn't in it at build time silently does
nothing. The Runs list column lost its width that way and a long error message
stretched it past the window. Use an inline style for any value not built in."""
import re
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "ui"


def test_every_arbitrary_class_exists_in_the_vendored_css():
    css = (UI / "vendor" / "tailwind.css").read_text()
    html = (UI / "index.html").read_text()
    classes = " ".join(re.findall(r"class(?:Name)?\s*=\s*[\"']([^\"']*)", html))
    used = set(re.findall(r"(?<![\w-])([a-z][\w:/-]*-\[[^\]\s]+\])", classes))
    missing = sorted(c for c in used if "." + re.sub(r"([\[\]%.:/#(),])", r"\\\1", c) not in css)
    assert not missing, f"not in ui/vendor/tailwind.css (use style=...): {missing}"

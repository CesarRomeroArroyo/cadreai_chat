import re
import unicodedata

WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in normalized.splitlines()]
    return BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()

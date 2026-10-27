import re
import unicodedata


_PLURAL_ENDINGS = (
    ("ies", "y"),
    ("sses", "ss"),
    ("s", ""),
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [singularize(word) for word in text.split() if word]
    return " ".join(words)


def singularize(word: str) -> str:
    if len(word) <= 3:
        return word
    for suffix, replacement in _PLURAL_ENDINGS:
        if word.endswith(suffix):
            return word[: -len(suffix)] + replacement
    return word

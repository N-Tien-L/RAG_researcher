"""Text normalization helpers."""

import re
import unicodedata


def standardize_text(text: str) -> str:
    """Clean and standardize extracted text for downstream processing."""
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", normalized)
    normalized = re.sub(r"[‐‑‒–—―]", "-", normalized)
    normalized = re.sub(r"[''‚]", "'", normalized)
    normalized = re.sub(r"[""„]", '"', normalized)
    normalized = re.sub(r"\u00ad", "", normalized)
    normalized = re.sub(r"-\s*\n\s*", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = "".join(
        char
        for char in normalized
        if char == "\n" or char == "\t" or not unicodedata.category(char).startswith("C")
    )

    return normalized.strip()

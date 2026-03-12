"""Text normalization helpers."""

import re
import unicodedata


def standardize_text(text: str) -> str:
    """Normalise and clean extracted text for downstream embedding and chunking.

    Applies the following transformations in order:

    1. **NFKC Unicode normalisation** — decomposes compatibility characters.
    2. **Zero-width character removal** (U+200B through U+200D, U+FEFF).
    3. **Dash normalisation** — all Unicode dash variants mapped to ASCII ``-``.
    4. **Quotation-mark normalisation** — curly/typographic quotes to ASCII
       ``'`` and ``"``.
    5. **Soft-hyphen removal** (U+00AD).
    6. **Hyphenated line-break joining** — ``-\n`` sequences collapsed.
    7. **Consecutive space collapsing** — multiple spaces → single space
       (tabs preserved for indentation).
    8. **Trailing-space stripping** before newlines.
    9. **Excessive blank-line collapsing** — 3+ newlines → 2 newlines.
    10. **Control character removal** (except ``\n`` and ``\t``).
    11. **Strip leading/trailing whitespace**.

    Args:
        text: Raw text string from a PDF page or YouTube segment.

    Returns:
        str: Cleaned, normalised text string, or an empty string if
        ``text`` is falsy.
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", normalized)
    normalized = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015]", "-", normalized)
    normalized = re.sub(r"[\u2018\u2019\u201a]", "'", normalized)
    normalized = re.sub(r"[\u201c\u201d\u201e]", '"', normalized)
    normalized = re.sub(r"\u00ad", "", normalized)
    normalized = re.sub(r"-\s*\n\s*", "", normalized)
    # Collapse multiple spaces (but preserve tabs)
    normalized = re.sub(r" {2,}", " ", normalized)
    # Remove trailing spaces (but not tabs) before newlines
    normalized = re.sub(r" +\n", "\n", normalized)
    # Remove leading spaces (but not tabs) after newlines  - commented to preserve indentation
    # normalized = re.sub(r"\n +", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    # Remove control characters but keep newlines and tabs
    normalized = "".join(
        char
        for char in normalized
        if char == "\n" or char == "\t" or not unicodedata.category(char).startswith("C")
    )

    # Strip all trailing/leading whitespace
    return normalized.strip()

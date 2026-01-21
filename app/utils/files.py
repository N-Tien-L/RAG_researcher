"""File-related helper utilities."""

from pathlib import Path
from typing import Union


def ensure_directory(path: Union[str, Path]) -> Path:
    """Create directory if missing and return Path."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target

"""Time helpers."""


def format_seconds(seconds: float) -> str:
    """Return mm:ss formatted duration."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

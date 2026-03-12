"""Time formatting helpers for human-readable durations."""


def format_seconds(seconds: float) -> str:
    """Format a duration in seconds as ``mm:ss``.

    Args:
        seconds: Duration in seconds (non-negative float).

    Returns:
        str: Zero-padded duration string, e.g. ``"1:05"`` for 65 seconds.
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

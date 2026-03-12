"""Source loaders for ingestion (PDF, YouTube)."""

import re
from pathlib import Path
from typing import Dict, List, Optional

from pypdf import PdfReader
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)


class ExtractionError(Exception):
    """Base exception for content extraction failures.

    Subclassed by :class:`PDFExtractionError` and
    :class:`YouTubeExtractionError` to allow callers to catch either
    source-specific error or the common base.
    """


class PDFExtractionError(ExtractionError):
    """Raised when a PDF file cannot be read or parsed.

    Typical causes: file not found, wrong extension, corrupt PDF, or an
    unexpected error from ``pypdf.PdfReader``.
    """


class YouTubeExtractionError(ExtractionError):
    """Raised when a YouTube transcript cannot be fetched.

    Typical causes: invalid URL, transcripts disabled, video unavailable,
    or no transcript in the requested language.
    """


def extract_from_pdf(file_path: str) -> Dict[str, object]:
    """Extract full text and per-page text from a PDF file.

    Args:
        file_path: Absolute or relative path to the PDF file.

    Returns:
        dict: ``{"text": str, "page_texts": {page_num: str},
        "metadata": dict}``.
        ``metadata`` includes ``source``, ``source_type``, ``file_path``,
        ``page_count``, ``total_chars``, and optional PDF header fields
        (``title``, ``author``, ``creator``, ``subject``).

    Raises:
        PDFExtractionError: If the file does not exist, is not a PDF, or
            ``pypdf`` fails to parse it.
    """
    path = Path(file_path)
    if not path.exists():
        raise PDFExtractionError(f"File not found: {file_path}")
    if path.suffix.lower() != ".pdf":
        raise PDFExtractionError(f"Not a PDF file: {file_path}")

    try:
        reader = PdfReader(file_path)

        text_parts: List[str] = []
        page_texts: Dict[int, str] = {}

        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text:
                text_parts.append(text)
                page_texts[page_num] = text

        full_text = "\n\n".join(text_parts)

        metadata = {
            "source": path.name,
            "source_type": "pdf",
            "file_path": str(path.absolute()),
            "page_count": len(reader.pages),
            "total_chars": len(full_text),
        }

        if reader.metadata:
            for field in ("title", "author", "creator", "subject"):
                value = getattr(reader.metadata, field, None)
                if value:
                    metadata[field] = value

        return {
            "text": full_text,
            "page_texts": page_texts,
            "metadata": metadata,
        }

    except Exception as exc:
        raise PDFExtractionError(str(exc)) from exc


def _extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract the 11-character YouTube video ID from a URL or bare ID.

    Accepts:
    - Bare 11-char IDs (``"dQw4w9WgXcQ"``).
    - Standard watch URLs (``https://www.youtube.com/watch?v=…``).
    - Short URLs (``https://youtu.be/…``).
    - Embed URLs (``https://www.youtube.com/embed/…``).
    - URLs with extra query parameters.

    Args:
        url: YouTube URL or raw video ID string.

    Returns:
        str | None: The 11-character video ID, or ``None`` if not found.
    """
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url

    patterns = [
        r"(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com\/watch\?.*?v=([a-zA-Z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def extract_from_youtube(
    url: str,
    languages: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Fetch and return the auto-generated or manual transcript for a YouTube video.

    Args:
        url: YouTube watch URL or bare video ID.
        languages: Ordered list of BCP-47 language codes to try
            (default ``["en"]``).

    Returns:
        dict: ``{"text": str, "segments": list[dict],
        "metadata": dict}``.
        Each segment dict has ``"text"``, ``"start"``, and ``"duration"``
        keys.  ``metadata`` includes ``source_type``, ``video_id``,
        ``video_url``, ``language``, ``is_generated``,
        ``duration_seconds``, ``segment_count``, and ``total_chars``.

    Raises:
        YouTubeExtractionError: If the URL is invalid, the video is
            unavailable, transcripts are disabled, or no transcript
            exists in any of the requested languages.
    """
    languages = languages or ["en"]
    video_id = _extract_youtube_video_id(url)

    if not video_id:
        raise YouTubeExtractionError(f"Invalid YouTube URL: {url}")

    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=languages)
        transcript_data = fetched.to_raw_data()

    except TranscriptsDisabled:
        raise YouTubeExtractionError("Transcripts disabled")
    except VideoUnavailable:
        raise YouTubeExtractionError("Video unavailable")
    except NoTranscriptFound:
        raise YouTubeExtractionError("No transcript found")

    text_parts = [seg["text"] for seg in transcript_data]
    full_text = " ".join(text_parts)

    duration = 0
    if transcript_data:
        last = transcript_data[-1]
        duration = last.get("start", 0) + last.get("duration", 0)

    metadata = {
        "source": f"youtube:{video_id}",
        "source_type": "youtube",
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "language": fetched.language_code,
        "is_generated": fetched.is_generated,
        "duration_seconds": duration,
        "segment_count": len(transcript_data),
        "total_chars": len(full_text),
    }

    return {
        "text": full_text,
        "segments": transcript_data,
        "metadata": metadata,
    }

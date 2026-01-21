"""Extraction helpers for PDFs and YouTube transcripts."""

import re
from pathlib import Path
from typing import Dict, List, Optional

from pypdf import PdfReader
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable


class ExtractionError(Exception):
    """Base exception for extraction errors."""


class PDFExtractionError(ExtractionError):
    """Exception raised for PDF extraction errors."""


class YouTubeExtractionError(ExtractionError):
    """Exception raised for YouTube extraction errors."""


def extract_from_pdf(file_path: str) -> Dict[str, object]:
    """Extract text and metadata from a PDF file."""

    try:
        path = Path(file_path)
        if not path.exists():
            raise PDFExtractionError(f"File not found: {file_path}")

        if path.suffix.lower() != ".pdf":
            raise PDFExtractionError(f"File is not a PDF: {file_path}")

        reader = PdfReader(file_path)

        text_parts: List[str] = []
        page_texts: Dict[int, str] = {}

        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
                page_texts[page_num] = page_text

        full_text = "\n\n".join(text_parts)

        metadata: Dict[str, object] = {
            "source": path.name,
            "source_type": "pdf",
            "file_path": str(path.absolute()),
            "page_count": len(reader.pages),
            "total_chars": len(full_text),
        }

        if reader.metadata:
            if reader.metadata.title:
                metadata["title"] = reader.metadata.title
            if reader.metadata.author:
                metadata["author"] = reader.metadata.author
            if reader.metadata.creator:
                metadata["creator"] = reader.metadata.creator
            if reader.metadata.subject:
                metadata["subject"] = reader.metadata.subject

        return {"text": full_text, "metadata": metadata, "page_texts": page_texts}

    except PDFExtractionError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise PDFExtractionError(f"Failed to extract text from PDF: {exc}") from exc


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""

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


def extract_from_youtube(url: str, languages: Optional[List[str]] = None) -> Dict[str, object]:
    """Extract transcript and metadata from a YouTube video."""

    if languages is None:
        languages = ["en"]

    try:
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise YouTubeExtractionError(f"Could not extract video ID from URL: {url}")

        try:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=languages)
            transcript_data = fetched.to_raw_data()
            language_code = fetched.language_code
            is_generated = fetched.is_generated
        except TranscriptsDisabled:
            raise YouTubeExtractionError(f"Transcripts are disabled for video: {video_id}")
        except VideoUnavailable:
            raise YouTubeExtractionError(f"Video unavailable: {video_id}")
        except NoTranscriptFound:
            raise YouTubeExtractionError(f"No transcript found for video: {video_id}")

        text_parts = [segment["text"] for segment in transcript_data]
        full_text = " ".join(text_parts)

        duration = 0
        if transcript_data:
            last_segment = transcript_data[-1]
            duration = last_segment.get("start", 0) + last_segment.get("duration", 0)

        metadata = {
            "source": f"YouTube: {video_id}",
            "source_type": "youtube",
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "language": language_code,
            "is_generated": is_generated,
            "duration_seconds": duration,
            "segment_count": len(transcript_data),
            "total_chars": len(full_text),
        }

        return {"text": full_text, "metadata": metadata, "segments": transcript_data}

    except YouTubeExtractionError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise YouTubeExtractionError(f"Failed to extract transcript from YouTube: {exc}") from exc

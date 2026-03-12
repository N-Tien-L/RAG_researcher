"""File-related helper utilities."""

import uuid
from pathlib import Path
from typing import Optional, Union

from fastapi import UploadFile


def ensure_directory(path: Union[str, Path]) -> Path:
    """Create directory if missing and return Path."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def generate_unique_filename(original_name: str) -> str:
    suffix = Path(original_name).suffix or ".bin"
    return f"{uuid.uuid4().hex}{suffix}"


def validate_pdf_upload(file: UploadFile, max_bytes: int = 20 * 1024 * 1024) -> None:
    """Validate that the upload is a PDF and within size budget."""

    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are accepted")

    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise ValueError("Invalid content type for PDF upload")

    pos = file.file.tell()
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(pos)

    if size > max_bytes:
        raise ValueError("File exceeds maximum allowed size")


def save_upload_file(
    file: UploadFile,
    upload_dir: Union[str, Path],
    *,
    filename: Optional[str] = None,
) -> Path:
    ensure_directory(upload_dir)

    target_name = filename or generate_unique_filename(file.filename or "upload")
    target_path = Path(upload_dir) / target_name

    with target_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)

    return target_path

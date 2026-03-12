"""Tests for file utility functions."""

import io
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import UploadFile

from app.utils.files import (
    ensure_directory,
    generate_unique_filename,
    save_upload_file,
    validate_pdf_upload,
)


class TestValidatePDFUpload:
    """Tests for validate_pdf_upload function."""
    
    def test_validate_pdf_invalid_content_type(self):
        """Raises ValueError for invalid content type."""
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "test.pdf"
        mock_file.content_type = "text/plain"  # Invalid content type
        mock_file.file = MagicMock()
        mock_file.file.tell.return_value = 0
        mock_file.file.seek.side_effect = lambda *args: None
        
        with pytest.raises(ValueError, match="Invalid content type"):
            validate_pdf_upload(mock_file)
    
    def test_validate_pdf_file_too_large(self):
        """Raises ValueError when file exceeds size limit."""
        mock_file = Mock(spec=UploadFile)
        mock_file.filename = "test.pdf"
        mock_file.content_type = "application/pdf"
        
        # Mock file size to be larger than limit
        mock_file.file = MagicMock()
        mock_file.file.tell.return_value = 0
        
        # Simulate large file (30MB > 20MB default limit)
        large_size = 30 * 1024 * 1024
        mock_file.file.seek.side_effect = lambda pos, whence=0: None
        
        # First tell() returns 0, second tell() returns the file size
        tell_calls = [0, large_size]
        mock_file.file.tell.side_effect = lambda: tell_calls.pop(0)
        
        with pytest.raises(ValueError, match="exceeds maximum allowed size"):
            validate_pdf_upload(mock_file, max_bytes=20 * 1024 * 1024)


class TestEnsureDirectory:
    """Tests for ensure_directory."""

    def test_ensure_directory_creates_and_is_idempotent(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "new" / "nested"

        first_result = ensure_directory(target_dir)
        second_result = ensure_directory(target_dir)

        assert first_result == target_dir
        assert second_result == target_dir
        assert target_dir.is_dir()


class TestGenerateUniqueFilename:
    """Tests for generate_unique_filename."""

    def test_generate_unique_filename_preserves_extension_and_is_unique(self) -> None:
        first = generate_unique_filename("sample.txt")
        second = generate_unique_filename("sample.txt")

        assert first.endswith(".txt")
        assert second.endswith(".txt")
        assert first != second


class TestSaveUploadFile:
    """Tests for save_upload_file."""

    def test_save_upload_file_uses_provided_filename(self, tmp_path: Path) -> None:
        content = b"hello world"
        upload = Mock(spec=UploadFile)
        upload.filename = "input.txt"
        upload.file = io.BytesIO(content)

        output_path = save_upload_file(upload, tmp_path, filename="target.txt")

        assert output_path.name == "target.txt"
        assert output_path.read_bytes() == content

    def test_save_upload_file_generates_unique_name_when_missing(self, tmp_path: Path) -> None:
        content = b"generated content"
        upload = Mock(spec=UploadFile)
        upload.filename = "source.pdf"
        upload.file = io.BytesIO(content)

        with patch("app.utils.files.generate_unique_filename", return_value="generated.bin") as gen_name:
            output_path = save_upload_file(upload, tmp_path)

        gen_name.assert_called_once_with("source.pdf")
        assert output_path.name == "generated.bin"
        assert output_path.read_bytes() == content

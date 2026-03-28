"""Source management routes."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import schemas
from app.ingestion.loaders import _extract_youtube_video_id
from app.services.chat_service import ChatService
from app.services.exceptions import ServiceError
from app.services.source_service import SourceService
from app.utils.files import save_upload_file, validate_pdf_upload
from app.core.config import settings

router = APIRouter(prefix="/sources", tags=["sources"])


def _resolve_source_title(explicit_title: str | None, fallback_name: str) -> str:
    """Return a cleaned source title using explicit value or fallback."""
    if explicit_title and explicit_title.strip():
        return explicit_title.strip()
    return fallback_name


def _compute_upload_file_hash(file: UploadFile) -> str:
    """Compute SHA-256 hash for an uploaded file without changing stream position."""
    stream = file.file
    pos = stream.tell()
    stream.seek(0)

    digest = hashlib.sha256()
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)

    stream.seek(0)
    if pos != 0:
        stream.seek(pos)
    return digest.hexdigest()


async def _auto_link_if_requested(
    *,
    chat_service: ChatService,
    current_user: schemas.UserRead,
    source_id: UUID,
    chat_session_id: UUID | None,
) -> None:
    """Link a source to a chat session when chat context is provided."""
    if chat_session_id is None:
        return

    try:
        chat = await chat_service.get_chat_session(chat_session_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        ) from exc
    if chat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this chat",
        )

    await chat_service.link_source_to_chat(
        chat_session_id,
        source_id,
        ignore_existing=True,
    )


@router.post(
    "/upload",
    response_model=schemas.SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pdf_source(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
    chat_service: Annotated[ChatService, Depends(deps.chat_service)],
    title: Annotated[str | None, Form()] = None,
    chat_session_id: Annotated[UUID | None, Form()] = None,
) -> schemas.SourceRead:
    """Upload a PDF file and register it as a new source.

    Validates the upload, saves it to ``settings.UPLOAD_DIR``, then creates
    a ``Source`` record with ``status=processing`` pending the
    ``/{source_id}/process`` call.

    Args:
        file: Multipart PDF upload.  Must be ``application/pdf``; max 20 MB.
        title: Human-readable title for the source.
        current_user: Authenticated owner of the new source.
        service: Source service for database persistence.

    Returns:
        schemas.SourceRead: The newly created source record.

    Raises:
        HTTPException: 400 Bad Request if the file is not a valid PDF.
        HTTPException: 500 Internal Server Error if persistence fails.
    """
    try:
        validate_pdf_upload(file)
        content_hash = _compute_upload_file_hash(file)

        existing = await service.get_source_by_user_and_content_hash(
            user_id=current_user.id,
            content_hash=content_hash,
            source_type=schemas.SourceType.pdf,
        )
        if existing is not None:
            await _auto_link_if_requested(
                chat_service=chat_service,
                current_user=current_user,
                source_id=existing.id,
                chat_session_id=chat_session_id,
            )
            return existing

        saved_path = save_upload_file(file, settings.UPLOAD_DIR)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file upload",
        ) from exc

    inferred_title = _resolve_source_title(
        title,
        Path(file.filename or "Untitled PDF").stem,
    )

    source_in = schemas.SourceCreate(
        user_id=current_user.id,
        type=schemas.SourceType.pdf,
        title=inferred_title,
        source_uri=str(saved_path.absolute()),
        status=schemas.SourceStatus.processing,
        content_hash=content_hash,
    )

    try:
        created = await service.create_source(source_in)
        await _auto_link_if_requested(
            chat_service=chat_service,
            current_user=current_user,
            source_id=created.id,
            chat_session_id=chat_session_id,
        )
        return created
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create source",
        ) from exc


@router.post(
    "/youtube",
    response_model=schemas.SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_youtube_source(
    url: Annotated[str, Form(...)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
    chat_service: Annotated[ChatService, Depends(deps.chat_service)],
    title: Annotated[str | None, Form()] = None,
    chat_session_id: Annotated[UUID | None, Form()] = None,
) -> schemas.SourceRead:
    """Register a YouTube video as a new source.

    Extracts the ``video_id`` from the URL, then creates a ``Source`` record
    with ``status=processing`` pending the ``/{source_id}/process`` call.

    Args:
        url: Full YouTube watch URL (e.g. ``https://www.youtube.com/watch?v=…``).
        title: Human-readable title for the source.
        current_user: Authenticated owner of the new source.
        service: Source service for database persistence.

    Returns:
        schemas.SourceRead: The newly created source record.

    Raises:
        HTTPException: 400 Bad Request if the URL does not contain a valid YouTube video ID.
        HTTPException: 500 Internal Server Error if persistence fails.
    """
    video_id = _extract_youtube_video_id(url)
    if not video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid YouTube URL format",
        )

    inferred_title = _resolve_source_title(
        title,
        f"YouTube {video_id}",
    )

    existing = await service.get_youtube_source_by_user_and_external_id(
        user_id=current_user.id,
        external_id=video_id,
    )
    if existing is not None:
        await _auto_link_if_requested(
            chat_service=chat_service,
            current_user=current_user,
            source_id=existing.id,
            chat_session_id=chat_session_id,
        )
        return existing

    source_in = schemas.SourceCreate(
        user_id=current_user.id,
        type=schemas.SourceType.youtube,
        title=inferred_title,
        external_id=video_id,
        source_uri=url,
        status=schemas.SourceStatus.processing,
    )

    try:
        created = await service.create_source(source_in)
        await _auto_link_if_requested(
            chat_service=chat_service,
            current_user=current_user,
            source_id=created.id,
            chat_session_id=chat_session_id,
        )
        return created
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create source",
        ) from exc


@router.get(
    "/{source_id}",
    response_model=schemas.SourceRead,
)
async def get_source(
    source_id: UUID,
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
) -> schemas.SourceRead:
    """Retrieve a source by its ID.

    Args:
        source_id: UUID of the source to retrieve.
        current_user: Authenticated user; must be the source owner.
        service: Source service for database lookup.

    Returns:
        schemas.SourceRead: The requested source record.

    Raises:
        HTTPException: 404 Not Found if the source does not exist.
        HTTPException: 403 Forbidden if the caller is not the source owner.
    """
    try:
        source = await service.get_source(source_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        ) from exc

    if source.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this source",
        )

    return source


@router.get(
    "/",
    response_model=list[schemas.SourceRead],
)
async def list_sources(
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
    skip: int = 0,
    limit: int = 100,
) -> list[schemas.SourceRead]:
    """List all sources owned by the current user with offset pagination.

    Args:
        current_user: Authenticated user whose sources are listed.
        service: Source service for database query.
        skip: Number of records to skip (default 0).
        limit: Maximum number of records to return (default 100).

    Returns:
        list[schemas.SourceRead]: Paginated list of the user's sources.
    """
    return await service.list_sources_for_user(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/{source_id}/process",
    response_model=schemas.SourceProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_source(
    source_id: UUID,
    db: Annotated[AsyncSession, Depends(deps.db_session)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
) -> schemas.SourceProcessResponse:
    """Trigger content extraction, chunking, embedding, and vector-store ingestion.

    Implements *smart re-ingestion*: if the source content hash matches the
    previously stored hash, chunking and embedding are skipped and ``status``
    in the response will be ``'skipped'``.  Otherwise chunks are stored and
    ``status`` will be ``'ingested'``.

    Args:
        source_id: UUID of the source to process.
        db: Database session used to initialise ``IngestionApplicationService``.
        current_user: Authenticated user; must be the source owner.
        service: Source service for ownership verification and status refresh.

    Returns:
        schemas.SourceProcessResponse: Updated source record plus ingestion
        statistics (``chunks_added``, ``ids``,
        ``content_hash``, ``status``).

    Raises:
        HTTPException: 404 Not Found if the source does not exist.
        HTTPException: 403 Forbidden if the caller is not the source owner.
        HTTPException: 400 Bad Request if the source has no URI or external ID.
    """
    from app.applications.ingestion_application import IngestionApplicationService
    
    # Get and verify source ownership
    try:
        source = await service.get_source(source_id)
    except ServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        ) from exc
    
    if source.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to process this source",
        )
    
    # Validate source has required data
    ingestion_input = source.source_uri or source.external_id
    if not ingestion_input:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source has no URI or external ID to process",
        )
    
    # Determine stable source key
    source_key = source.source_key or source.external_id or source.source_uri or str(source.id)
    
    # Initialize ingestion service
    ingestion_app = IngestionApplicationService(db)
    
    # Process source and get ingestion stats
    result = await ingestion_app.process_source(
        source_id=str(source.id),
        source=ingestion_input,
        source_type=source.type,
        extra_metadata={
            "source_name": source.title,
            "source_uri": source.source_uri,
            "external_id": source.external_id,
        },
        source_uuid=str(source.id),
        source_key=source_key,
    )

    # Persist ingestion metadata in source table and refresh source state.
    await service.update_source_ingestion_metadata(
        source.id,
        content_hash=result["content_hash"],
        last_ingested_at=datetime.now(UTC),
    )
    updated_source = await service.get_source(source.id)

    # Return combined response with source details and ingestion stats
    return schemas.SourceProcessResponse(
        source=updated_source,
        chunks_added=result["chunks_added"],
        ids=result["ids"],
        content_hash=result["content_hash"],
        status=result["status"],
    )

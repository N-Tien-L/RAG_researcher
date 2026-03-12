"""Source management routes."""

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
from app.core.config import settings
from app.db import schemas
from app.ingestion.loaders import _extract_youtube_video_id
from app.services.exceptions import ServiceError
from app.services.source_service import SourceService
from app.utils.files import save_upload_file, validate_pdf_upload

router = APIRouter(prefix="/sources", tags=["sources"])


@router.post(
    "/upload",
    response_model=schemas.SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_pdf_source(
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str, Form(...)],
    collection_name: Annotated[str, Form(...)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
) -> schemas.SourceRead:
    """Upload a PDF file and register it as a new source.

    Validates the upload, saves it to ``settings.UPLOAD_DIR``, then creates
    a ``Source`` record with ``status=processing`` pending the
    ``/{source_id}/process`` call.

    Args:
        file: Multipart PDF upload.  Must be ``application/pdf``; max 20 MB.
        title: Human-readable title for the source.
        collection_name: Vector-store collection to index this source into.
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
        saved_path = save_upload_file(file, settings.UPLOAD_DIR)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file upload",
        ) from exc

    source_in = schemas.SourceCreate(
        user_id=current_user.id,
        type=schemas.SourceType.pdf,
        title=title,
        collection_name=collection_name,
        source_uri=str(saved_path.absolute()),
        status=schemas.SourceStatus.processing,
    )

    try:
        return await service.create_source(source_in)
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
    title: Annotated[str, Form(...)],
    collection_name: Annotated[str, Form(...)],
    current_user: Annotated[schemas.UserRead, Depends(deps.current_user)],
    service: Annotated[SourceService, Depends(deps.source_service)],
) -> schemas.SourceRead:
    """Register a YouTube video as a new source.

    Extracts the ``video_id`` from the URL, then creates a ``Source`` record
    with ``status=processing`` pending the ``/{source_id}/process`` call.

    Args:
        url: Full YouTube watch URL (e.g. ``https://www.youtube.com/watch?v=…``).
        title: Human-readable title for the source.
        collection_name: Vector-store collection to index this source into.
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

    source_in = schemas.SourceCreate(
        user_id=current_user.id,
        type=schemas.SourceType.youtube,
        title=title,
        collection_name=collection_name,
        external_id=video_id,
        source_uri=url,
        status=schemas.SourceStatus.processing,
    )

    try:
        return await service.create_source(source_in)
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
        statistics (``chunks_added``, ``collection``, ``ids``,
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
        collection_name=source.collection_name,
        extra_metadata={
            "source_name": source.title,
            "source_uri": source.source_uri,
            "external_id": source.external_id,
        },
        source_uuid=str(source.id),
        source_key=source_key,
    )

    # Refresh source to get updated status
    updated_source = await service.get_source(source.id)

    # Return combined response with source details and ingestion stats
    return schemas.SourceProcessResponse(
        source=updated_source,
        chunks_added=result["chunks_added"],
        collection=result["collection"],
        ids=result["ids"],
        content_hash=result["content_hash"],
        status=result["status"],
    )

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
    """Upload a PDF file as a source."""
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
    """Create a YouTube video source."""
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
    """Get source by ID."""
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
    """List sources for current user with pagination."""
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
    """Trigger processing/ingestion of a source.
    
    Extracts content, chunks it, generates embeddings, and stores in vector DB.
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

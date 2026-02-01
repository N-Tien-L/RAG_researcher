"""Chroma vector store helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import settings

_client: chromadb.PersistentClient | None = None
_collections: Dict[str, Collection] = {}

def init_chroma() -> None:
    global _client
    if _client is None:
        vector_db_path = Path(settings.VECTOR_STORAGE_PATH).as_posix()
        _client = chromadb.PersistentClient(vector_db_path)

def get_collection(collection_name: str) -> Collection:
    """Return (and cache) a Chroma collection for the given name."""
    if _client is None:
        raise RuntimeError("Chroma client is not initialized")

    if collection_name not in _collections:
        _collections[collection_name] = _client.get_or_create_collection(collection_name)
    return _collections[collection_name]
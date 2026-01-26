"""Chroma vector store helpers."""

from __future__ import annotations

from typing import Dict

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import get_db_path

_client: chromadb.PersistentClient | None = None
_collections: Dict[str, Collection] = {}


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        db_path = get_db_path().as_posix()
        _client = chromadb.PersistentClient(db_path)
    return _client


def get_collection(collection_name: str) -> Collection:
    """Return (and cache) a Chroma collection for the given name."""

    if collection_name not in _collections:
        client = _get_client()
        _collections[collection_name] = client.get_or_create_collection(collection_name)
    return _collections[collection_name]
"""Unit tests for Chroma helper utilities."""

from unittest.mock import MagicMock

import pytest

from app.vectorstore import chroma


@pytest.fixture(autouse=True)
def reset_chroma_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test runs with a clean cache."""

    monkeypatch.setattr(chroma, "_client", None)
    monkeypatch.setattr(chroma, "_collections", {})


def test_get_collection_initializes_client_and_caches_result(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_collection = MagicMock(name="collection")
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    monkeypatch.setattr(chroma, "_get_client", MagicMock(return_value=mock_client))

    first = chroma.get_collection("docs")
    second = chroma.get_collection("docs")

    assert first is second is mock_collection
    mock_client.get_or_create_collection.assert_called_once_with("docs")


def test_get_collection_keeps_distinct_entries_per_name(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    collections = {
        "alpha": MagicMock(name="collection_alpha"),
        "beta": MagicMock(name="collection_beta"),
    }
    mock_client.get_or_create_collection.side_effect = lambda name: collections[name]
    monkeypatch.setattr(chroma, "_get_client", MagicMock(return_value=mock_client))

    alpha_first = chroma.get_collection("alpha")
    beta_first = chroma.get_collection("beta")
    alpha_second = chroma.get_collection("alpha")
    beta_second = chroma.get_collection("beta")

    assert alpha_first is alpha_second is collections["alpha"]
    assert beta_first is beta_second is collections["beta"]
    assert mock_client.get_or_create_collection.call_count == 2

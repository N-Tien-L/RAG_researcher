"""Integration smoke test for Chroma persistence."""

import os
import unittest
from pathlib import Path

import chromadb

from app.core.config import settings

class TestChromaPersistence(unittest.TestCase):
    def test_persistence_round_trip(self) -> None:
        db_path = Path(settings.VECTOR_STORAGE_PATH).as_posix()
        client = chromadb.PersistentClient(db_path)
        collection = client.get_or_create_collection("test_connection")

        collection.add(
            documents=["This is document about Python", "This one about RAG"],
            metadatas=[{"source": "python_doc"}, {"source": "rag_doc"}],
            ids=["id1", "id2"],
        )

        result = collection.query(query_texts=["What are these documents about?"], n_results=1)
        self.assertTrue(result["documents"])
        self.assertTrue(os.path.exists(db_path))


if __name__ == "__main__":
    unittest.main()

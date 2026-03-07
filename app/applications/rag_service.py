"""Lightweight RAG service for answering questions over stored chunks."""

from typing import Dict, List, Optional

from langchain_community.chat_models import ChatOllama
from langchain_core.messages import AIMessage

from app.core.config import get_env
from app.embeddings.huggingface_tei import HuggingFaceTEIEmbedder
from app.rag.prompts.qa import qa_prompt
from app.rag.retrieval import retrieve_chunks


class RagService:
    """Wraps retrieval + LLM answering into a single callable."""

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k

        tei_url = get_env("TEI_URL", "http://localhost:8080")
        self.embedder = HuggingFaceTEIEmbedder(base_url=tei_url, mode="query")

        model = get_env("OLLAMA_MODEL", "llama3.2:3b") or "llama3.2:3b"
        base_url = get_env("OLLAMA_URL", "http://localhost:11434")
        temperature = float(get_env("OLLAMA_TEMPERATURE", "0.2") or "0.2")
        self.llm = ChatOllama(model=model, base_url=base_url, temperature=temperature)

    def answer(
        self,
        question: str,
        collection_name: str,
        where: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Return an answer string + chunk metadata for a user question."""

        query_embedding = self.embedder._embed([question], mode="query")[0]
        chunks = retrieve_chunks(
            embedding=query_embedding,
            collection_name=collection_name,
            top_k=self.top_k,
            where=where,
        )

        if not chunks:
            return {"answer": "I don't know.", "sources": []}

        context = "\n\n".join(f"[{idx + 1}] {chunk['text']}" for idx, chunk in enumerate(chunks))
        prompt = qa_prompt(context=context, question=question)

        response = self.llm.invoke(prompt)
        answer_text = response.content if isinstance(response, AIMessage) else str(response)

        return {
            "answer": answer_text.strip(),
            "sources": _serialize_sources(chunks),
        }


def _serialize_sources(chunks: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Keep only ids + metadata for downstream consumers."""

    return [
        {
            "chunk_id": chunk["id"],
            "metadata": chunk.get("metadata", {}),
        }
        for chunk in chunks
    ]

"""Error code documentation for API responses."""

ERROR_CODES = {
    # Ingestion errors — correspond to IngestionError(stage=...)
    "INGESTION_EXTRACTION": "Failed to extract content from source",
    "INGESTION_CHUNKING": "Failed to chunk extracted content",
    "INGESTION_UNKNOWN": "Unexpected error during ingestion",

    # Embedding errors — raised by HuggingFaceTEIEmbedder
    "EMBEDDING_GENERATION_FAILED": "Failed to generate embeddings",

    # Vector store errors — raised by pgvector_store helpers
    "VECTORSTORE_INSERT": "Failed to insert data into vector store",
    "VECTORSTORE_QUERY": "Failed to query vector store",
    "VECTORSTORE_DELETE": "Failed to delete data from vector store",

    # LLM errors — raised by RAGPipeline._generate_answer
    "LLM_GENERATION_FAILED": "Failed to generate response from LLM",
}

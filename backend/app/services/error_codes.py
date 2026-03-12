"""Error code documentation for API responses."""

ERROR_CODES = {
    # Ingestion errors
    "INGESTION_EXTRACTION": "Failed to extract content from source",
    "INGESTION_CHUNKING": "Failed to chunk extracted content",
    "INGESTION_UNKNOWN": "Unexpected error during ingestion",

    # Embedding errors
    "EMBEDDING_GENERATION_FAILED": "Failed to generate embeddings",

    # Vector store errors
    "VECTORSTORE_INSERT": "Failed to insert data into vector store",
    "VECTORSTORE_QUERY": "Failed to query vector store",
    "VECTORSTORE_DELETE": "Failed to delete data from vector store",

    # LLM errors
    "LLM_GENERATION_FAILED": "Failed to generate response from LLM",
}

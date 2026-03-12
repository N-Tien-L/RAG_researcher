# API Reference

## Authentication

All protected endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Obtain a token via `POST /api/auth/login`. The `OAuth2PasswordRequestForm` uses the `username` field to accept the user's **email address** (not a username). Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 60 minutes).

## Rate Limiting Headers

All responses include rate limit information:

| Header | Description |
|---|---|
| `X-RateLimit-Limit` | Maximum requests allowed in the window |
| `X-RateLimit-Remaining` | Requests remaining in the current window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |
| `Retry-After` | Seconds to wait (only present on 429 responses) |

## Error Response Format

All error responses follow this structure:

```json
{
  "error_code": "RESOURCE_NOT_FOUND",
  "message": "Human-readable description",
  "detail": "Technical detail string",
  "context": {"request_id": "uuid", "user_id": "uuid"},
  "details": {}
}
```

### Error Codes

| Code | HTTP Status | Description |
|---|---|---|
| `INGESTION_EXTRACTION` | 500 | Failed to extract content from source |
| `INGESTION_CHUNKING` | 500 | Failed to chunk extracted content |
| `INGESTION_UNKNOWN` | 500 | Unexpected error during ingestion |
| `EMBEDDING_GENERATION_FAILED` | 503 | Failed to generate embeddings |
| `VECTORSTORE_INSERT` | 503 | Failed to insert data into vector store |
| `VECTORSTORE_QUERY` | 503 | Failed to query vector store |
| `VECTORSTORE_DELETE` | 503 | Failed to delete data from vector store |
| `LLM_GENERATION_FAILED` | 503 | Failed to generate response from LLM |

## Endpoints

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | No | Authenticate and return JWT token |
| GET | `/api/auth/me` | Yes | Get current authenticated user |

**POST `/api/auth/login`**

Form fields (`application/x-www-form-urlencoded`):
- `username` — user's email address
- `password` — plain text password

Response: `Token`
```json
{"access_token": "eyJ...", "token_type": "bearer"}
```

---

### Users

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/users/` | No | Register new user |
| GET | `/api/users/{user_id}` | Yes | Get user by ID |
| GET | `/api/users/` | Yes | List users (paginated) |
| PATCH | `/api/users/{user_id}` | Yes | Update user fields |
| DELETE | `/api/users/{user_id}` | Yes | Delete user (204) |

**POST `/api/users/`** — Request body `UserCreate`:
```json
{"email": "user@example.com", "username": "alice", "password": "secret"}
```
Response `UserRead`: `201 Created`

Errors: `409 Conflict` if email or username already exists.

---

### Sources

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/sources/upload` | Yes | Upload PDF file |
| POST | `/api/sources/youtube` | Yes | Add YouTube video URL |
| GET | `/api/sources/{source_id}` | Yes | Get source by ID |
| GET | `/api/sources/` | Yes | List user's sources (paginated) |
| POST | `/api/sources/{source_id}/process` | Yes | Trigger ingestion |

**POST `/api/sources/upload`** — `multipart/form-data`:
- `file` — PDF binary (max 20 MB, `application/pdf`)
- `title` — display name
- `collection_name` — vector store namespace

Response `SourceRead`: `201 Created`. The `status` field starts as `processing`.

**POST `/api/sources/youtube`** — `application/x-www-form-urlencoded`:
- `url` — full YouTube URL or 11-character video ID
- `title` — display name
- `collection_name` — vector store namespace

Response `SourceRead`: `201 Created`.

**POST `/api/sources/{source_id}/process`** — Triggers ingestion pipeline.

Response `SourceProcessResponse`:
```json
{
  "source": { ... },
  "chunks_added": 42,
  "collection": "documents",
  "ids": ["src-chunk-0", "src-chunk-1"],
  "content_hash": "abc123...",
  "status": "ingested"
}
```
`status` is `"ingested"` for new/modified sources, `"skipped"` if content hash is unchanged.

---

### Chats

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/chats/` | Yes | Create chat session |
| GET | `/api/chats/{chat_session_id}` | Yes | Get chat session |
| GET | `/api/chats/` | Yes | List user's chat sessions |
| POST | `/api/chats/{chat_session_id}/sources/{source_id}` | Yes | Link source to chat |

All chat endpoints enforce ownership — `403 Forbidden` is returned if `user_id` does not match the authenticated user.

**POST `/api/chats/`** — Request body `ChatSessionCreate`:
```json
{"user_id": "uuid", "title": "My research", "collections": ["documents"]}
```

---

### Messages

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/messages/send` | Yes | Send message, get AI response |
| GET | `/api/messages/{chat_id}/history` | Yes | Get chat history (ascending) |

**POST `/api/messages/send`** — Request body:
```json
{
  "chat_id": "uuid",
  "content": "What is RAG?",
  "use_rag": true,
  "collection_name": "documents"
}
```

When `use_rag=true`, the assistant response is generated via the RAG pipeline with chat history context. When `use_rag=false`, only the user message is saved (no AI response).

Response `SendMessageResponse`:
```json
{
  "user_message": { ... },
  "assistant_message": { ... },
  "sources": [{"chunk_id": "...", "metadata": {...}}]
}
```

**GET `/api/messages/{chat_id}/history`** — Returns messages ordered ascending by `created_at`.

---

### RAG

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/rag/query` | Yes | Direct RAG query |

**POST `/api/rag/query`** — Request body `RAGQueryRequest`:
```json
{
  "question": "What is retrieval-augmented generation?",
  "collection_name": "documents",
  "source_id": null
}
```

- `source_id` — optional; filters retrieval to a single source

Response `RAGQueryResponse`:
```json
{
  "answer": "RAG is ...",
  "sources": [{"chunk_id": "...", "metadata": {...}}]
}
```

Errors: `503 Service Unavailable` if TEI, vector store, or LLM is unavailable.

---

### System

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Health check |
| GET | `/metrics` | No | Prometheus metrics |
| GET | `/cache/stats` | Yes | Cache statistics |
| POST | `/cache/clear` | Yes | Clear cache by type |

**GET `/health`** — Returns `{"status": "ok"}`.

**GET `/metrics`** — Returns Prometheus text format.

**POST `/cache/clear`** — Query param `cache_type`: `embeddings`, `llm`, or `all`.

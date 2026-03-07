
-- 1. Check the source and its status
SELECT id, title, status, collection_name, content_hash, source_uri, last_ingested_at
FROM sources
WHERE id = '37a36c6d-a58c-4561-aeed-7b4cb992a53a';

-- 2. Count chunks stored for this source
SELECT COUNT(*) AS chunks_count, collection_name
FROM document_chunks
WHERE source_id = '37a36c6d-a58c-4561-aeed-7b4cb992a53a'
GROUP BY collection_name;

-- 3. Preview first 3 chunks (verify content looks correct)
SELECT chunk_id, LEFT(content, 150) AS preview, collection_name
FROM document_chunks
WHERE source_id = '37a36c6d-a58c-4561-aeed-7b4cb992a53a'
ORDER BY chunk_id
LIMIT 3;

SELECT * FROM chat_sessions;

SELECT * FROM chat_session_sources;

-- 4. Check your chat session
SELECT id, title, user_id, created_at
FROM chat_sessions
WHERE user_id = '0fffbfed-ce8d-4e14-b185-1fa7ea4e14c3'
ORDER BY created_at DESC;

-- 5. Check if source is linked to the chat  ← KEY CHECK
SELECT css.chat_session_id, css.source_id, css.created_at
FROM chat_session_sources css
WHERE css.chat_session_id = '491dadae-f9ea-4217-a5d9-2fc0c2a7d00a';
-- If this returns 0 rows → source is NOT linked → RAG will return nothing

-- 6. Check messages in the chat
SELECT id, role, LEFT(content, 200) AS content, created_at
FROM chat_messages
WHERE chat_id = '491dadae-f9ea-4217-a5d9-2fc0c2a7d00a'
ORDER BY created_at ASC;

-- 7. Full picture: chat → linked sources → chunk count
SELECT
    cs.id           AS chat_id,
    cs.title        AS chat_title,
    s.id            AS source_id,
    s.title         AS source_title,
    s.status        AS source_status,
    s.collection_name,
    COUNT(dc.id)    AS chunk_count
FROM chat_sessions cs
LEFT JOIN chat_session_sources css ON css.chat_session_id = cs.id
LEFT JOIN sources s                ON s.id = css.source_id
LEFT JOIN document_chunks dc       ON dc.source_id = s.id::text
WHERE cs.user_id = '0fffbfed-ce8d-4e14-b185-1fa7ea4e14c3'
GROUP BY cs.id, cs.title, s.id, s.title, s.status, s.collection_name
ORDER BY cs.created_at DESC;
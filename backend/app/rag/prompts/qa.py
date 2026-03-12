"""Q&A prompt templates with versioning."""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Version 1: Basic Q&A with context
QA_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful AI assistant. Answer the user's question using ONLY the context provided below.
    
IMPORTANT RULES:
- Only use information from the context
- If the answer is not in the context, respond with "I don't know"
- Be concise and accurate
- Cite specific parts of the context when possible

Context:
{context}"""),
    ("human", "{question}"),
])

# Metadata for tracking
QA_PROMPT_V1.metadata = {
    "version": "1.0",
    "purpose": "Basic Q&A with context grounding",
    "required_inputs": ["context", "question"],
    "created_at": "2026-02-04",
}

# Version 2: Conversational Q&A with chat history
QA_CONVERSATIONAL_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful AI assistant engaged in a conversation.
    
USE THE CONTEXT:
{context}

Answer the user's question based on the context and conversation history.
If you don't know, say "I don't know"."""),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{question}"),
])

QA_CONVERSATIONAL_PROMPT_V1.metadata = {
    "version": "1.0",
    "purpose": "Conversational Q&A with context and history",
    "required_inputs": ["context", "question"],
    "optional_inputs": ["chat_history"],
    "created_at": "2026-02-04",
}

# Helper function for backwards compatibility
def qa_prompt(context: str, question: str) -> str:
    """Legacy helper - deprecated, use QA_PROMPT_V1 directly."""
    messages = QA_PROMPT_V1.format_messages(context=context, question=question)
    return "\n".join([msg.content for msg in messages])
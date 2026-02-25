"""Tests for RAG prompts."""

import pytest

from app.rag.prompts.qa import qa_prompt, QA_PROMPT_V1


class TestQAPrompt:
    """Tests for QA prompt templates."""
    
    def test_qa_prompt_legacy_helper(self):
        """Legacy qa_prompt helper works correctly."""
        context = "Python is a programming language."
        question = "What is Python?"
        
        result = qa_prompt(context=context, question=question)
        
        assert isinstance(result, str)
        assert "Python" in result
        assert "programming language" in result
    
    def test_qa_prompt_v1_template(self):
        """QA_PROMPT_V1 template formats correctly."""
        messages = QA_PROMPT_V1.format_messages(
            context="Test context",
            question="Test question"
        )
        
        assert len(messages) >= 1
        assert any("Test context" in msg.content for msg in messages)

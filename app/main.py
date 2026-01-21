"""Streamlit entrypoint for testing the ingestion pipeline."""

import tempfile
from pathlib import Path

import streamlit as st

from ingestion.ingest import (
    PDFExtractionError,
    YouTubeExtractionError,
    extract_from_pdf,
    extract_from_youtube,
)
from rag.pipeline import RagPipeline
from utils.text import standardize_text


def main() -> None:
    st.set_page_config(
        page_title="Data Ingestion Test",
        page_icon="📥",
        layout="wide",
    )

    st.title("📥 Data Ingestion Pipeline Test")
    st.markdown("Test PDF and YouTube video extraction with text standardization")

    # Initialize RAG pipeline for chunking
    pipeline = RagPipeline(max_tokens=300, overlap=40)

    tab1, tab2 = st.tabs(["📄 PDF Upload", "🎥 YouTube Video"])

    with tab1:
        st.header("PDF File Extraction")

        uploaded_file = st.file_uploader(
            "Upload a PDF file",
            type=["pdf"],
            help="Upload a PDF file to extract text",
        )

        if uploaded_file is not None:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.read())
                tmp_path = tmp_file.name

            try:
                with st.spinner("Extracting text from PDF..."):
                    result = extract_from_pdf(tmp_path)

                st.success("✅ Text extracted successfully!")

                st.subheader("📋 Metadata")
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Pages", result["metadata"].get("page_count", "N/A"))
                with col2:
                    st.metric("Characters", result["metadata"].get("total_chars", "N/A"))
                with col3:
                    st.metric("Source Type", result["metadata"].get("source_type", "N/A"))

                with st.expander("View Full Metadata"):
                    st.json(result["metadata"])

                st.subheader("📝 Raw Extracted Text")
                raw_text = result["text"]
                st.text_area(
                    "Raw text (first 2000 characters)",
                    raw_text[:2000] + ("..." if len(raw_text) > 2000 else ""),
                    height=200,
                    disabled=True,
                )

                st.subheader("✨ Standardized Text")
                with st.spinner("Standardizing text..."):
                    standardized = standardize_text(raw_text)

                st.text_area(
                    "Standardized text (first 2000 characters)",
                    standardized[:2000] + ("..." if len(standardized) > 2000 else ""),
                    height=200,
                    disabled=True,
                )

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Original Length", len(raw_text))
                with col2:
                    reduction = len(raw_text) - len(standardized)
                    st.metric("Cleaned Length", len(standardized), delta=f"-{reduction} chars")

                st.subheader("🔪 Chunking Preview")
                chunks = pipeline.prepare_document(result)
                st.caption(f"Generated {len(chunks)} chunks (showing first 3)")
                for idx, chunk in enumerate(chunks[:3]):
                    st.text_area(
                        f"Chunk {idx}",
                        chunk["text"],
                        height=150,
                        disabled=True,
                    )

                if "page_texts" in result and result["page_texts"]:
                    with st.expander("📄 View Text by Page"):
                        page_num = st.selectbox(
                            "Select Page",
                            options=list(result["page_texts"].keys()),
                            format_func=lambda x: f"Page {x}",
                        )
                        if page_num:
                            st.text_area(
                                f"Page {page_num} Content",
                                result["page_texts"][page_num],
                                height=300,
                                disabled=True,
                            )

            except PDFExtractionError as exc:
                st.error(f"❌ PDF Extraction Error: {exc}")
            except Exception as exc:  # pragma: no cover - safety net for UI
                st.error(f"❌ Unexpected Error: {exc}")
            finally:
                Path(tmp_path).unlink(missing_ok=True)

    with tab2:
        st.header("YouTube Video Transcript Extraction")

        youtube_url = st.text_input(
            "YouTube URL or Video ID",
            placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ or dQw4w9WgXcQ",
            help="Enter a YouTube video URL or video ID",
        )

        col1, col2 = st.columns([3, 1])
        with col1:
            languages = st.text_input(
                "Preferred Languages (comma-separated)",
                value="en",
                help="Language codes to try, e.g., 'en,es,fr'",
            )
        with col2:
            extract_button = st.button("Extract Transcript", type="primary", use_container_width=True)

        if youtube_url and extract_button:
            lang_list = [lang.strip() for lang in languages.split(",") if lang.strip()]

            try:
                with st.spinner("Fetching transcript from YouTube..."):
                    result = extract_from_youtube(youtube_url, languages=lang_list)

                st.success("✅ Transcript extracted successfully!")

                st.subheader("📋 Metadata")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Video ID", result["metadata"].get("video_id", "N/A"))
                with col2:
                    duration = result["metadata"].get("duration_seconds", 0)
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    st.metric("Duration", f"{minutes}:{seconds:02d}")
                with col3:
                    st.metric("Language", result["metadata"].get("language", "N/A"))
                with col4:
                    st.metric("Segments", result["metadata"].get("segment_count", "N/A"))

                with st.expander("View Full Metadata"):
                    st.json(result["metadata"])

                if "video_id" in result["metadata"]:
                    with st.expander("🎬 Video Preview"):
                        st.video(result["metadata"]["video_url"])

                st.subheader("📝 Raw Transcript")
                raw_text = result["text"]
                st.text_area(
                    "Raw transcript (first 2000 characters)",
                    raw_text[:2000] + ("..." if len(raw_text) > 2000 else ""),
                    height=200,
                    disabled=True,
                )

                st.subheader("✨ Standardized Transcript")
                with st.spinner("Standardizing text..."):
                    standardized = standardize_text(raw_text)

                st.text_area(
                    "Standardized transcript (first 2000 characters)",
                    standardized[:2000] + ("..." if len(standardized) > 2000 else ""),
                    height=200,
                    disabled=True,
                )

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Original Length", len(raw_text))
                with col2:
                    reduction = len(raw_text) - len(standardized)
                    st.metric("Cleaned Length", len(standardized), delta=f"-{reduction} chars")

                st.subheader("🔪 Chunking Preview")
                chunks = pipeline.prepare_document(result)
                st.caption(f"Generated {len(chunks)} chunks (showing first 3)")
                for idx, chunk in enumerate(chunks[:3]):
                    st.text_area(
                        f"Chunk {idx}",
                        chunk["text"],
                        height=150,
                        disabled=True,
                    )

                if "segments" in result and result["segments"]:
                    with st.expander("⏱️ View Transcript Segments"):
                        num_segments = len(result["segments"])
                        st.info(f"Showing first 20 of {num_segments} segments")

                        for segment in result["segments"][:20]:
                            start = segment.get("start", 0)
                            duration = segment.get("duration", 0)
                            text = segment.get("text", "")

                            minutes = int(start // 60)
                            seconds = int(start % 60)
                            timestamp = f"{minutes}:{seconds:02d}"

                            st.text(f"[{timestamp}] {text}")

            except YouTubeExtractionError as exc:
                st.error(f"❌ YouTube Extraction Error: {exc}")
            except Exception as exc:  # pragma: no cover - safety net for UI
                st.error(f"❌ Unexpected Error: {exc}")

    with st.sidebar:
        st.header("ℹ️ About")
        st.markdown(
            """
        This test application demonstrates the data ingestion pipeline:

        **Features:**
        - 📄 PDF text extraction with metadata
        - 🎥 YouTube transcript extraction
        - ✨ Text standardization and cleaning
        - 📊 Metadata display
        - 📈 Statistics and analytics

        **Extraction Process:**
        1. Extract raw text/transcript
        2. Capture metadata
        3. Standardize and clean text
        4. Display results

        **Next Steps:**
        - Chunking
        - Embedding generation
        - Vector storage in ChromaDB
        """
        )

        st.header("🛠️ Settings")
        st.markdown(
            """
        **Supported Formats:**
        - PDF files
        - YouTube videos (with transcripts)

        **Languages:**
        Multiple language transcripts supported.
        Use ISO 639-1 language codes.
        """
        )


if __name__ == "__main__":
    main()

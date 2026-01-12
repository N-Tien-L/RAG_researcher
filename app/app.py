import streamlit as st
import requests
import os

st.title("Docker-to-Ollama Connection Test")

# Get the URL from the environment variable we set in docker-compose
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

st.write(f"Attempting to connect to Ollama at: `{ollama_url}`")

if st.button("Check Connection"):
    try:
        # Ask Ollama for its version/tags
        response = requests.get(f"{ollama_url}/api/tags")
        if response.status_code == 200:
            st.success("✅ Success! The container can see Ollama.")
            st.json(response.json()) # Shows what models you have pulled
        else:
            st.error(f"❌ Ollama is there but returned error: {response.status_code}")
    except Exception as e:
        st.error(f"❌ Connection Failed. Error: {e}")
        st.info("Tip: Make sure Ollama is running on your Ubuntu host!")
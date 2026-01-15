import os
import chromadb
import dotenv

dotenv.load_dotenv()

def test_connection():

    db_path = dotenv.get_key(".env", "DB_PATH")

    print(f"-- Initializing ChromaDB at: {db_path}")

    # Initialize ChromaDB client
    client = chromadb.PersistentClient(db_path)
    
    # Create or get a Collection
    collection = client.get_or_create_collection("test_connection")

    # Try to add data to the collection
    print("--- Inserting test data ---")
    collection.add(
        documents=["This is document about Python", "This one about RAG"],
        metadatas=[{"source": "python_doc"}, {"source": "rag_doc"}],
        ids=["id1", "id2"]
    )

    # try to query them
    print("--- Querying ---")
    result = collection.query(
        query_texts=["What are these documents about?"],
        n_results=1
    )

    print("--- Query result ---")
    print(result["documents"])

    if os.path.exists(db_path):
        print(f"\nSuccess! Data have been saved in folder: {db_path}")
    else:
        print("\nError! The folder can't be found")

if __name__ == "__main__":
    test_connection()
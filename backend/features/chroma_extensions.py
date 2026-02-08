import chromadb
from .chroma_utils import get_collection, DEFAULT_CHROMA_DIR, DEFAULT_COLLECTION_NAME

def delete_document_from_chroma(doc_name: str, chroma_dir: str = DEFAULT_CHROMA_DIR, collection_name: str = DEFAULT_COLLECTION_NAME):
    """
    Deletes all chunks associated with a specific document from ChromaDB.
    """
    try:
        col = get_collection(chroma_dir, collection_name)
        # Delete by metadata "doc" matching doc_name
        col.delete(where={"doc": doc_name})
        return True
    except Exception as e:
        print(f"Error deleting doc '{doc_name}': {e}")
        return False

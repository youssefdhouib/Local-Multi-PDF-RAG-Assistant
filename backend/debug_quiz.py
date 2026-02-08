
import sys
import os
import logging

# Ensure we can import local modules
sys.path.append(os.getcwd())

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("debug_quiz")

try:
    print("--- IMPORTING MODULES ---")
    from features.chroma_utils import list_docs, fetch_doc_chunks, get_collection
    from features.mcq_generator import generate_mcqs_for_document
    print("✅ Modules imported successfully.")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("Make sure you are running this from 'd:/PycharmProjects/Local_Multi-PDF_RAG_Assistant/PDF processing/'")
    sys.exit(1)

def main():
    print("\n--- 1. CHECKING CHROMADB ---")
    try:
        docs = list_docs()
        print(f"found {len(docs)} documents in ChromaDB:")
        for d in docs:
            print(f" - {d}")
        
        if not docs:
            print("❌ No documents found in ChromaDB. Cannot generate quiz.")
            return

        target_doc = docs[0]
        print(f"\n--- 2. FETCHING CHUNKS FOR '{target_doc}' ---")
        chunks = fetch_doc_chunks(target_doc)
        print(f"Found {len(chunks)} chunks.")
        
        if not chunks:
            print("❌ fetch_doc_chunks returned 0 items. Checking why...")
            # Debug retrieval
            col = get_collection()
            data = col.get(where={"doc": target_doc})
            print(f"Raw query for doc='{target_doc}' returned {len(data['ids'])} ids.")
            
            # Check if maybe filename encoding is issue
            all_meta = col.get()["metadatas"]
            print(f"First 5 metadata entries in DB: {all_meta[:5]}")
            return

        print(f"Sample chunk text: {chunks[0]['text'][:100]}...")

        print(f"\n--- 3. GENERATING QUIZ FOR '{target_doc}' ---")
        print("Sending request to Ollama... (this may take 10-20s)")
        mcqs = generate_mcqs_for_document(target_doc, n=3)
        
        if not mcqs:
            print("❌ generate_mcqs_for_document returned INVALID/EMPTY result.")
        else:
            print(f"✅ Success! Generated {len(mcqs)} questions.")
            for i, q in enumerate(mcqs):
                print(f"Q{i+1}: {q.question}")
                print(f"    Options: {q.options}")
                print(f"    Ans: {q.options[q.correct_index] if q.correct_index is not None else 'None'}")

    except Exception as e:
        logger.exception("Diagnostic failed with error")

if __name__ == "__main__":
    main()

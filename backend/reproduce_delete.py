
import json
from pathlib import Path
from ingest.service import ingest_service

def test_delete():
    doc_name = "test_delete_artifact.pdf"
    
    # 1. Setup: Create dummy file
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    file_path = data_dir / doc_name
    file_path.touch()
    print(f"Created dummy file: {file_path}")

    # 2. Setup: Add to registry
    ingest_service.update_status(doc_name, "ready", test="true")
    print(f"Added {doc_name} to registry")

    # 3. Verify it's there
    reg = ingest_service.get_all_docs()
    if doc_name not in reg:
        print("❌ Setup failed: Document not found in registry")
        return

    # 4. Execute Delete
    print("Executing delete_doc...")
    try:
        current_docs_count = len(reg)
        success = ingest_service.delete_doc(doc_name)
        
        if not success:
             print("❌ delete_doc returned False")
    except Exception as e:
        print(f"❌ Exception during delete_doc: {e}")
        return

    # 5. Verification
    # Check Registry
    reg_after = ingest_service.get_all_docs()
    if doc_name in reg_after:
        print("❌ Verification failed: Document still in registry")
    else:
        print("✅ Registry cleared")

    # Check File
    if file_path.exists():
        print("❌ Verification failed: File still exists on disk")
    else:
        print("✅ File deleted from disk")

if __name__ == "__main__":
    test_delete()

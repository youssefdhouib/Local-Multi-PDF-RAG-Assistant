import json
from pathlib import Path
import threading

REGISTRY_FILE = Path("storage/registry.json")
registry_lock = threading.Lock()

def test_registry_operations():
    print("Testing registry operations...")
    
    # Test 1: Load registry
    print("\n1. Loading registry...")
    with registry_lock:
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, "r") as f:
                reg = json.load(f)
                print(f"   Loaded {len(reg)} documents")
        else:
            reg = {}
            print("   Registry file doesn't exist")
    
    # Test 2: Add a test entry
    print("\n2. Adding test entry...")
    test_doc = "test_simple.pdf"
    with registry_lock:
        reg[test_doc] = {"name": test_doc, "status": "ready", "test": True}
        with open(REGISTRY_FILE, "w") as f:
            json.dump(reg, f, indent=2)
        print(f"   Added {test_doc}")
    
    # Test 3: Delete the test entry
    print("\n3. Deleting test entry...")
    with registry_lock:
        with open(REGISTRY_FILE, "r") as f:
            reg = json.load(f)
        
        if test_doc in reg:
            del reg[test_doc]
            print(f"   Deleted {test_doc} from dict")
            
            with open(REGISTRY_FILE, "w") as f:
                json.dump(reg, f, indent=2)
            print(f"   Saved registry")
        else:
            print(f"   {test_doc} not found")
    
    print("\n✅ All registry operations completed successfully")

if __name__ == "__main__":
    test_registry_operations()

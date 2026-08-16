import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_DIR = "storage/chroma_db"
COLLECTION_NAME = "pdf_chunks"

model = SentenceTransformer("all-MiniLM-L6-v2")


def print_results(title, results, max_chars=300):
    print(f"\n{title}\n" + "-" * len(title))
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results.get("distances", [[None] * len(docs)])[0]

    for i, (text, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        print(
            f"\n#{i}  {meta['doc']} | page {meta['page']} "
            f"| chunk {meta['chunk_index']} | dist={dist:.4f}"
        )
        print(text[:max_chars].replace("\n", " "), "...")


def run_query(collection, query, where=None):
    q_emb = model.encode(query, normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=[q_emb],
        n_results=3,
        where=where,
        include=["documents", "metadatas", "distances"]
    )

    scope = "ALL PDFs" if where is None else f"FILTERED {where}"
    print_results(f"🔍 Query: {query} ({scope})", results)


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION_NAME)

    # ✅ Queries that REALLY exist in the document
    queries = [
        "Qu’est-ce que la recherche gourmande ?",
        "Définir une heuristique admissible",
        "Expliquer l’algorithme A*",
        "Qu’est-ce qu’un espace d’états en IA ?",
    ]

    for q in queries:
        # All PDFs
        run_query(collection, q)

        # Filtered to AI course only
        run_query(
            collection,
            q,
            where={"doc": "CoursIA-3-1.pdf"}
        )


if __name__ == "__main__":
    main()

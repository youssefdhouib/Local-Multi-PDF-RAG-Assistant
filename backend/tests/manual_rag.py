from rag_answer import rag_answer

def print_citations(evidence):
    print("\nCitations (for UI panel):")
    for i, e in enumerate(evidence, start=1):
        print(f"- [E{i}] {e.doc} | page {e.page} | chunk {e.chunk_index} | dist={e.distance:.4f}")

def main():
    q = "Qu’est-ce que la recherche gourmande ?"

    answer, evidence = rag_answer(
        question=q,
        top_k=6,
        use_top_n_in_prompt=3,           # only top 3 used by LLM (clean citations)
        where={"doc": "CoursIA-3-1.pdf"}, # filter to the AI course
        max_distance=0.75,
        ollama_model="llama3.2"
    )

    print("\nQUESTION:", q)
    print("\nANSWER:\n", answer)
    print_citations(evidence)

if __name__ == "__main__":
    main()

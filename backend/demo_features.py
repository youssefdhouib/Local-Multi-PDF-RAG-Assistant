from features.chroma_utils import list_docs
from features.summarize import summarize_document, summarize_library
from features.mcq_generator import generate_mcqs_for_document
from features.export_utils import save_markdown, export_pdf_simple, build_mcq_markdown


def main():
    docs = list_docs()
    print("Docs in Chroma:", docs)

    if not docs:
        print("❌ No documents in Chroma. Run Step 6 first (run_chroma.py).")
        return

    # Pick first doc for demo
    doc = docs[0]

    # ---- Step 8: Summary (single doc)
    s = summarize_document(doc_name=doc, max_chunks=35)
    print("\n--- SUMMARY (single doc) ---\n")
    print(s.markdown[:800], "\n...")

    md_path = save_markdown(s.markdown, "storage/exports/summary_doc.md")
    pdf_path = export_pdf_simple(s.markdown, "storage/exports/summary_doc.pdf", title=s.title)
    print("✅ Exported:", md_path)
    print("✅ Exported:", pdf_path)

    # ---- Step 8: Summary (library)
    s2 = summarize_library(per_doc=10)
    md_path2 = save_markdown(s2.markdown, "storage/exports/summary_library.md")
    pdf_path2 = export_pdf_simple(s2.markdown, "storage/exports/summary_library.pdf", title=s2.title)
    print("✅ Exported:", md_path2)
    print("✅ Exported:", pdf_path2)

    # ---- Step 9: MCQ (single doc)
    mcqs = generate_mcqs_for_document(doc_name=doc, n=5, max_chunks=45)
    if not mcqs:
        print("⚠️ MCQ generation returned empty (try increasing max_chunks or use another doc).")
        return

    quiz_md = build_mcq_markdown(mcqs, title=f"MCQ Quiz — {doc}")
    md_path3 = save_markdown(quiz_md, "storage/exports/quiz.md")
    pdf_path3 = export_pdf_simple(quiz_md, "storage/exports/quiz.pdf", title=f"MCQ Quiz — {doc}")
    print("✅ Exported:", md_path3)
    print("✅ Exported:", pdf_path3)

    print("\nDONE ✅")


if __name__ == "__main__":
    main()

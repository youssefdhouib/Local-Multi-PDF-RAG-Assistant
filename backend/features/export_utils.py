from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm


def save_markdown(md_text: str, out_path: str) -> str:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md_text, encoding="utf-8")
    return str(p.resolve())


def _wrap_text(text: str, width_chars: int = 110) -> List[str]:
    """
    Simple word-wrap for PDF rendering.
    """
    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.rstrip()
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split()
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 <= width_chars:
                cur = (cur + " " + w).strip()
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def export_pdf_simple(md_text: str, out_path: str, title: str = "Report") -> str:
    """
    Very reliable PDF export for personal projects.
    Renders markdown as plain text (headings look like headings by stripping '#').
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(p), pagesize=A4)
    width, height = A4

    x = 2 * cm
    y = height - 2 * cm
    line_height = 14

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 2 * cm

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, title)
    y -= 24
    c.setFont("Helvetica", 11)

    # Convert markdown-ish to readable text
    # Keep it simple and robust: remove markdown symbols
    plain = md_text
    plain = re.sub(r"^#{1,6}\s*", "", plain, flags=re.MULTILINE)  # headings
    plain = plain.replace("**", "").replace("*", "")
    plain = plain.replace("`", "")

    lines = _wrap_text(plain, width_chars=110)

    for line in lines:
        if y < 2 * cm:
            new_page()
            c.setFont("Helvetica", 11)
        c.drawString(x, y, line)
        y -= line_height

    c.save()
    return str(p.resolve())


def build_mcq_markdown(mcqs: List[Any], title: str = "MCQ Quiz") -> str:
    """
    mcqs: list of features.mcq_generator.MCQ objects (or same fields).
    """
    out = [f"# {title}", ""]
    for idx, q in enumerate(mcqs, start=1):
        out.append(f"## Q{idx}. {q.question}")
        out.append("")
        labels = ["A", "B", "C", "D"]
        for i, opt in enumerate(q.options):
            out.append(f"- {labels[i]}. {opt}")
        out.append("")
        out.append(f"**Correct:** {labels[q.correct_index]}")
        if q.explanation:
            out.append(f"**Explanation:** {q.explanation}")
        if getattr(q, "citations", None):
            cits = q.citations
            out.append("**Citations:** " + ", ".join(
                [f"{c.get('doc')} p{c.get('page')} c{c.get('chunk_index')}" for c in cits]
            ))
        out.append("")
    return "\n".join(out)


def build_answer_markdown(answer: str, evidence: List[Any], question: str, title: str = "Answer") -> str:
    out = [f"# {title}", "", f"## Question", question, "", "## Answer", answer, "", "## Evidence / Citations", ""]
    for i, e in enumerate(evidence, start=1):
        out.append(f"- [E{i}] {e.doc} | page {e.page} | chunk {e.chunk_index} | dist={e.distance:.4f}")
    out.append("")
    return "\n".join(out)

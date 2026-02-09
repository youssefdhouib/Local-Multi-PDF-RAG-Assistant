export function downloadFile(content: string, filename: string, type: string = "text/markdown") {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

export function exportChatToMarkdown(messages: any[], selectedDocs: string[]) {
    const timestamp = new Date().toISOString().split("T")[0];
    let md = `# RAG Assistant Chat Export - ${timestamp}\n\n`;

    if (selectedDocs.length > 0) {
        md += `**Context**: ${selectedDocs.join(", ")}\n\n---\n\n`;
    } else {
        md += `**Context**: General Knowledge (Chat Mode)\n\n---\n\n`;
    }

    messages.forEach((msg) => {
        const role = msg.role === "user" ? "User" : "Assistant";
        md += `### ${role}\n${msg.content}\n\n`;

        if (msg.citations && msg.citations.length > 0) {
            md += `> **Sources**:\n`;
            msg.citations.forEach((c: any) => {
                md += `> - *${c.doc}* (Page ${c.page}): "${c.text_snippet}"\n`;
            });
            md += `\n`;
        }
        md += `---\n\n`;
    });

    downloadFile(md, `chat_export_${timestamp}.md`);
}

export function exportSummaryToMarkdown(summary: any) {
    if (!summary) return;
    const timestamp = new Date().toISOString().split("T")[0];
    let md = `# ${summary.title}\n\n`;
    md += summary.markdown;

    if (summary.citations && summary.citations.length > 0) {
        md += `\n\n## Sources\n`;
        summary.citations.forEach((c: any) => {
            // Handle different citation shapes if needed
            const doc = c.doc || c.document_name;
            const page = c.page || c.page_number;
            md += `- ${doc} (Page ${page})\n`;
        });
    }

    downloadFile(md, `summary_${timestamp}.md`);
}

export function exportQuizToMarkdown(quiz: any, withAnswers: boolean = false) {
    if (!quiz || !quiz.mcqs) return;
    const timestamp = new Date().toISOString().split("T")[0];
    let md = `# Quiz Export - ${timestamp}\n\n`;

    quiz.mcqs.forEach((q: any, i: number) => {
        md += `### Q${i + 1}: ${q.question}\n`;
        q.options.forEach((opt: string, idx: number) => {
            const letter = String.fromCharCode(65 + idx);
            md += `- [ ] ${letter}. ${opt}\n`;
        });

        if (withAnswers) {
            const correctLetter = String.fromCharCode(65 + q.correct_index);
            md += `\n> **Answer**: ${correctLetter}\n`;
            md += `> **Explanation**: ${q.explanation}\n`;
        }
        md += `\n`;
    });

    downloadFile(md, `quiz_${timestamp}.md`);
}

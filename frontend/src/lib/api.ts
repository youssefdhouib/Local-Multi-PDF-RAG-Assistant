const API_BASE = "http://localhost:8000/api";

export interface Citation {
    id: string;
    doc: string;
    page: number;
    chunk_index: number;
    text_snippet?: string;
    distance: number;
}

export interface ChatResponse {
    answer: string;
    citations: Citation[];
}

export interface SummaryResponse {
    title: string;
    markdown: string;
    citations: any[];
}

export interface MCQItem {
    question: string;
    options: string[];
    correct_index: number;
    explanation: string;
    citations: any[];
}

export interface QuizResponse {
    mcqs: MCQItem[];
}

export interface Document {
    name: string;
    status: "indexing" | "ready" | "failed";
    created_at?: string;
    updated_at?: string;
    chunk_count?: number;
    page_count?: number;
    error?: string;
}

export async function fetchDocuments(): Promise<Document[]> {
    const res = await fetch(`${API_BASE}/documents`);
    if (!res.ok) throw new Error("Failed to fetch documents");
    const data = await res.json();
    return data.documents; // Now returns list of objects
}

export const uploadDocument = async (file: File): Promise<any> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
    }
    return response.json();
};

export async function deleteDocument(docName: string): Promise<any> {
    const res = await fetch(`${API_BASE}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_name: docName }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Delete failed");
    }
    return res.json();
}

export async function reindexDocument(docName: string): Promise<any> {
    const res = await fetch(`${API_BASE}/reindex`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_name: docName }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Re-index failed");
    }
    return res.json();
}

// Features
export async function chat(question: string, docName?: string): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, doc_name: docName }),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Chat failed");
    }
    return res.json();
}

export async function summarizeDocument(docName: string): Promise<SummaryResponse> {
    const res = await fetch(`${API_BASE}/summary/document`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_name: docName }),
    });
    if (!res.ok) throw new Error("Summarize failed");
    return res.json();
}

export async function summarizeLibrary(): Promise<SummaryResponse> {
    const res = await fetch(`${API_BASE}/summary/library`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error("Summarize failed");
    return res.json();
}

export async function generateQuiz(docName?: string, numQuestions: number = 5): Promise<QuizResponse> {
    const specific = !!docName;
    const endpoint = specific ? `${API_BASE}/quiz/document` : `${API_BASE}/quiz/library`;
    const body = specific ? { doc_name: docName, num_questions: numQuestions } : { num_questions: numQuestions };

    const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("Quiz generation failed");
    return res.json();
}

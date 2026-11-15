const API_BASE = "http://localhost:8000/api";

// Read FastAPI's {"detail": ...} so the UI shows the real reason
// (e.g. "Cannot reach Ollama ... Start it with `ollama serve`").
async function errorFrom(res: Response, fallback: string): Promise<Error> {
    const body = await res.json().catch(() => ({}));
    const detail = body?.detail;
    if (typeof detail === "string") return new Error(detail);
    if (Array.isArray(detail) && detail[0]?.msg) return new Error(detail[0].msg);
    return new Error(`${fallback} (HTTP ${res.status})`);
}

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

export interface CitationInfo {
    doc?: string;
    document_name?: string;
    page?: number;
    page_number?: number;
    text_snippet?: string;
}

export interface SummaryResponse {
    title: string;
    markdown: string;
    citations: CitationInfo[];
}

export interface MCQItem {
    question: string;
    options: string[];
    correct_index: number;
    explanation: string;
    citations: CitationInfo[];
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
    if (!res.ok) throw await errorFrom(res, "Failed to fetch documents");
    const data = await res.json();
    return data.documents; // Now returns list of objects
}

export interface ActionResponse {
    status: string;
    message: string;
}

export const uploadDocument = async (file: File): Promise<ActionResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
    });
    if (!response.ok) throw await errorFrom(response, "Upload failed");
    return response.json();
};

export async function deleteDocument(docName: string): Promise<ActionResponse> {
    const res = await fetch(`${API_BASE}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_name: docName }),
    });
    if (!res.ok) throw await errorFrom(res, "Delete failed");
    return res.json();
}

export async function reindexDocument(docName: string): Promise<ActionResponse> {
    const res = await fetch(`${API_BASE}/reindex`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_name: docName }),
    });
    if (!res.ok) throw await errorFrom(res, "Re-index failed");
    return res.json();
}

// Features
// docNames: the selected documents. Empty/undefined = search the whole library.
export async function chat(question: string, docNames?: string[]): Promise<ChatResponse> {
    const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, doc_names: docNames && docNames.length > 0 ? docNames : undefined }),
    });
    if (!res.ok) throw await errorFrom(res, "Chat failed");
    return res.json();
}

export async function summarizeDocument(docName: string): Promise<SummaryResponse> {
    const res = await fetch(`${API_BASE}/summary/document`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_name: docName }),
    });
    if (!res.ok) throw await errorFrom(res, "Summarize failed");
    return res.json();
}

export async function summarizeLibrary(): Promise<SummaryResponse> {
    const res = await fetch(`${API_BASE}/summary/library`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
    });
    if (!res.ok) throw await errorFrom(res, "Summarize failed");
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
    if (!res.ok) throw await errorFrom(res, "Quiz generation failed");
    return res.json();
}

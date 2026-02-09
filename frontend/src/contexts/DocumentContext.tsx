import { createContext, useState, useEffect, useContext, type ReactNode } from "react";
import { fetchDocuments, uploadDocument, deleteDocument, reindexDocument, type Document } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

interface DocumentContextType {
    documents: Document[];
    selectedDocs: string[]; // Still tracking by name for simplicity
    loading: boolean;
    uploading: boolean;
    refreshDocuments: () => Promise<void>;
    toggleDocumentSelection: (doc: string) => void;
    setSingleSelection: (doc: string) => void;
    uploadFile: (file: File) => Promise<void>;
    deleteFile: (doc: string) => Promise<void>;
    reindexFile: (doc: string) => Promise<void>;
    selectAll: () => void;
    deselectAll: () => void;
}

const DocumentContext = createContext<DocumentContextType | undefined>(undefined);

export function DocumentProvider({ children }: { children: ReactNode }) {
    const { toast } = useToast();
    const [documents, setDocuments] = useState<Document[]>([]);
    const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);

    const refreshDocuments = async () => {
        // Don't set global loading true on poll, only on initial
        try {
            const docs = await fetchDocuments();
            setDocuments(docs);

            // Cleanup selectedDocs if any were deleted
            setSelectedDocs(prev => prev.filter(d => docs.some(doc => doc.name === d)));
        } catch (error) {
            console.error(error);
        }
    };

    // Initial fetch
    useEffect(() => {
        setLoading(true);
        refreshDocuments().finally(() => setLoading(false));
    }, []);

    // Polling for indexing status
    useEffect(() => {
        // If any document is in "indexing" state, poll frequently
        const anyIndexing = documents.some(d => d.status === "indexing");
        let interval: ReturnType<typeof setInterval>;

        if (anyIndexing) {
            interval = setInterval(refreshDocuments, 2000); // 2s poll
        }

        return () => {
            if (interval) clearInterval(interval);
        };
    }, [documents]);

    const toggleDocumentSelection = (doc: string) => {
        // Only allow selecting ready docs? Or allow selecting but disable actions elsewhere?
        // User asked to "disable selecting it for chat until ready". 
        // We'll enforce that in UI, but here we can just toggle.
        // Actually, let's enforce it here to be safe:
        const docObj = documents.find(d => d.name === doc);
        if (docObj && docObj.status !== "ready") {
            toast({ title: "Not Ready", description: "Document is still indexing.", variant: "destructive" });
            return;
        }

        setSelectedDocs(prev =>
            prev.includes(doc) ? prev.filter(d => d !== doc) : [...prev, doc]
        );
    };

    const setSingleSelection = (doc: string) => {
        const docObj = documents.find(d => d.name === doc);
        if (docObj && docObj.status === "ready") {
            setSelectedDocs([doc]);
        }
    };

    const selectAll = () => {
        const readyDocs = documents.filter(d => d.status === "ready").map(d => d.name);
        setSelectedDocs(readyDocs);
    };

    const deselectAll = () => setSelectedDocs([]);

    const uploadFile = async (file: File) => {
        setUploading(true);
        try {
            const res = await uploadDocument(file);
            toast({
                title: res.status === "ready" ? "Already Exists" : "Upload Started",
                description: res.message
            });
            await refreshDocuments(); // will trigger polling
        } catch (error: any) {
            toast({ title: "Upload Failed", description: error.message, variant: "destructive" });
            throw error;
        } finally {
            setUploading(false);
        }
    };

    const deleteFile = async (doc: string) => {
        try {
            // Optimistic update - immediately remove from UI
            setDocuments(prev => prev.filter(d => d.name !== doc));
            setSelectedDocs(prev => prev.filter(d => d !== doc));

            await deleteDocument(doc);
            toast({ title: "Deleted", description: `Removed ${doc}` });

            // Refresh to confirm deletion from backend
            await refreshDocuments();
        } catch (error: any) {
            toast({ title: "Delete Failed", description: error.message, variant: "destructive" });
            // Refresh to restore the document if delete failed
            await refreshDocuments();
        }
    };

    const reindexFile = async (doc: string) => {
        setUploading(true);
        try {
            await reindexDocument(doc);
            toast({ title: "Re-indexing Started", description: `Updating index for ${doc}` });
            await refreshDocuments(); // starts polling
        } catch (error: any) {
            toast({ title: "Re-index Failed", description: error.message, variant: "destructive" });
        } finally {
            setUploading(false);
        }
    };

    return (
        <DocumentContext.Provider value={{
            documents,
            selectedDocs,
            loading,
            uploading,
            refreshDocuments,
            toggleDocumentSelection,
            setSingleSelection,
            uploadFile,
            deleteFile,
            reindexFile,
            selectAll,
            deselectAll
        }}>
            {children}
        </DocumentContext.Provider>
    );
}

export function useDocuments() {
    const context = useContext(DocumentContext);
    if (!context) throw new Error("useDocuments must be used within a DocumentProvider");
    return context;
}

import { createContext, useState, useContext, type ReactNode, useEffect } from "react";
import { chat, type ChatResponse, type Citation } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";
import { useDocuments } from "@/contexts/DocumentContext";
import { useUser } from "@/contexts/UserContext";

export interface Message {
    role: "user" | "assistant";
    content: string;
    citations?: Citation[];
}

interface ChatContextType {
    messages: Message[];
    input: string;
    setInput: (val: string) => void;
    loading: boolean;
    sendMessage: (text?: string) => Promise<void>;
    clearChat: () => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export function ChatProvider({ children }: { children: ReactNode }) {
    const { toast } = useToast();
    const { selectedDocs } = useDocuments();
    const { username } = useUser();

    // State moved from ChatPage
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);

    // Initial Greeting
    useEffect(() => {
        // Keep existing messages; only seed the chat when it is empty and the
        // username is known (or reset after logout).
        setMessages((prev) => {
            if (prev.length > 0) return prev;
            const greeting = username
                ? `Hello ${username}! I'm your MultiPDF Assistant. Upload documents to the sidebar and select them to start chatting contextually, or just ask me anything!`
                : "Hello! I'm your MultiPDF Assistant. Upload documents to the sidebar and select them to start chatting contextually, or just ask me anything!";
            return [{ role: "assistant", content: greeting }];
        });
    }, [username]);

    const sendMessage = async (text: string = input) => {
        if (!text.trim() || loading) return;

        const userMsg = text;
        if (text === input) {
            setInput("");
        }

        setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
        setLoading(true);

        try {
            // Determine doc context
            let docName: string | undefined = undefined;
            if (selectedDocs.length === 1) {
                docName = selectedDocs[0];
            }
            // If > 1, backend handles it (or we pass list if API supported it, but current API takes optional single docName or none)
            // Wait, current API `chat(message, docName)` logic:
            // logic in ChatPage was: if selectedDocs.length === 1 -> docName.
            // What if multiple? The backend `_build_prompt` takes `evidence_text`. 
            // The logic implies we only support single doc chatting OR full library chatting via router?
            // Let's check `web_server.py`/`chat` endpoint.
            // It takes `doc_name: Optional[str]`. If None, it queries ALL docs (library chat).
            // So if selectedDocs.length > 1, we currently treat it as "Library Chat" (docName=undefined).
            // BUT wait, if I select 2 docs, I expect to chat with THOSE 2.
            // The current backend simplistic logic might not support "Subset of docs".
            // It supports "One doc" or "All docs".
            // Let's stick to existing behavior for now: Single doc -> specific context. Multiple docs -> All docs context (or maybe logic needs upgrade later).
            // Actually, `activeTab` logic in `ChatPage` didn't explicitly handle >1.

            const res: ChatResponse = await chat(userMsg, docName);

            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: res.answer, citations: res.citations },
            ]);
        } catch (err) {
            const message = err instanceof Error ? err.message : "Something went wrong";
            toast({ title: "Error", description: message, variant: "destructive" });
            setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, I encountered an error answering that." }]);
        } finally {
            setLoading(false);
        }
    };

    const clearChat = () => {
        setMessages([{ role: "assistant", content: "Chat cleared. Ready for new questions." }]);
    };

    return (
        <ChatContext.Provider value={{
            messages,
            input,
            setInput,
            loading,
            sendMessage,
            clearChat
        }}>
            {children}
        </ChatContext.Provider>
    );
}

export function useChat() {
    const context = useContext(ChatContext);
    if (!context) throw new Error("useChat must be used within a ChatProvider");
    return context;
}

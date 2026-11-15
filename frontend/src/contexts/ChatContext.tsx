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
            // Search exactly the selected documents (1 or more).
            // No selection = search the whole library.
            const res: ChatResponse = await chat(userMsg, selectedDocs);

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

import { useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Send, Bookmark, MoreVertical, Trash, Lightbulb, Download, User, Sparkles } from "lucide-react";
import { exportChatToMarkdown } from "@/lib/export";
import { useDocuments } from "@/contexts/DocumentContext";
import { useChat } from "@/contexts/ChatContext";
import { useUser } from "@/contexts/UserContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";

export function ChatPage() {
    const { username } = useUser();
    const { selectedDocs } = useDocuments();
    const { messages, input, setInput, loading, sendMessage, clearChat } = useChat();
    const endRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSend = (text?: string) => sendMessage(text);
    const handleClear = () => clearChat();


    // Suggestions based on context
    const getSuggestions = () => {
        if (selectedDocs.length === 0) return [
            "What can you do?",
            "How do I upload a PDF?",
            "Write a short poem about AI"
        ];
        if (selectedDocs.length === 1) return [
            `Summarize ${selectedDocs[0]}`,
            "What are the main key points?",
            "Explain the technical concepts",
            "Create a quiz from this doc"
        ];
        return [
            "Summarize the selected documents",
            "Compare the arguments in these files",
            "What are the common themes?",
            "List all dates mentioned"
        ];
    };

    return (
        <div className="flex flex-col h-full relative bg-background font-sans">
            {/* Floating Context Pill */}
            {selectedDocs.length > 0 && (
                <div className="absolute top-6 left-0 right-0 z-10 flex justify-center pointer-events-none">
                    <div className="bg-background/95 backdrop-blur-md border shadow-sm px-4 py-2 rounded-full text-xs text-muted-foreground flex items-center gap-2 animate-in fade-in slide-in-from-top-2 duration-300 pointer-events-auto hover:shadow-md transition-shadow">
                        <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
                        <span>Using context from <span className="font-semibold text-foreground">{selectedDocs.length} document{selectedDocs.length > 1 ? 's' : ''}</span></span>
                    </div>
                </div>
            )}

            {/* Messages Area */}
            <ScrollArea className="flex-1 w-full">
                <div className="max-w-3xl mx-auto px-4 pt-24 pb-12 space-y-6">
                    {messages.map((msg, idx) => (
                        <div
                            key={idx}
                            className={`flex gap-4 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"} animate-in fade-in slide-in-from-bottom-2 duration-500`}
                        >
                            {/* Avatar */}
                            <Avatar className={`h-8 w-8 mt-1 border shrink-0 ${msg.role === "assistant" ? "bg-primary/10" : "bg-secondary"}`}>
                                <AvatarFallback className={`${msg.role === "assistant" ? "text-primary" : "text-foreground"}`}>
                                    {msg.role === "assistant" ? <Sparkles size={14} /> : (
                                        <span className="text-xs font-semibold">
                                            {username ? username.charAt(0).toUpperCase() : <User size={14} />}
                                        </span>
                                    )}
                                </AvatarFallback>
                            </Avatar>

                            {/* Content */}
                            <div className={`flex flex-col max-w-[85%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
                                <div className={`prose prose-neutral dark:prose-invert max-w-none text-sm leading-relaxed ${msg.role === "user"
                                    ? "bg-primary text-primary-foreground shadow-sm px-5 py-3 rounded-2xl rounded-tr-sm"
                                    : ""
                                    }`}>
                                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                                </div>

                                {/* Sources (Assistant Only) */}
                                {msg.role === "assistant" && msg.citations && msg.citations.length > 0 && (
                                    <div className="mt-3 w-full max-w-full">
                                        <Accordion type="single" collapsible className="w-full">
                                            <AccordionItem value="sources" className="border rounded-lg bg-muted/30 px-0 overflow-hidden">
                                                <AccordionTrigger className="px-3 py-2 text-xs font-medium text-muted-foreground hover:no-underline hover:bg-muted/50 transition-colors">
                                                    <span className="flex items-center gap-2">
                                                        <Bookmark className="h-3.5 w-3.5" />
                                                        {msg.citations.length} Sources
                                                    </span>
                                                </AccordionTrigger>
                                                <AccordionContent className="px-3 pb-3 pt-1 space-y-3 bg-background/50">
                                                    {msg.citations.map((cit, i) => (
                                                        <div key={i} className="text-xs group">
                                                            <div className="flex items-baseline justify-between mb-1">
                                                                <span className="font-semibold text-foreground truncate max-w-[70%] text-[11px] bg-primary/10 px-1.5 py-0.5 rounded">
                                                                    {cit.doc}
                                                                </span>
                                                                <span className="text-muted-foreground whitespace-nowrap ml-2 font-mono text-[10px]">
                                                                    Page {cit.page}
                                                                </span>
                                                            </div>
                                                            <p className="text-muted-foreground/80 pl-2 border-l-2 border-primary/20 italic leading-relaxed">
                                                                "{cit.text_snippet}"
                                                            </p>
                                                        </div>
                                                    ))}
                                                </AccordionContent>
                                            </AccordionItem>
                                        </Accordion>
                                    </div>
                                )}

                                {/* Suggestion Chips (Assistant Only - Last Message) */}
                                {msg.role === "assistant" && idx === messages.length - 1 && !loading && (
                                    <div className="flex gap-2 mt-3 flex-wrap">
                                        {["Tell me more", "Simplify", "Key takeaways"].map((s, i) => (
                                            <button
                                                key={i}
                                                onClick={() => handleSend(s)}
                                                className="text-xs bg-muted/40 hover:bg-muted border border-transparent hover:border-border px-3 py-1.5 rounded-full transition-all text-muted-foreground hover:text-foreground cursor-pointer"
                                            >
                                                {s}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}

                    {/* Loading Indicator */}
                    {loading && (
                        <div className="flex gap-4 animate-pulse">
                            <Avatar className="h-8 w-8 mt-1 border shrink-0 bg-primary/10">
                                <AvatarFallback className="text-primary"><Sparkles size={14} /></AvatarFallback>
                            </Avatar>
                            <div className="space-y-2 mt-2">
                                <div className="h-4 w-48 bg-muted/50 rounded animate-pulse" />
                                <div className="h-4 w-32 bg-muted/50 rounded animate-pulse delay-75" />
                            </div>
                        </div>
                    )}

                    {/* Empty State / Suggestions */}
                    {messages.length === 1 && !loading && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-12 w-full">
                            {getSuggestions().map((s, i) => (
                                <button
                                    key={i}
                                    onClick={() => handleSend(s)}
                                    className="p-4 text-sm text-left border rounded-xl hover:bg-muted/40 hover:border-primary/30 transition-all duration-300 group"
                                >
                                    <span className="flex items-center gap-2 font-medium text-foreground/80 group-hover:text-primary mb-1">
                                        <Lightbulb className="h-4 w-4 opacity-50 group-hover:text-primary" />
                                        Suggestion
                                    </span>
                                    <span className="text-muted-foreground block">{s}</span>
                                </button>
                            ))}
                        </div>
                    )}

                    <div ref={endRef} />
                </div>
            </ScrollArea>

            {/* Input Area - Fixed Bottom */}
            <div className="bg-background/80 backdrop-blur-xl pt-2 pb-8 px-4">
                <div className="max-w-3xl mx-auto relative flex flex-col gap-3">
                    <div className="relative shadow-xl shadow-primary/5 border border-border/50 rounded-3xl bg-background/50 focus-within:bg-background focus-within:border-primary/30 focus-within:shadow-primary/10 transition-all duration-300">
                        <Input
                            placeholder="Ask a follow-up question..."
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleSend()}
                            disabled={loading}
                            className="w-full border-0 focus-visible:ring-0 focus-visible:ring-offset-0 shadow-none py-7 pl-6 pr-24 text-base bg-transparent placeholder:text-muted-foreground/50"
                        />
                        <div className="absolute right-2 top-2 flex items-center gap-1">
                            <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-10 w-10 rounded-full text-muted-foreground hover:bg-muted/50 transition-colors">
                                        <MoreVertical className="h-4 w-4" />
                                    </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="rounded-xl">
                                    <DropdownMenuItem onClick={handleClear} className="rounded-lg cursor-pointer">
                                        <Trash className="mr-2 h-4 w-4" /> Clear Chat
                                    </DropdownMenuItem>
                                    <DropdownMenuItem onClick={() => exportChatToMarkdown(messages, selectedDocs)} className="rounded-lg cursor-pointer">
                                        <Download className="mr-2 h-4 w-4" /> Export Chat
                                    </DropdownMenuItem>
                                </DropdownMenuContent>
                            </DropdownMenu>

                            <Button
                                onClick={() => handleSend()}
                                disabled={loading || !input.trim()}
                                size="icon"
                                className={`h-10 w-10 rounded-full shadow-sm transition-all duration-300 ${input.trim()
                                    ? "bg-primary text-primary-foreground hover:scale-105 hover:shadow-md"
                                    : "bg-muted/50 text-muted-foreground cursor-not-allowed"
                                    }`}
                            >
                                <Send size={18} className={input.trim() ? "ml-0.5" : ""} />
                            </Button>
                        </div>
                    </div>
                    <div className="text-center">
                        <p className="text-[11px] text-muted-foreground/60 transition-opacity hover:opacity-100 cursor-default">
                            MultiPDF Assistant can make mistakes. Check important info.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

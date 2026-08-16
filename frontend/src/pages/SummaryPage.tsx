import { useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Copy, FileText, Check, AlertCircle, Printer, BookOpen, Quote, FileDown } from "lucide-react";
import { summarizeDocument, summarizeLibrary, type SummaryResponse } from "@/lib/api";
import { useDocuments } from "@/contexts/DocumentContext";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

declare global {
    interface Window {
        html2pdf?: (options?: Record<string, unknown>) => {
            set: (options: Record<string, unknown>) => {
                from: (element: HTMLElement) => {
                    save: () => void;
                };
            };
        };
    }
}

export function SummaryPage() {
    const { toast } = useToast();
    const { selectedDocs } = useDocuments();
    const [summary, setSummary] = useState<SummaryResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [copied, setCopied] = useState(false);
    const contentRef = useRef<HTMLDivElement>(null);

    // Determine mode based on selection
    const mode = selectedDocs.length === 1 ? "document" : "library";
    const targetDoc = selectedDocs.length === 1 ? selectedDocs[0] : null;

    const handleSummarize = async () => {
        setLoading(true);
        setSummary(null);
        try {
            let res: SummaryResponse;
            if (mode === "document" && targetDoc) {
                res = await summarizeDocument(targetDoc);
            } else {
                res = await summarizeLibrary();
            }
            setSummary(res);
        } catch (err) {
            const message = err instanceof Error ? err.message : "Summarization failed";
            toast({ title: "Error", description: message, variant: "destructive" });
        } finally {
            setLoading(false);
        }
    };

    const handleCopy = () => {
        if (!summary) return;
        navigator.clipboard.writeText(summary.markdown);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
        toast({ title: "Copied", description: "Summary copied to clipboard" });
    };

    const handlePrint = () => {
        window.print();
    };

    const handleDownloadPDF = () => {
        if (!contentRef.current || !summary) return;

        const element = contentRef.current;
        const opt = {
            margin: [15, 15],
            filename: `${summary.title || "Summary"}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2 },
            jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
        };

        if (window.html2pdf) {
            window.html2pdf().set(opt).from(element).save();
            toast({ title: "Generating PDF", description: "Your download will start shortly." });
        } else {
            toast({ title: "Error", description: "PDF library not loaded. Try refreshing the page.", variant: "destructive" });
        }
    };

    return (
        <div className="h-full flex flex-col md:flex-row gap-6 max-w-7xl mx-auto w-full p-6">

            {/* Left Sidebar - Options & Metadata */}
            <div className="w-full md:w-80 flex-shrink-0 flex flex-col gap-6 no-print">
                <div className="space-y-1">
                    <h2 className="text-2xl font-bold tracking-tight">Summary</h2>
                    <p className="text-sm text-muted-foreground">
                        Generate concise overviews of your documents.
                    </p>
                </div>

                <div className="bg-muted/30 p-4 rounded-xl border space-y-4">
                    <div className="space-y-2">
                        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Target Content</span>
                        <div className="flex items-center gap-2 font-medium text-sm">
                            {mode === "document" ? (
                                <>
                                    <FileText className="h-4 w-4 text-primary" />
                                    <span className="truncate" title={targetDoc!}>{targetDoc}</span>
                                </>
                            ) : (
                                <>
                                    <BookOpen className="h-4 w-4 text-primary" />
                                    <span>Entire Library ({selectedDocs.length} selected)</span>
                                </>
                            )}
                        </div>
                    </div>

                    {summary && (
                        <>
                            <div className="h-px bg-border" />
                            <div className="space-y-2">
                                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Analysis Stats</span>
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                    <div className="bg-background p-2 rounded border">
                                        <span className="block text-muted-foreground">Citations</span>
                                        <span className="font-semibold text-lg">{summary.citations?.length || 0}</span>
                                    </div>
                                    <div className="bg-background p-2 rounded border">
                                        <span className="block text-muted-foreground">Est. Read</span>
                                        <span className="font-semibold text-lg">~2 min</span>
                                    </div>
                                </div>
                            </div>

                            <div className="h-px bg-border" />
                            <div className="space-y-2">
                                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</span>
                                <div className="flex flex-col gap-2 pt-1">
                                    <Button variant="outline" className="w-full justify-start h-9" onClick={handleCopy}>
                                        {copied ? <Check className="h-4 w-4 mr-2 text-green-500" /> : <Copy className="h-4 w-4 mr-2" />}
                                        Copy Markdown
                                    </Button>
                                    <Button variant="outline" className="w-full justify-start h-9" onClick={handlePrint}>
                                        <Printer className="h-4 w-4 mr-2" />
                                        Print Page
                                    </Button>
                                    <Button variant="default" className="w-full justify-start h-9" onClick={handleDownloadPDF}>
                                        <FileDown className="h-4 w-4 mr-2" />
                                        Download PDF
                                    </Button>
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Status Alert if needed */}
                {selectedDocs.length === 0 && (
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertTitle>No Selection</AlertTitle>
                        <AlertDescription className="text-xs">
                            Please select a document from the "Docs" tab to summarize.
                        </AlertDescription>
                    </Alert>
                )}
            </div>

            {/* Right Content Area */}
            <div className="flex-1 flex flex-col h-full min-h-[500px]">
                {!summary ? (
                    <div className="flex-1 flex flex-col items-center justify-center space-y-6 border-2 border-dashed rounded-xl bg-muted/5 p-12 text-center h-[600px]">
                        <div className="relative">
                            <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full opacity-0 animate-pulse" style={{ opacity: loading ? 0.5 : 0 }} />
                            <div className="relative bg-background p-6 rounded-full shadow-sm border">
                                <FileText className={`h-10 w-10 text-primary transition-all duration-500 ${loading ? "animate-bounce" : ""}`} />
                            </div>
                        </div>

                        <div className="space-y-2 max-w-sm">
                            <h3 className="text-xl font-semibold">
                                {loading ? "Analyzing Document..." : "Ready to Summarize"}
                            </h3>
                            <p className="text-muted-foreground">
                                {loading
                                    ? "Our AI is reading through the content to extract key insights. This may take a moment."
                                    : "Click the button below to generate a comprehensive summary with citations."}
                            </p>
                        </div>

                        {!loading && selectedDocs.length > 0 && (
                            <Button onClick={handleSummarize} size="lg" className="px-8 shadow-lg shadow-primary/20 hover:shadow-primary/30 transition-shadow">
                                <Quote className="mr-2 h-4 w-4" /> Generate Summary
                            </Button>
                        )}
                    </div>
                ) : (
                    <ScrollArea className="flex-1 rounded-xl border bg-background shadow-sm h-[800px]"> {/* Fixed height for scroll or flex-1 logic needs parent height */}
                        <div ref={contentRef} className="print-content p-8 md:p-12 max-w-[210mm] mx-auto bg-white min-h-full text-zinc-900"> {/* A4 width approx */}
                            <div className="mb-8 border-b pb-4">
                                <h1 className="text-3xl font-bold tracking-tight text-zinc-900">{summary.title || "Document Summary"}</h1>
                                <p className="text-sm text-zinc-500 mt-2">Generated on {new Date().toLocaleDateString()}</p>
                            </div>

                            <div className="prose prose-slate max-w-none text-justify leading-relaxed text-zinc-800">
                                <ReactMarkdown>{summary.markdown}</ReactMarkdown>
                            </div>

                            {summary.citations && summary.citations.length > 0 && (
                                <div className="mt-12 pt-6 border-t border-dashed border-zinc-200">
                                    <h4 className="text-sm font-semibold mb-4 uppercase tracking-wider text-zinc-500">References</h4>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        {summary.citations.map((cit, idx) => (
                                            <div key={idx} className="flex items-start gap-2 text-xs bg-zinc-50 p-3 rounded border border-zinc-100">
                                                <Badge variant="secondary" className="text-[10px] shrink-0 bg-zinc-200 text-zinc-700">{idx + 1}</Badge>
                                                <div>
                                                    <span className="font-medium block mb-0.5 text-zinc-900">{cit.doc}</span>
                                                    <span className="text-zinc-500">Page {cit.page}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </ScrollArea>
                )}
            </div>
        </div>
    );
}

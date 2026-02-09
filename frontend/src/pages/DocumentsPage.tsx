import { useState } from "react";
import {
    FileText, PlayCircle, BarChart2, Search, UploadCloud, CheckCircle2,
    MoreVertical, Trash2, RefreshCw, Loader2, File, Calendar, HardDrive, AlertTriangle
} from "lucide-react";
import { useDocuments } from "@/contexts/DocumentContext";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Progress } from "@/components/ui/progress";
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle
} from "@/components/ui/alert-dialog";

interface DocumentsPageProps {
    onNavigate: (page: string, context?: any) => void;
}

export function DocumentsPage({ onNavigate }: DocumentsPageProps) {
    const {
        documents, selectedDocs, toggleDocumentSelection, setSingleSelection,
        uploadFile, deleteFile, reindexFile, uploading
    } = useDocuments();
    const [filter, setFilter] = useState("");
    const [isDragging, setIsDragging] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);

    const handleConfirmDelete = async () => {
        if (!deleteTarget) return;
        setIsDeleting(true);
        try {
            await deleteFile(deleteTarget);
        } finally {
            setIsDeleting(false);
            setDeleteTarget(null);
        }
    };

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            try {
                await uploadFile(file);
            } catch (e) {
                // toast handled in context
            }
        }
        e.target.value = "";
    };

    const filteredDocs = documents.filter((d) => d.name.toLowerCase().includes(filter.toLowerCase()));

    return (
        <div className="flex flex-col h-full space-y-8 p-6 max-w-7xl mx-auto w-full">
            {/* Header Section */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 border-b pb-6">
                <div className="space-y-1">
                    <h2 className="text-3xl font-bold tracking-tight text-foreground">Knowledge Base</h2>
                    <p className="text-muted-foreground text-sm max-w-lg">
                        Manage your documents. content. Select files to use them as context for your chat.
                    </p>
                </div>

                <div className="relative w-full md:w-72 group transition-all duration-300 focus-within:w-80">
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="Search documents..."
                        className="pl-9 h-10 bg-muted/50 border-transparent focus:bg-background focus:border-input transition-all shadow-sm"
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                    />
                </div>
            </div>

            {/* Upload Zone */}
            <div
                className={`relative group rounded-xl border-2 border-dashed transition-all duration-300 ${isDragging || uploading
                    ? "border-primary bg-primary/5 scale-[1.01] shadow-lg"
                    : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30"
                    }`}
            >
                <input
                    type="file"
                    accept=".pdf"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20"
                    onChange={handleUpload}
                    disabled={uploading}
                    onDragEnter={() => setIsDragging(true)}
                    onDragLeave={() => setIsDragging(false)}
                    onDragOver={(e) => {
                        e.preventDefault();
                        setIsDragging(true);
                    }}
                    onDrop={() => setIsDragging(false)}
                />
                <div className="flex flex-col items-center justify-center py-10 text-center space-y-4">
                    <div className={`p-4 rounded-full bg-background shadow-sm ring-1 ring-border transition-transform duration-500 group-hover:scale-110 ${uploading ? "animate-pulse" : ""}`}>
                        {uploading ? (
                            <Loader2 className="h-8 w-8 text-primary animate-spin" />
                        ) : (
                            <UploadCloud className="h-8 w-8 text-primary/80" />
                        )}
                    </div>
                    <div className="space-y-1">
                        <h3 className="text-lg font-semibold text-foreground">
                            {uploading ? "Uploading & Indexing..." : "Click to Upload PDF"}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                            or drag and drop here to add to library
                        </p>
                    </div>
                </div>
                {uploading && <Progress value={45} className="absolute bottom-0 h-1 w-full rounded-b-xl" />}
            </div>

            {/* Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 pb-12">
                {filteredDocs.map((doc) => {
                    const isSelected = selectedDocs.includes(doc.name);
                    const isReady = doc.status === "ready";
                    const isIndexing = doc.status === "indexing";

                    return (
                        <Card
                            key={doc.name}
                            className={`group relative flex flex-col transition-all duration-300 border hover:shadow-lg hover:-translate-y-1 overflow-hidden ${isSelected
                                ? "ring-2 ring-primary border-primary bg-primary/[0.02]"
                                : "bg-card hover:border-primary/40"
                                } ${!isReady ? "opacity-90" : ""}`}
                        >
                            {/* Selection Overlay */}
                            <div
                                className={`absolute inset-0 z-0 ${isReady ? "cursor-pointer" : "cursor-not-allowed"}`}
                                onClick={() => isReady && toggleDocumentSelection(doc.name)}
                            />

                            <CardHeader className="flex flex-row items-start justify-between p-5 pb-2 relative z-10 pointer-events-none">
                                <div className={`p-2.5 rounded-xl shadow-sm ring-1 ring-border/50 transition-colors ${isSelected
                                    ? "bg-primary text-primary-foreground ring-primary"
                                    : "bg-background text-muted-foreground group-hover:text-foreground group-hover:bg-accent"
                                    }`}>
                                    <FileText size={22} strokeWidth={1.5} />
                                </div>

                                <div className="flex items-center gap-1 pointer-events-auto">
                                    {isSelected && (
                                        <div className="animate-in zoom-in duration-300 text-primary mr-1">
                                            <CheckCircle2 className="h-5 w-5 fill-primary/10" />
                                        </div>
                                    )}

                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-background/80 rounded-full">
                                                <MoreVertical className="h-4 w-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end" className="w-40">
                                            <DropdownMenuItem onClick={(e) => { e.stopPropagation(); reindexFile(doc.name); }}>
                                                <RefreshCw className="mr-2 h-4 w-4" /> Re-index
                                            </DropdownMenuItem>
                                            <DropdownMenuItem
                                                onClick={(e) => { e.stopPropagation(); setDeleteTarget(doc.name); }}
                                                className="text-destructive focus:text-destructive"
                                            >
                                                <Trash2 className="mr-2 h-4 w-4" /> Delete
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            </CardHeader>

                            <CardContent className="px-5 py-3 flex-1 relative z-10 pointer-events-none">
                                <h3 className="font-semibold text-base mb-1 line-clamp-2 leading-snug group-hover:text-primary transition-colors" title={doc.name}>
                                    {doc.name}
                                </h3>

                                <div className="flex flex-wrap gap-y-1 gap-x-3 text-[11px] text-muted-foreground font-medium mt-3">
                                    {isIndexing ? (
                                        <Badge variant="secondary" className="bg-blue-500/10 text-blue-600 hover:bg-blue-500/20 gap-1 pl-1">
                                            <Loader2 className="h-3 w-3 animate-spin" /> Indexing...
                                        </Badge>
                                    ) : (
                                        <>
                                            <span className="flex items-center gap-1 bg-muted/40 px-2 py-0.5 rounded-md">
                                                <HardDrive className="h-3 w-3 opacity-70" /> {doc.chunk_count || 0} chunks
                                            </span>
                                            {doc.created_at && (
                                                <span className="flex items-center gap-1 bg-muted/40 px-2 py-0.5 rounded-md">
                                                    <Calendar className="h-3 w-3 opacity-70" /> {new Date(doc.created_at).toLocaleDateString()}
                                                </span>
                                            )}
                                        </>
                                    )}
                                </div>
                            </CardContent>

                            <CardFooter className="p-4 pt-0 gap-2 relative z-10 pointer-events-auto mt-auto">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={!isReady}
                                    className="flex-1 h-9 text-xs font-medium hover:bg-primary/5 hover:text-primary transition-colors hover:border-primary/30"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setSingleSelection(doc.name);
                                        onNavigate("summary", { doc: doc.name });
                                    }}
                                >
                                    <BarChart2 className="mr-2 h-3.5 w-3.5" /> Summarize
                                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={!isReady}
                                    className="flex-1 h-9 text-xs font-medium hover:bg-primary/5 hover:text-primary transition-colors hover:border-primary/30"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setSingleSelection(doc.name);
                                        onNavigate("quiz", { doc: doc.name });
                                    }}
                                >
                                    <PlayCircle className="mr-2 h-3.5 w-3.5" /> Quiz
                                </Button>
                            </CardFooter>
                        </Card>
                    );
                })}

                {filteredDocs.length === 0 && (
                    <div className="col-span-full flex flex-col items-center justify-center py-20 text-muted-foreground border border-dashed rounded-xl bg-muted/5">
                        <div className="p-4 bg-muted/50 rounded-full mb-4">
                            <File className="h-8 w-8 opacity-40" />
                        </div>
                        <p className="text-lg font-medium text-foreground">No documents found</p>
                        <p className="text-sm opacity-70">Try searching for something else or upload a new PDF.</p>
                    </div>
                )}
            </div>

            {/* Delete Confirmation Dialog */}
            <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
                <AlertDialogContent className="rounded-2xl max-w-md">
                    <AlertDialogHeader>
                        <div className="mx-auto w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-2">
                            <AlertTriangle className="h-6 w-6 text-destructive" />
                        </div>
                        <AlertDialogTitle className="text-center">Delete Document?</AlertDialogTitle>
                        <AlertDialogDescription className="text-center">
                            This will permanently remove <span className="font-semibold text-foreground">{deleteTarget}</span> from
                            the vector database and all cached data. This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter className="sm:justify-center gap-2 mt-4">
                        <AlertDialogCancel className="rounded-xl" disabled={isDeleting}>
                            Cancel
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleConfirmDelete}
                            className="bg-destructive hover:bg-destructive/90 text-destructive-foreground rounded-xl"
                            disabled={isDeleting}
                        >
                            {isDeleting ? (
                                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Deleting...</>
                            ) : (
                                <><Trash2 className="mr-2 h-4 w-4" /> Delete</>
                            )}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

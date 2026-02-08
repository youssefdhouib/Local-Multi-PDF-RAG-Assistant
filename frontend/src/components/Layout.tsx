import { useState } from "react";
import { useDocuments } from "@/contexts/DocumentContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
    Search, Check, MoreHorizontal,
    Trash2, RefreshCw, Sun, Moon, Menu, Loader2, Zap, FileText, X, Upload, AlertTriangle
} from "lucide-react";
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle
} from "@/components/ui/alert-dialog";

// Fuzzy search: matches if query words appear anywhere in the name
const fuzzyMatch = (name: string, query: string): boolean => {
    if (!query.trim()) return true;
    const lowerName = name.toLowerCase();
    const words = query.toLowerCase().split(/\s+/);
    return words.every(word => lowerName.includes(word));
};

// Highlight matching parts
const highlightMatch = (text: string, query: string) => {
    if (!query.trim()) return text;
    const regex = new RegExp(`(${query.split(/\s+/).join('|')})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, i) =>
        regex.test(part) ? <mark key={i} className="bg-primary/20 text-primary rounded px-0.5">{part}</mark> : part
    );
};

export function Sidebar() {
    const {
        documents, selectedDocs, toggleDocumentSelection,
        uploadFile, deleteFile, reindexFile,
        loading, uploading
    } = useDocuments();
    const [search, setSearch] = useState("");
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

    const filtered = documents.filter(d => fuzzyMatch(d.name, search));

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            try {
                await uploadFile(file);
            } catch (e) {
                // error handled in context
            }
        }
        e.target.value = ""; // Reset
    };

    return (
        <div className="flex flex-col h-full bg-gradient-to-b from-muted/5 to-muted/20">
            {/* Header */}
            <div className="p-4 pb-3 border-b bg-background/50 backdrop-blur-sm">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <div className="h-7 w-7 rounded-lg bg-primary/10 flex items-center justify-center">
                            <FileText className="h-4 w-4 text-primary" />
                        </div>
                        <h2 className="text-base font-semibold tracking-tight">Documents</h2>
                    </div>
                    <span className="text-[11px] bg-primary/10 text-primary px-2 py-0.5 rounded-full font-semibold">
                        {documents.length}
                    </span>
                </div>

                {/* Search Input */}
                <div className="relative group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/60 group-focus-within:text-primary transition-colors" />
                    <Input
                        placeholder="Search documents..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="pl-9 pr-8 h-10 text-sm bg-muted/30 border-muted-foreground/10 focus:bg-background focus:border-primary/30 transition-all rounded-xl"
                    />
                    {search && (
                        <button
                            onClick={() => setSearch("")}
                            className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground hover:text-foreground transition-colors"
                        >
                            <X className="h-4 w-4" />
                        </button>
                    )}
                </div>
            </div>

            {/* Upload Button */}
            <div className="p-3">
                <div className="relative group">
                    <input
                        type="file"
                        accept=".pdf"
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                        onChange={handleUpload}
                        disabled={uploading}
                    />
                    <Button
                        variant="outline"
                        className="w-full h-11 justify-center gap-2 text-sm font-medium border-dashed border-2 border-primary/20 bg-primary/5 hover:bg-primary/10 hover:border-primary/40 text-primary transition-all rounded-xl"
                        disabled={uploading}
                    >
                        {uploading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Upload className="h-4 w-4" />
                        )}
                        {uploading ? "Processing..." : "Upload PDF"}
                    </Button>
                </div>
            </div>

            {/* Document List */}
            <ScrollArea className="flex-1 px-3">
                <div className="space-y-1.5 pb-4">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-12 gap-3">
                            <Loader2 className="h-6 w-6 animate-spin text-primary/60" />
                            <span className="text-xs text-muted-foreground">Loading documents...</span>
                        </div>
                    ) : filtered.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 gap-3">
                            <div className="h-12 w-12 rounded-full bg-muted/50 flex items-center justify-center">
                                <FileText className="h-6 w-6 text-muted-foreground/50" />
                            </div>
                            <div className="text-center">
                                <p className="text-sm font-medium text-muted-foreground">
                                    {search ? "No matches found" : "No documents yet"}
                                </p>
                                <p className="text-xs text-muted-foreground/60 mt-1">
                                    {search ? "Try a different search term" : "Upload a PDF to get started"}
                                </p>
                            </div>
                        </div>
                    ) : (
                        filtered.map((doc) => {
                            const isSelected = selectedDocs.includes(doc.name);
                            const isReady = doc.status === "ready";
                            const isIndexing = doc.status === "indexing";
                            const isFailed = doc.status === "failed";

                            return (
                                <div
                                    key={doc.name}
                                    className={`group flex items-center gap-2.5 rounded-lg px-2.5 py-2 transition-all duration-150 cursor-pointer ${isSelected
                                        ? "bg-accent"
                                        : "hover:bg-muted/60"
                                        } ${!isReady ? "opacity-60 cursor-not-allowed" : ""}`}
                                    onClick={() => isReady && toggleDocumentSelection(doc.name)}
                                >
                                    {/* Checkbox */}
                                    <div className={`h-4 w-4 shrink-0 rounded border flex items-center justify-center transition-all ${isSelected
                                        ? "bg-primary border-primary text-primary-foreground"
                                        : "border-muted-foreground/40 group-hover:border-muted-foreground/60"
                                        }`}>
                                        {isSelected && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
                                    </div>

                                    {/* Document Info */}
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate text-foreground" title={doc.name}>
                                            {highlightMatch(doc.name, search)}
                                        </p>
                                        {isIndexing && (
                                            <p className="text-[10px] text-blue-500 flex items-center gap-1 mt-0.5">
                                                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                                                Indexing...
                                            </p>
                                        )}
                                        {isFailed && (
                                            <p className="text-[10px] text-destructive mt-0.5" title={doc.error}>
                                                Failed to process
                                            </p>
                                        )}
                                    </div>

                                    {/* Actions */}
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg"
                                            >
                                                <MoreHorizontal className="h-4 w-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end" className="rounded-xl">
                                            <DropdownMenuItem onClick={() => reindexFile(doc.name)} className="rounded-lg">
                                                <RefreshCw className="mr-2 h-4 w-4" /> Re-index
                                            </DropdownMenuItem>
                                            <DropdownMenuItem
                                                onClick={() => setDeleteTarget(doc.name)}
                                                className="text-destructive focus:text-destructive rounded-lg"
                                            >
                                                <Trash2 className="mr-2 h-4 w-4" /> Delete
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            );
                        })
                    )}
                </div>
            </ScrollArea>

            {/* Footer / Context Info */}
            <div className="p-3 border-t bg-background/50 backdrop-blur-sm">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
                        <span className="text-[11px] font-medium text-muted-foreground">System Ready</span>
                    </div>
                    <span className="text-[11px] font-semibold text-primary">
                        {selectedDocs.length}/{documents.length} active
                    </span>
                </div>
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

import { useUser } from "@/contexts/UserContext";
import { LogOut } from "lucide-react";

export function TopBar() {
    const { username, logout } = useUser();

    return (
        <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background px-4 sm:px-6 shadow-sm">
            <Sheet>
                <SheetTrigger asChild>
                    <Button size="icon" variant="ghost" className="md:hidden">
                        <Menu className="h-5 w-5" />
                        <span className="sr-only">Toggle Menu</span>
                    </Button>
                </SheetTrigger>
                <SheetContent side="left" className="sm:max-w-xs p-0">
                    <Sidebar />
                </SheetContent>
            </Sheet>

            <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Zap className="h-5 w-5 fill-current" />
                </div>
                <h1 className="text-lg font-bold tracking-tight hidden md:inline-block">
                    MultiPDF <span className="text-primary">Assistant</span>
                </h1>
            </div>

            <div className="flex-1" />

            <div className="flex items-center gap-3">
                {/* Welcome Message */}
                {username && (
                    <span className="text-sm font-medium hidden sm:inline-block text-muted-foreground">
                        Hi, <span className="text-foreground">{username}</span>
                    </span>
                )}

                {/* Theme Toggle placeholder */}
                <Button variant="ghost" size="icon" className="text-muted-foreground">
                    <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                    <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                    <span className="sr-only">Toggle theme</span>
                </Button>

                <Button
                    variant="ghost"
                    size="icon"
                    className="text-muted-foreground hover:text-destructive transition-colors"
                    onClick={logout}
                    title="Sign out"
                >
                    <LogOut className="h-5 w-5" />
                </Button>

                <Button variant="ghost" size="icon" className="rounded-full">
                    <Avatar className="h-8 w-8 border bg-primary/5">
                        <AvatarImage src="" alt={`@${username}`} />
                        <AvatarFallback className="font-semibold text-primary">
                            {username ? username.charAt(0).toUpperCase() : "U"}
                        </AvatarFallback>
                    </Avatar>
                </Button>
            </div>
        </header>
    );
}

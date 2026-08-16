import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, RotateCcw, HelpCircle, Download, Trophy, ArrowRight, Play, AlertCircle, FileText } from "lucide-react";
import { generateQuiz, type QuizResponse } from "@/lib/api";
import { useDocuments } from "@/contexts/DocumentContext";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

export function QuizPage() {
    const { toast } = useToast();
    const { selectedDocs } = useDocuments();
    const [quiz, setQuiz] = useState<QuizResponse | null>(null);
    const [currentQIndex, setCurrentQIndex] = useState(0);
    const [userAnswers, setUserAnswers] = useState<Record<number, number>>({});
    const [isQuizFinished, setIsQuizFinished] = useState(false);
    const [loading, setLoading] = useState(false);
    const [explanationVisible, setExplanationVisible] = useState(false);

    // Loading State
    const [loadingMessage, setLoadingMessage] = useState("Initializing...");
    const [loadingProgress, setLoadingProgress] = useState(0);

    // Effect for loading animation
    useEffect(() => {
        if (!loading) {
            setLoadingProgress(0);
            return;
        }

        const messages = [
            "Reading document content...",
            "Analyzing key concepts...",
            "Identifying important facts...",
            "Drafting questions...",
            "Verifying answers...",
            "Finalizing quiz..."
        ];

        let msgIndex = 0;
        setLoadingMessage(messages[0]);

        // Message cycler
        const msgInterval = setInterval(() => {
            msgIndex = (msgIndex + 1) % messages.length;
            setLoadingMessage(messages[msgIndex]);
        }, 3000);

        // Progress bar simulation (0 to 90%)
        const progressInterval = setInterval(() => {
            setLoadingProgress(prev => {
                if (prev >= 90) return prev;
                return prev + (Math.random() * 5);
            });
        }, 800);

        return () => {
            clearInterval(msgInterval);
            clearInterval(progressInterval);
        };
    }, [loading]);

    // Determine mode based on selection
    const mode = selectedDocs.length === 1 ? "document" : "library";
    const targetDoc = selectedDocs.length === 1 ? selectedDocs[0] : null;

    const startQuiz = async () => {
        setLoading(true);
        setQuiz(null);
        setCurrentQIndex(0);
        setUserAnswers({});
        setIsQuizFinished(false);
        setExplanationVisible(false);

        try {
            const res = await generateQuiz(targetDoc || undefined, 5);
            setQuiz(res);
        } catch (err) {
            const message = err instanceof Error ? err.message : "Quiz generation failed";
            toast({ title: "Error", description: message, variant: "destructive" });
        } finally {
            setLoading(false);
        }
    };

    const handleAnswer = (optionIndex: number) => {
        if (userAnswers[currentQIndex] !== undefined) return; // Prevent changing answer

        setUserAnswers((prev) => ({ ...prev, [currentQIndex]: optionIndex }));
        setExplanationVisible(true);
    };

    const handleNext = () => {
        if (!quiz) return;

        if (currentQIndex < quiz.mcqs.length - 1) {
            setCurrentQIndex((prev) => prev + 1);
            setExplanationVisible(false); // Hide explanation for next Q
        } else {
            setIsQuizFinished(true);
        }
    };

    const handleRestart = () => {
        setQuiz(null);
        setCurrentQIndex(0);
        setUserAnswers({});
        setIsQuizFinished(false);
        setExplanationVisible(false);
    };

    const handleDownloadPDF = async () => {
        if (!quiz) return;

        try {
            const { jsPDF } = await import("jspdf");
            const doc = new jsPDF();

            // Title
            doc.setFontSize(20);
            doc.text(`MCQ Quiz - ${targetDoc || "Library Quiz"}`, 15, 20);

            doc.setFontSize(10);
            doc.setTextColor(100);
            doc.text(`Generated on ${new Date().toLocaleDateString()}`, 15, 28);

            let y = 40; // Start Y position
            const pageHeight = doc.internal.pageSize.height;
            const margin = 15;
            const contentWidth = 180; // A4 width (210) - 2 * margin (15)

            quiz.mcqs.forEach((q, idx) => {
                // Check if we need a new page
                if (y > pageHeight - 40) {
                    doc.addPage();
                    y = 20;
                }

                // Question
                doc.setFontSize(12);
                doc.setTextColor(0);
                doc.setFont("helvetica", "bold");

                // Wrap text manually
                const questionLines = doc.splitTextToSize(`Q${idx + 1}. ${q.question}`, contentWidth);
                doc.text(questionLines, margin, y);
                y += (questionLines.length * 7) + 2;

                // Options
                doc.setFontSize(11);
                doc.setFont("helvetica", "normal");
                q.options.forEach((opt, optIdx) => {
                    const prefix = String.fromCharCode(65 + optIdx);
                    // access state directly since we are in the component
                    const isUserSelected = userAnswers[idx] === optIdx;
                    const isCorrect = q.correct_index === optIdx;

                    let status = "";
                    if (isUserSelected) status += " (Your Answer)";
                    if (isCorrect) status += " (Correct)";

                    const optText = `- ${prefix}. ${opt}${status}`;
                    const optLines = doc.splitTextToSize(optText, contentWidth - 5);

                    // Simple color logic for text 
                    if (isCorrect) doc.setTextColor(0, 128, 0); // Green
                    else if (isUserSelected && !isCorrect) doc.setTextColor(200, 0, 0); // Red
                    else doc.setTextColor(60); // Gray

                    doc.text(optLines, margin + 5, y);
                    y += (optLines.length * 6);
                });

                // Explanation & Citations
                y += 2;
                doc.setTextColor(0);
                doc.setFontSize(10);

                const expText = `Explanation: ${q.explanation}`;
                const expLines = doc.splitTextToSize(expText, contentWidth);
                doc.text(expLines, margin, y);
                y += (expLines.length * 5) + 5;

                // Separator
                doc.setDrawColor(200);
                doc.line(margin, y, margin + contentWidth, y);
                y += 10;
            });

            doc.save(`Quiz_Results_${new Date().toISOString().split('T')[0]}.pdf`);
            toast({ title: "Success", description: "PDF downloaded successfully." });

        } catch (error) {
            console.error(error);
            toast({ title: "Error", description: "Failed to generate PDF.", variant: "destructive" });
        }
    };

    // --- RENDER STATES ---

    if (selectedDocs.length === 0) {
        return (
            <div className="p-8 max-w-4xl mx-auto">
                <Alert variant="destructive" className="animate-in fade-in slide-in-from-top-2">
                    <HelpCircle className="h-4 w-4" />
                    <AlertTitle>No Documents Selected</AlertTitle>
                    <AlertDescription>
                        Please select at least one document from the sidebar to start a quiz.
                    </AlertDescription>
                </Alert>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="h-full flex flex-col items-center justify-center p-8 space-y-8 animate-in fade-in zoom-in-95 duration-500">
                <div className="relative">
                    <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full animate-pulse"></div>
                    <div className="bg-background relative p-6 rounded-full shadow-xl border-4 border-muted">
                        <RotateCcw className="h-12 w-12 text-primary animate-spin" style={{ animationDuration: "3s" }} />
                    </div>
                </div>

                <div className="space-y-4 text-center max-w-md w-full">
                    <h2 className="text-2xl font-bold tracking-tight animate-pulse">{loadingMessage}</h2>
                    <Progress value={loadingProgress} className="h-2 w-full transition-all duration-500" />
                    <p className="text-sm text-muted-foreground">This may take a few seconds...</p>
                </div>
            </div>
        );
    }

    // 1. Start Screen
    if (!quiz) {
        return (
            <div className="h-full flex items-center justify-center p-6">
                <div className="flex flex-col items-center justify-center space-y-6 border border-dashed rounded-2xl bg-muted/5 p-12 max-w-md w-full text-center hover:bg-muted/10 transition-colors">
                    <div className="bg-primary/10 w-20 h-20 rounded-full flex items-center justify-center mb-2 shadow-sm">
                        <Trophy className="h-10 w-10 text-primary" />
                    </div>
                    <div className="space-y-2">
                        <h2 className="text-2xl font-bold tracking-tight">Knowledge Check</h2>
                        <p className="text-muted-foreground text-sm">
                            {mode === "document"
                                ? `Generate a 5-question quiz based on "${targetDoc}".`
                                : "Generate a quiz from your entire document library."}
                        </p>
                    </div>
                    <Button size="lg" onClick={startQuiz} disabled={loading} className="w-full gap-2 font-semibold shadow-md">
                        <Play className="h-4 w-4 fill-current" /> Start Quiz
                    </Button>
                </div>
            </div>
        );
    }

    // Calculate Stats
    const totalQuestions = quiz.mcqs.length;
    const correctCount = Object.values(userAnswers).reduce((acc, ans, idx) => {
        return ans === quiz.mcqs[idx].correct_index ? acc + 1 : acc;
    }, 0);
    const scorePercentage = Math.round((correctCount / totalQuestions) * 100);

    // 2. Summary Screen (End)
    if (isQuizFinished) {
        return (
            // Added pb-20 to ensure bottom buttons are never cut off by screen edges
            <div className="min-h-full max-w-4xl mx-auto p-6 space-y-8 animate-in fade-in zoom-in-95 duration-300 relative pb-20">
                {/* 
                   PDF GENERATION CONTAINER 
                   Fix for "Empty PDF": 
                   1. Use 'fixed' + 'left-[200vw]' to move it safely off-screen without coordinate issues.
                   2. strictly visible (opacity-100) and high z-index to ensure html2canvas captures it.
                   3. bg-white ensures no transparency issues.
                */}
                <div className="fixed top-0 left-[200vw] w-[210mm] min-h-[297mm] bg-white text-black p-12 z-50 pointer-events-none">
                    <div className="mb-8 border-b pb-4">
                        <h1 className="text-3xl font-bold mb-2">MCQ Quiz — {targetDoc || "Library Quiz"}</h1>
                        <p className="text-gray-600">Generated on {new Date().toLocaleDateString()}</p>
                    </div>

                    <div className="space-y-8">
                        {quiz.mcqs.map((q, idx) => (
                            <div key={idx} className="break-inside-avoid">
                                <p className="font-bold text-lg mb-3">Q{idx + 1}. {q.question}</p>
                                <div className="space-y-1 mb-3 ml-4">
                                    {q.options.map((opt, optIdx) => (
                                        <div key={optIdx} className="flex gap-2 text-base">
                                            <span className="font-semibold w-6">- {String.fromCharCode(65 + optIdx)}.</span>
                                            <span>{opt}</span>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-gray-50 p-4 rounded-lg border text-sm space-y-2">
                                    <p><span className="font-bold text-green-700">Correct:</span> {String.fromCharCode(65 + q.correct_index)}</p>
                                    <p><span className="font-bold">Explanation:</span> {q.explanation}</p>
                                    {q.citations && q.citations.length > 0 && (
                                        <p className="text-gray-500 text-xs italic">
                                            Citations: {q.citations.map(c => `${c.doc} p${c.page}`).join(", ")}
                                        </p>
                                    )}
                                </div>
                                <hr className="mt-6 border-gray-200" />
                            </div>
                        ))}
                    </div>

                    <div className="mt-8 text-center text-sm text-gray-400">
                        Generated by Multi-PDF RAG Assistant
                    </div>
                </div>

                {/* Visible UI */}
                <div className="text-center space-y-4">
                    <div className="inline-flex items-center justify-center p-4 bg-background rounded-full shadow-lg border-4 border-muted">
                        <span className={`text-4xl font-extrabold ${scorePercentage >= 70 ? "text-green-500" : "text-yellow-500"}`}>
                            {scorePercentage}%
                        </span>
                    </div>
                    <div>
                        <h2 className="text-3xl font-bold">Quiz Complete!</h2>
                        <p className="text-muted-foreground">You scored {correctCount} out of {totalQuestions}</p>
                    </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                    {quiz.mcqs.map((q, idx) => {
                        const userAns = userAnswers[idx];
                        const isCorrect = userAns === q.correct_index;
                        return (
                            <Card key={idx} className={`border-l-4 ${isCorrect ? "border-l-green-500" : "border-l-destructive"}`}>
                                <CardHeader className="p-4 py-3">
                                    <CardTitle className="text-sm font-medium leading-normal flex justify-between gap-2">
                                        <span>Q{idx + 1}. {q.question}</span>
                                        {isCorrect
                                            ? <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
                                            : <XCircle className="h-5 w-5 text-destructive shrink-0" />}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="p-4 pt-0 text-xs text-muted-foreground">
                                    <div className="flex flex-col gap-1">
                                        <span>Your answer: <span className={isCorrect ? "font-semibold text-green-600" : "font-semibold text-destructive line-through"}>{q.options[userAns]}</span></span>
                                        {!isCorrect && <span className="font-semibold text-green-600">Correct: {q.options[q.correct_index]}</span>}
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })}
                </div>

                <div className="flex justify-center gap-6 pt-8 mt-4 border-t">
                    <Button onClick={handleRestart} variant="outline" size="lg" className="gap-2 px-8">
                        <RotateCcw className="h-4 w-4" /> Restart
                    </Button>
                    <Button onClick={handleDownloadPDF} variant="default" size="lg" className="gap-2 px-8">
                        <Download className="h-4 w-4" /> Export PDF
                    </Button>
                </div>
            </div>
        );
    }

    // 3. Question Screen (Active)
    const currentQuestion = quiz.mcqs[currentQIndex];

    if (!currentQuestion) {
        return (
            <div className="flex flex-col items-center justify-center p-6 space-y-4">
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Quiz Error</AlertTitle>
                    <AlertDescription>
                        No questions were generated. Please try again or select a different document.
                    </AlertDescription>
                </Alert>
                <Button onClick={handleRestart} variant="outline">
                    <RotateCcw className="h-4 w-4 mr-2" /> Try Again
                </Button>
            </div>
        );
    }

    const userAnswer = userAnswers[currentQIndex];
    const isAnswered = userAnswer !== undefined;
    const isCorrect = userAnswer === currentQuestion.correct_index;

    return (
        <div className="h-full flex flex-col max-w-3xl mx-auto p-6 space-y-6 w-full">
            {/* Header Progress */}
            <div className="space-y-2">
                <div className="flex justify-between text-sm font-medium text-muted-foreground">
                    <span>Question {currentQIndex + 1} of {totalQuestions}</span>
                    <span>Score: {correctCount}</span>
                </div>
                <Progress value={((currentQIndex + (isAnswered ? 1 : 0)) / totalQuestions) * 100} className="h-2" />
            </div>

            <Card className="flex-1 flex flex-col shadow-md border-0 bg-card/50 backdrop-blur-sm ring-1 ring-border/50">
                <CardHeader className="pb-6">
                    <CardTitle className="text-xl leading-relaxed text-foreground font-semibold">
                        {currentQuestion.question}
                    </CardTitle>
                </CardHeader>

                <CardContent className="flex-1 space-y-3">
                    <div className="grid gap-3">
                        {currentQuestion.options.map((opt, optIdx) => {
                            let className = "relative justify-start text-left h-auto py-4 px-5 text-base transition-all duration-200 border bg-card hover:bg-accent hover:border-accent";

                            // Visual Logic
                            if (isAnswered) {
                                if (optIdx === currentQuestion.correct_index) {
                                    className = "relative justify-start text-left h-auto py-4 px-5 text-base border-green-200 bg-green-50 text-green-800 hover:bg-green-100 dark:bg-green-900/20 dark:border-green-800 dark:text-green-300";
                                } else if (optIdx === userAnswer && !isCorrect) {
                                    className = "relative justify-start text-left h-auto py-4 px-5 text-base border-red-200 bg-red-50 text-red-800 hover:bg-red-100 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300";
                                } else {
                                    className += " opacity-40 cursor-not-allowed";
                                }
                            } else {
                                // Default hover state is already in base class
                            }

                            return (
                                <button
                                    key={optIdx}
                                    className={`w-full rounded-xl flex items-center group ${className} ${isAnswered ? 'cursor-default' : 'cursor-pointer'}`}
                                    onClick={() => !isAnswered && handleAnswer(optIdx)}
                                    disabled={isAnswered}
                                >
                                    <span className={`mr-4 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border transition-colors ${isAnswered && optIdx === currentQuestion.correct_index
                                        ? "bg-green-500 text-white border-green-600"
                                        : isAnswered && optIdx === userAnswer && !isCorrect
                                            ? "bg-red-500 text-white border-red-600"
                                            : "bg-muted text-muted-foreground border-border group-hover:border-primary/50"
                                        }`}>
                                        {String.fromCharCode(65 + optIdx)}
                                    </span>
                                    <span className="flex-1 font-medium">{opt}</span>

                                    {isAnswered && optIdx === currentQuestion.correct_index && (
                                        <CheckCircle2 className="h-5 w-5 text-green-600 ml-2" />
                                    )}
                                    {isAnswered && optIdx === userAnswer && !isCorrect && (
                                        <XCircle className="h-5 w-5 text-red-600 ml-2" />
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    {/* Explanation - Animated Reveal */}
                    {explanationVisible && (
                        <div className="mt-6 p-5 bg-muted/30 rounded-xl border animate-in fade-in slide-in-from-top-2">
                            <div className="flex gap-2 items-start">
                                <FileText className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                                <div className="space-y-1">
                                    <h4 className="font-semibold text-sm text-foreground">Explanation</h4>
                                    <p className="text-sm text-muted-foreground leading-relaxed">
                                        {currentQuestion.explanation}
                                    </p>
                                    {currentQuestion.citations && currentQuestion.citations.length > 0 && (
                                        <Badge variant="outline" className="mt-2 text-[10px] font-normal text-muted-foreground">
                                            Source: {currentQuestion.citations[0].doc} (p. {currentQuestion.citations[0].page})
                                        </Badge>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </CardContent>

                <CardFooter className="pt-2 pb-6 flex justify-end">
                    <Button
                        onClick={handleNext}
                        disabled={!isAnswered}
                        className="w-full md:w-auto gap-2 px-8 transition-all"
                        size="lg"
                    >
                        {currentQIndex === quiz.mcqs.length - 1 ? "View Results" : "Next Question"}
                        <ArrowRight className="h-4 w-4" />
                    </Button>
                </CardFooter>
            </Card>
        </div>
    );
}

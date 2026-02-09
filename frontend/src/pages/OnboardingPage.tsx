
import { useState } from "react";
import { useUser } from "@/contexts/UserContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowRight, Sparkles, Zap } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export function OnboardingPage() {
    const { updateUser } = useUser();
    const [name, setName] = useState("");
    const [step, setStep] = useState(0);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (name.trim()) {
            setStep(1);
            // Delay actual update to allow exit animation
            setTimeout(() => updateUser(name), 1000);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 p-4 overflow-hidden relative">
            {/* Background Decorations */}
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl -z-10 animate-pulse duration-[5000ms]" />
            <div className="absolute bottom-1/4 right-1/4 w-64 h-64 bg-secondary/20 rounded-full blur-3xl -z-10 animate-pulse duration-[7000ms]" />

            <AnimatePresence mode="wait">
                {step === 0 ? (
                    <motion.div
                        key="intro"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95 }}
                        transition={{ duration: 0.5, ease: "easeOut" }}
                        className="w-full max-w-lg text-center space-y-8"
                    >
                        <motion.div
                            initial={{ scale: 0.8 }}
                            animate={{ scale: 1 }}
                            transition={{ delay: 0.2, type: "spring" }}
                            className="w-24 h-24 bg-gradient-to-tr from-primary/10 to-primary/5 rounded-3xl flex items-center justify-center mx-auto mb-8 ring-1 ring-primary/20 shadow-xl shadow-primary/5"
                        >
                            <Zap className="w-12 h-12 text-primary fill-current" />
                        </motion.div>

                        <div className="space-y-4">
                            <motion.h1
                                className="text-4xl md:text-5xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-primary to-primary/60 pb-2"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: 0.3 }}
                            >
                                Welcome to MultiPDF Assistant
                            </motion.h1>
                            <motion.p
                                className="text-muted-foreground text-xl"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ delay: 0.4 }}
                            >
                                Let's get you set up. What should we call you?
                            </motion.p>
                        </div>

                        <motion.form
                            onSubmit={handleSubmit}
                            className="space-y-4"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.5 }}
                        >
                            <div className="relative group">
                                <Input
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    placeholder="Enter your name..."
                                    className="h-14 text-lg text-center bg-background/50 border-2 focus:border-primary transition-all rounded-xl shadow-sm hover:bg-background/80"
                                    autoFocus
                                />
                            </div>

                            <Button
                                size="lg"
                                className="w-full h-12 text-lg rounded-xl gap-2 shadow-lg hover:shadow-primary/25 transition-all"
                                disabled={!name.trim()}
                            >
                                Get Started <ArrowRight className="w-5 h-5" />
                            </Button>
                        </motion.form>
                    </motion.div>
                ) : (
                    <motion.div
                        key="success"
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="text-center space-y-4"
                    >
                        <div className="w-24 h-24 bg-green-500/10 rounded-full flex items-center justify-center mx-auto">
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ type: "spring", delay: 0.2 }}
                            >
                                <Sparkles className="w-12 h-12 text-green-500" />
                            </motion.div>
                        </div>
                        <h2 className="text-2xl font-semibold">Perfect! Welcome aboard, {name}.</h2>
                        <p className="text-muted-foreground">Setting up your workspace...</p>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

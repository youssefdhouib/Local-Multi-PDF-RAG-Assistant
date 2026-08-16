
import { createContext, useContext, useState, type ReactNode } from "react";

interface UserContextType {
    username: string | null;
    isOnboarded: boolean;
    updateUser: (name: string) => void;
    logout: () => void;
}

function readStoredUser(): { username: string | null; isOnboarded: boolean } {
    const savedName = localStorage.getItem("rag_username");
    const onboarded = localStorage.getItem("rag_onboarded") === "true";
    if (savedName && onboarded) {
        return { username: savedName, isOnboarded: true };
    }
    return { username: null, isOnboarded: false };
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export function UserProvider({ children }: { children: ReactNode }) {
    const [username, setUsername] = useState<string | null>(readStoredUser().username);
    const [isOnboarded, setIsOnboarded] = useState<boolean>(readStoredUser().isOnboarded);

    const updateUser = (name: string) => {
        const trimmed = name.trim();
        if (!trimmed) return;

        setUsername(trimmed);
        setIsOnboarded(true);
        localStorage.setItem("rag_username", trimmed);
        localStorage.setItem("rag_onboarded", "true");
    };

    const logout = () => {
        setUsername(null);
        setIsOnboarded(false);
        localStorage.removeItem("rag_username");
        localStorage.removeItem("rag_onboarded");
    };

    return (
        <UserContext.Provider value={{ username, isOnboarded, updateUser, logout }}>
            {children}
        </UserContext.Provider>
    );
}

export function useUser() {
    const context = useContext(UserContext);
    if (context === undefined) {
        throw new Error("useUser must be used within a UserProvider");
    }
    return context;
}

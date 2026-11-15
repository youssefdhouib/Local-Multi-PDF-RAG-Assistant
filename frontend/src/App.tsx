import { useState } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChatPage } from "@/pages/ChatPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { SummaryPage } from "@/pages/SummaryPage";
import { QuizPage } from "@/pages/QuizPage";
import { OnboardingPage } from "@/pages/OnboardingPage"; // Import Onboarding
import { MessageSquare, Files, BookOpen, GraduationCap } from "lucide-react";
import { DocumentProvider, useDocuments } from "@/contexts/DocumentContext";
import { Sidebar, TopBar } from "@/components/Layout";
import { ChatProvider } from "@/contexts/ChatContext";
import { UserProvider, useUser } from "@/contexts/UserContext"; // Import User Context

function AppContent() {
  const { isOnboarded } = useUser();
  const [activeTab, setActiveTab] = useState("chat");
  const { selectedDocs } = useDocuments();
  const selectionKey = selectedDocs.join("|");

  if (!isOnboarded) {
    return <OnboardingPage />;
  }

  const handleNavigate = (page: string) => {
    setActiveTab(page);
  };

  return (
    <div className="flex h-screen overflow-hidden flex-col bg-background animate-in fade-in duration-700">
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        <div className="hidden border-r bg-muted/40 md:block w-64 lg:w-72">
          <Sidebar />
        </div>

        <main className="flex flex-1 flex-col overflow-hidden">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col h-full">
            <div className="border-b px-4 py-2">
              <TabsList className="grid w-full max-w-md grid-cols-4">
                <TabsTrigger value="chat"><MessageSquare className="h-4 w-4 mr-2" /> Chat</TabsTrigger>
                <TabsTrigger value="documents"><Files className="h-4 w-4 mr-2" /> Docs</TabsTrigger>
                <TabsTrigger value="summary"><BookOpen className="h-4 w-4 mr-2" /> Summary</TabsTrigger>
                <TabsTrigger value="quiz"><GraduationCap className="h-4 w-4 mr-2" /> Quiz</TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-hidden p-4 lg:p-6">
              <TabsContent value="chat" className="h-full m-0 data-[state=active]:flex data-[state=active]:flex-col">
                <ChatPage />
              </TabsContent>
              <TabsContent value="documents" className="h-full overflow-auto m-0">
                <DocumentsPage onNavigate={handleNavigate} />
              </TabsContent>
              {/*
                forceMount: keep Summary and Quiz alive when you switch tabs (only hide them),
                so a generated summary, a quiz in progress, or a running request is not lost.
                key: when the selected PDFs change, React starts these pages fresh, so you never
                see one document's summary or quiz under another document's name.
              */}
              <TabsContent value="summary" forceMount className="h-full overflow-hidden m-0 data-[state=inactive]:hidden">
                <SummaryPage key={selectionKey} />
              </TabsContent>
              <TabsContent value="quiz" forceMount className="h-full overflow-hidden m-0 data-[state=inactive]:hidden">
                <QuizPage key={selectionKey} />
              </TabsContent>
            </div>
          </Tabs>
        </main>
      </div>
      <Toaster />
    </div>
  );
}

export default function App() {
  return (
    <UserProvider>
      <DocumentProvider>
        <ChatProvider>
          <AppContent />
        </ChatProvider>
      </DocumentProvider>
    </UserProvider>
  );
}

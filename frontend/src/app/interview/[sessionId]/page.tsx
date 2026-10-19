import InterviewView from "@/components/InterviewView";

export default async function InterviewPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-6 py-12">
      <InterviewView sessionId={sessionId} />
    </main>
  );
}

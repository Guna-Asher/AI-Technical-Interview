import type { Metadata } from "next";
import InterviewView from "@/components/InterviewView";

export const metadata: Metadata = { title: "Your interview" };

export default async function InterviewPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6 sm:py-12">
      <InterviewView sessionId={sessionId} />
    </div>
  );
}

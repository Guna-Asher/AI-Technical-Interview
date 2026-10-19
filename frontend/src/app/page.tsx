import BackendStatus from "@/components/BackendStatus";
import StartInterviewForm from "@/components/StartInterviewForm";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col gap-6 px-6 py-12">
      <h1 className="text-3xl font-semibold">AI Technical Interview</h1>
      <p className="text-slate-600">
        Enter the role you are interviewing for and upload your resume. The questions are generated from your resume
        and from technical reference material.
      </p>
      <StartInterviewForm />
      <footer className="mt-auto pt-8">
        <BackendStatus />
      </footer>
    </main>
  );
}

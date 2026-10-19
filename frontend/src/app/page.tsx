import BackendStatus from "@/components/BackendStatus";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-semibold">AI Technical Interview</h1>
      <p className="text-slate-600">
        Upload your resume, pick a role, and practise with questions grounded in technical
        reference material.
      </p>
      <BackendStatus />
    </main>
  );
}

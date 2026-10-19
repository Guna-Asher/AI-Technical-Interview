"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { ApiError, createInterview, uploadResume } from "@/lib/api";

type Step = "idle" | "creating" | "reading";

const STEP_LABEL: Record<Step, string> = {
  idle: "",
  creating: "Creating your interview…",
  reading: "Reading your resume… this can take a little while.",
};

export default function StartInterviewForm() {
  const router = useRouter();
  const [role, setRole] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [error, setError] = useState<string | null>(null);
  // The session created for the current role. Kept so that retrying a failed resume upload
  // reuses it instead of creating another interview.
  const [created, setCreated] = useState<{ id: string; role: string } | null>(null);
  const busy = useRef(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    const trimmedRole = role.trim();
    if (!trimmedRole || !file) {
      setError("Enter the job role and choose a resume file (PDF or TXT).");
      return;
    }
    busy.current = true;
    setError(null);
    try {
      let session = created;
      if (!session || session.role !== trimmedRole) {
        setStep("creating");
        session = { id: (await createInterview(trimmedRole)).id, role: trimmedRole };
        setCreated(session);
      }
      setStep("reading");
      await uploadResume(session.id, file);
      router.push(`/interview/${session.id}`); // stay disabled while navigating
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setStep("idle");
      busy.current = false;
    }
  }

  const pending = step !== "idle";
  const retrying = created !== null && error !== null;

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="role" className="text-sm font-medium">
          Job role
        </label>
        <input
          id="role"
          type="text"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          maxLength={100}
          autoComplete="off"
          disabled={pending}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="resume" className="text-sm font-medium">
          Resume (PDF or TXT)
        </label>
        <input
          id="resume"
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          disabled={pending}
          className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-200 file:px-3 file:py-2"
        />
      </div>

      {error && (
        <p role="alert" className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
      {pending && (
        <p role="status" className="text-sm text-slate-600">
          {STEP_LABEL[step]}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-md bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
      >
        {pending ? "Working…" : retrying ? "Try again" : "Continue"}
      </button>
    </form>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { IconFile, IconUpload } from "@/components/icons";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { ProgressStripe } from "@/components/ui/Spinner";
import { ApiError, createInterview, uploadResume } from "@/lib/api";

type Step = "idle" | "creating" | "reading";

const STEP_LABEL: Record<Step, string> = {
  idle: "",
  creating: "Creating your interview…",
  reading: "Reading your resume… this can take a little while.",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const FIELD =
  "min-h-11 w-full rounded-lg border border-edge bg-paper px-3.5 text-base disabled:bg-mist disabled:text-graphite aria-invalid:border-brick aria-invalid:bg-brick-tint/40";

export default function StartInterviewForm() {
  const router = useRouter();
  const [role, setRole] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>("idle");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState({ role: false, file: false });
  const [dragging, setDragging] = useState(false);
  // The session created for the current role. Kept so that retrying a failed resume upload
  // reuses it instead of creating another interview.
  const [created, setCreated] = useState<{ id: string; role: string } | null>(null);
  const busy = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);

  function chooseFile(next: File | null) {
    setFile(next);
    if (next) setInvalid((v) => ({ ...v, file: false }));
  }

  function removeFile() {
    setFile(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (step !== "idle") return;
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) chooseFile(dropped);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    const trimmedRole = role.trim();
    if (!trimmedRole || !file) {
      setInvalid({ role: !trimmedRole, file: !file });
      setError("Enter the job role and choose a resume file (PDF or TXT).");
      return;
    }
    busy.current = true;
    setError(null);
    setInvalid({ role: false, file: false });
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
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex min-w-0 flex-col gap-6 self-start rounded-xl border border-rule bg-paper p-5 sm:p-7"
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="role" className="font-medium">
          Job role
        </label>
        <input
          id="role"
          type="text"
          value={role}
          onChange={(e) => {
            setRole(e.target.value);
            setInvalid((v) => ({ ...v, role: false }));
          }}
          maxLength={100}
          autoComplete="off"
          disabled={pending}
          aria-invalid={invalid.role || undefined}
          aria-describedby="role-hint"
          className={FIELD}
        />
        <p id="role-hint" className="text-sm text-graphite">
          Type any role, in your own words.
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <span id="resume-title" className="font-medium">
          Resume (PDF or TXT)
        </span>
        <div className="relative">
          <input
            ref={fileInput}
            id="resume"
            type="file"
            accept=".pdf,.txt,application/pdf,text/plain"
            onChange={(e) => chooseFile(e.target.files?.[0] ?? null)}
            disabled={pending}
            tabIndex={file ? -1 : 0}
            aria-labelledby="resume-title"
            aria-describedby="resume-hint"
            aria-invalid={invalid.file || undefined}
            className="peer sr-only"
          />
          {file ? (
            <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-edge bg-mist px-4 py-3 sm:flex-row sm:items-center sm:gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <IconFile className="size-5 text-cobalt" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium" title={file.name}>
                    {file.name}
                  </p>
                  <p className="text-sm text-graphite">{formatSize(file.size)}</p>
                </div>
              </div>
              <div className="flex gap-1 self-end sm:self-auto">
                <Button variant="quiet" onClick={() => fileInput.current?.click()} disabled={pending}>
                  Replace
                </Button>
                <Button variant="quiet" onClick={removeFile} disabled={pending} aria-label="Remove file">
                  Remove
                </Button>
              </div>
            </div>
          ) : (
            <label
              htmlFor="resume"
              onDragOver={(e) => {
                e.preventDefault();
                if (!pending) setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={`flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-6 text-center transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-cobalt peer-disabled:cursor-not-allowed peer-disabled:opacity-60 ${
                invalid.file ? "border-brick bg-brick-tint/40" : dragging ? "border-cobalt bg-cobalt-tint" : "border-edge bg-paper hover:bg-mist"
              }`}
            >
              <IconUpload className="size-5 text-cobalt" />
              <span>
                <span className="font-medium text-cobalt">Choose a file</span> or drop it here
              </span>
            </label>
          )}
        </div>
        <p id="resume-hint" className="text-sm text-graphite">
          PDF or plain text. The text is sent to the AI model to read your background; the file itself is not stored.
        </p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {pending && (
        <div className="flex flex-col gap-3" role="status">
          <p className="text-sm text-graphite">{STEP_LABEL[step]}</p>
          <ProgressStripe />
        </div>
      )}

      <Button type="submit" disabled={pending} loading={pending} className="w-full sm:w-auto sm:self-start">
        {pending ? "Working…" : retrying ? "Try again" : "Continue"}
      </Button>
    </form>
  );
}

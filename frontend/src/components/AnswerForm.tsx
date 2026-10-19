"use client";

import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { ApiError, submitAnswer } from "@/lib/api";
import type { Answer, Question } from "@/lib/types";

interface Props {
  sessionId: string;
  question: Question;
  /** Called with the saved answer, only after the backend has stored it. */
  onSaved: (answer: Answer) => void;
  /** Called when the backend says the question was already answered (for example from another tab). */
  onAlreadyAnswered: () => void;
}

export default function AnswerForm({ sessionId, question, onSaved, onAlreadyAnswered }: Props) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const form = useRef<HTMLFormElement>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy.current) return;
    if (!text.trim()) {
      setError("Write an answer before submitting.");
      return;
    }
    busy.current = true;
    setPending(true);
    setError(null);
    try {
      onSaved(await submitAnswer(sessionId, question.id, text));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        onAlreadyAnswered();
      } else {
        // The typed text stays in the box so nothing is lost; the candidate can try again.
        setError(err instanceof ApiError ? err.message : "Your answer could not be saved. Please try again.");
        busy.current = false;
        setPending(false);
      }
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      form.current?.requestSubmit();
    }
  }

  const hintId = `answer-hint-${question.id}`;
  return (
    <form ref={form} onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
      <label htmlFor={`answer-${question.id}`} className="font-medium">
        Your answer
      </label>
      <textarea
        id={`answer-${question.id}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        rows={9}
        disabled={pending}
        aria-describedby={hintId}
        className="min-h-48 w-full resize-y rounded-lg border border-edge bg-paper px-3.5 py-3 text-base leading-relaxed disabled:bg-mist disabled:text-graphite"
      />
      {error && <Alert tone="error">{error}</Alert>}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <Button type="submit" disabled={pending} loading={pending} className="w-full sm:w-auto">
          {pending ? "Saving…" : "Submit answer"}
        </Button>
        <p id={hintId} className="text-sm text-graphite">
          Saved as soon as you submit, and kept if you refresh. Press Ctrl or ⌘ and Enter to submit.
        </p>
      </div>
    </form>
  );
}

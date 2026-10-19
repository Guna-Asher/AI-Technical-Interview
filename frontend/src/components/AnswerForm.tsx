"use client";

import { useRef, useState, type FormEvent } from "react";
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

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
      <label htmlFor={`answer-${question.id}`} className="text-sm font-medium">
        Your answer
      </label>
      <textarea
        id={`answer-${question.id}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        disabled={pending}
        className="rounded-md border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
      />
      {error && (
        <p role="alert" className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-md bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50"
      >
        {pending ? "Saving…" : "Submit answer"}
      </button>
    </form>
  );
}

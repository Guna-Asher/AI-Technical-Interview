"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import AnswerForm from "@/components/AnswerForm";
import { IconBook, IconCheck, IconChevronDown } from "@/components/icons";
import ProgressBar from "@/components/ProgressBar";
import ReportView from "@/components/ReportView";
import Alert from "@/components/ui/Alert";
import Button from "@/components/ui/Button";
import { ProgressStripe, Spinner } from "@/components/ui/Spinner";
import Tag from "@/components/ui/Tag";
import { ApiError, completeInterview, generateQuestions, getInterview, getReport, listQuestions } from "@/lib/api";
import type { Answer, Interview, Question, Report } from "@/lib/types";

type State =
  | { status: "loading" }
  | { status: "error"; message: string; httpStatus: number }
  | { status: "ready"; interview: Interview; questions: Question[]; report: Report | null; reportError: string | null };

// The backend is the source of truth: this always reads the saved interview and its questions
// (with any saved answers), so a refresh shows exactly what was stored.
async function fetchState(sessionId: string): Promise<State> {
  try {
    const [interview, questions] = await Promise.all([getInterview(sessionId), listQuestions(sessionId)]);
    if (interview.status !== "completed") return { status: "ready", interview, questions, report: null, reportError: null };
    // A completed interview always has a saved report; reading it makes the results survive a refresh.
    try {
      return { status: "ready", interview, questions, report: await getReport(sessionId), reportError: null };
    } catch (err) {
      const reportError = err instanceof ApiError ? err.message : "The report could not be loaded.";
      return { status: "ready", interview, questions, report: null, reportError };
    }
  } catch (err) {
    if (err instanceof ApiError) return { status: "error", message: err.message, httpStatus: err.status };
    return { status: "error", message: "The interview could not be loaded.", httpStatus: 0 };
  }
}

const LINK = "text-cobalt underline underline-offset-4 hover:text-cobalt-deep";
// The page container is wider for the report; every other state keeps the narrower reading column.
const COLUMN = "mx-auto w-full max-w-[45rem]";

function errorTitle(httpStatus: number): string {
  if (httpStatus === 404) return "We could not find this interview";
  if (httpStatus === 422) return "This interview link is not valid";
  if (httpStatus === 0) return "The service cannot be reached";
  return "The interview could not be loaded";
}

function Sources({ question }: { question: Question }) {
  if (question.source_chunks.length === 0) return null;
  return (
    <p className="flex items-start gap-2 text-sm text-graphite">
      <IconBook className="mt-0.5 size-4" />
      <span>{`Based on: ${question.source_chunks.map((s) => `${s.source_title}, page ${s.page}`).join("; ")}`}</span>
    </p>
  );
}

/** Shown right after an answer is saved; the next question stays hidden until the candidate continues. */
function SavedConfirmation({ position, onContinue }: { position: number; onContinue: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    button.current?.focus();
  }, []);
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-moss/30 bg-moss-tint p-5 sm:p-7">
      <div role="status" className="flex flex-col gap-1">
        <p className="flex items-center gap-2 text-lg font-semibold text-moss">
          <IconCheck className="size-5" />
          <span>Answer saved</span>
        </p>
        <p className="text-graphite">Your answer to question {position} is saved and kept if you refresh.</p>
      </div>
      <Button ref={button} onClick={onContinue} className="w-full sm:w-auto sm:self-start">
        Continue to next question
      </Button>
    </section>
  );
}

export default function InterviewView({ sessionId }: { sessionId: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  // Id of the question whose answer was just saved in this browser. Transient: a refresh discards it.
  const [justSaved, setJustSaved] = useState<string | null>(null);
  const questionHeading = useRef<HTMLHeadingElement>(null);
  const focusQuestion = useRef(false);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const generatingRef = useRef(false);
  const [completing, setCompleting] = useState(false);
  const [completionError, setCompletionError] = useState<string | null>(null);
  const completingRef = useRef(false);

  useEffect(() => {
    let active = true;
    fetchState(sessionId).then((next) => {
      if (!active) return;
      setState(next);
      setJustSaved(null); // a confirmation never carries over from another session
    });
    return () => {
      active = false;
    };
  }, [sessionId]);

  // After Continue, move focus to the question that has just been revealed.
  useEffect(() => {
    if (justSaved === null && focusQuestion.current) {
      focusQuestion.current = false;
      questionHeading.current?.focus();
    }
  }, [justSaved]);

  async function reload() {
    setState(await fetchState(sessionId));
  }

  function retryLoading() {
    setState({ status: "loading" });
    void reload();
  }

  // Questions are only ever generated from this explicit action, never from an effect or a render.
  async function startInterview() {
    if (generatingRef.current) return;
    generatingRef.current = true;
    setGenerating(true);
    setGenerationError(null);
    try {
      const questions = await generateQuestions(sessionId);
      setState((s) => (s.status === "ready" ? { ...s, questions, interview: { ...s.interview, status: "in_progress" } } : s));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await reload(); // questions already exist (generated by an earlier request); show them
      } else {
        setGenerationError(err instanceof ApiError ? err.message : "The questions could not be generated.");
      }
    } finally {
      generatingRef.current = false;
      setGenerating(false);
    }
  }

  // Evaluation and the report are only ever started from this explicit action, never from an effect or a render.
  async function finishInterview() {
    if (completingRef.current) return;
    completingRef.current = true;
    setCompleting(true);
    setCompletionError(null);
    try {
      const report = await completeInterview(sessionId);
      setState((s) =>
        s.status === "ready"
          ? {
              ...s,
              report,
              reportError: null,
              questions: report.questions,
              interview: { ...s.interview, status: "completed", completed_at: report.completed_at },
            }
          : s,
      );
    } catch (err) {
      setCompletionError(err instanceof ApiError ? err.message : "The report could not be created. Please try again.");
    } finally {
      completingRef.current = false;
      setCompleting(false);
    }
  }

  function continueToNext() {
    focusQuestion.current = true;
    setJustSaved(null);
  }

  function answerSaved(questionId: string, answer: Answer) {
    setNotice(null);
    setJustSaved(questionId);
    setState((s) =>
      s.status === "ready"
        ? { ...s, questions: s.questions.map((q) => (q.id === questionId ? { ...q, answer } : q)) }
        : s,
    );
  }

  async function alreadyAnswered() {
    setNotice("This question was already answered, so the saved answer is shown.");
    await reload();
  }

  if (state.status === "loading") {
    return (
      <div role="status" className={`${COLUMN} flex items-center gap-3 text-graphite`}>
        <Spinner />
        <span>Loading your interview…</span>
      </div>
    );
  }

  if (state.status === "error") {
    const canRetry = state.httpStatus === 0 || state.httpStatus >= 500;
    return (
      <div className={`${COLUMN} flex flex-col items-start gap-5`}>
        <h1 className="text-2xl font-semibold">{errorTitle(state.httpStatus)}</h1>
        <Alert tone="error" className="w-full">
          {state.message}
        </Alert>
        <div className="flex flex-wrap items-center gap-4">
          {canRetry && <Button onClick={retryLoading}>Retry</Button>}
          <Link href="/" className={LINK}>
            Start a new interview
          </Link>
        </div>
      </div>
    );
  }

  const { interview, questions } = state;

  if (state.report) return <ReportView report={state.report} />;

  if (interview.status === "completed") {
    return (
      <div className={`${COLUMN} flex flex-col items-start gap-5`}>
        <h1 className="text-2xl font-semibold">The report could not be loaded</h1>
        <Alert tone="error" className="w-full">
          {state.reportError ?? "The report could not be loaded."}
        </Alert>
        <Button onClick={retryLoading}>Retry</Button>
      </div>
    );
  }

  if (!interview.candidate_profile) {
    return (
      <div className={`${COLUMN} flex flex-col items-start gap-4`}>
        <h1 className="text-2xl font-semibold">Your interview</h1>
        <p>No resume has been processed for this interview.</p>
        <p className="text-graphite">Start a new interview and upload your resume to continue.</p>
        <Link href="/" className={LINK}>
          Start a new interview
        </Link>
      </div>
    );
  }

  const header = (
    <div className="flex flex-col gap-1">
      <h1 className="text-2xl font-semibold">Your interview</h1>
      <p className="text-graphite">
        Role: <span className="whitespace-pre-wrap">{interview.role}</span>
      </p>
    </div>
  );

  if (questions.length === 0) {
    const profile = interview.candidate_profile;
    return (
      <div className={`${COLUMN} flex flex-col gap-8`}>
        {header}
        <section className="flex flex-col gap-4 rounded-xl border border-rule bg-paper p-5 sm:p-7">
          <h2 className="text-lg font-semibold">What we read from your resume</h2>
          {profile.summary && <p className="whitespace-pre-wrap font-serif text-[1.0625rem] leading-[1.7]">{profile.summary}</p>}
          <dl className="grid gap-4 sm:grid-cols-[8rem_1fr]">
            {profile.technologies.length > 0 && (
              <>
                <dt className="font-medium">Technologies</dt>
                <dd className="text-graphite">{profile.technologies.join(", ")}</dd>
              </>
            )}
            {profile.skills.length > 0 && (
              <>
                <dt className="font-medium">Skills</dt>
                <dd className="text-graphite">{profile.skills.join(", ")}</dd>
              </>
            )}
          </dl>
        </section>
        {generationError && <Alert tone="error">{generationError}</Alert>}
        {generating && (
          <div role="status" className="flex flex-col gap-3">
            <p className="text-graphite">Generating your questions… this can take up to a minute.</p>
            <ProgressStripe />
          </div>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <Button onClick={startInterview} disabled={generating} loading={generating} className="w-full sm:w-auto">
            {generationError ? "Try again" : "Start interview"}
          </Button>
          {!generating && !generationError && (
            <p className="text-sm text-graphite">Questions are written when you start, from your resume and the reference material.</p>
          )}
        </div>
      </div>
    );
  }

  const total = questions.length;
  const answered = questions.filter((q) => q.answer).length;
  const current = questions.find((q) => !q.answer) ?? null;
  const submitted = questions.filter((q) => q.answer);
  // Only while another question remains, and only for an answer that belongs to this session's data.
  const saved = justSaved ? questions.find((q) => q.id === justSaved && q.answer) : undefined;
  const confirming = saved !== undefined && current !== null;

  return (
    <div className={`${COLUMN} flex flex-col gap-8`}>
      {header}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium text-graphite">
          {!current
            ? `All ${total} questions answered`
            : confirming
              ? `${answered} of ${total} answered`
              : `Question ${current.position} of ${total} · ${answered} answered`}
        </p>
        <ProgressBar answered={answered} total={total} />
      </div>

      {notice && (
        <Alert tone="info" role="status">
          {notice}
        </Alert>
      )}

      {!current && (
        <section className="flex flex-col gap-4 rounded-xl border border-moss/30 bg-moss-tint p-5 sm:p-6">
          <p className="flex items-center gap-2 font-semibold text-moss">
            <IconCheck className="size-5" />
            <span>All {total} answers are saved.</span>
          </p>
          <p className="text-graphite">
            Finishing evaluates your answers with the AI model and writes your report. This can take a few minutes.
          </p>
          {completionError && <Alert tone="error">{completionError}</Alert>}
          {completing && (
            <div role="status" className="flex flex-col gap-3">
              <p className="text-graphite">
                Evaluating your answers and writing your report… this can take a few minutes. Your answers are already saved.
              </p>
              <ProgressStripe />
            </div>
          )}
          <Button onClick={finishInterview} disabled={completing} loading={completing} className="w-full sm:w-auto sm:self-start">
            {completionError ? "Try again" : "Finish interview and get my report"}
          </Button>
        </section>
      )}

      {confirming && <SavedConfirmation position={saved.position} onContinue={continueToNext} />}

      {current && !confirming && (
        <section className="flex flex-col gap-5 rounded-xl border border-rule bg-paper p-5 shadow-[0_1px_2px_rgb(21_26_34/0.06)] sm:p-7">
          <div className="flex flex-col gap-4">
            {(current.topic || current.difficulty) && (
              <div className="flex flex-wrap gap-2">
                {current.topic && <Tag tone="accent">{current.topic}</Tag>}
                {current.difficulty && <Tag>{current.difficulty}</Tag>}
              </div>
            )}
            <h2
              ref={questionHeading}
              tabIndex={-1}
              className="whitespace-pre-wrap font-serif text-[1.5rem] leading-snug [text-wrap:pretty] sm:text-[1.75rem]"
            >
              {current.question_text}
            </h2>
            <Sources question={current} />
          </div>
          <AnswerForm
            key={current.id}
            sessionId={sessionId}
            question={current}
            onSaved={(answer) => answerSaved(current.id, answer)}
            onAlreadyAnswered={alreadyAnswered}
          />
        </section>
      )}

      {submitted.length > 0 && (
        <details className="group rounded-xl border border-rule bg-paper">
          <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-4 py-2 font-medium sm:px-5">
            Previous answers ({submitted.length})
            <IconChevronDown className="size-4 text-graphite transition-transform group-open:rotate-180" />
          </summary>
          <ol className="flex flex-col gap-6 border-t border-rule px-4 py-5 sm:px-5">
            {submitted.map((q) => (
              <li key={q.id} className="flex flex-col gap-2">
                <p className="text-sm font-medium text-graphite">Question {q.position}</p>
                <p className="font-serif text-lg leading-snug">{q.question_text}</p>
                <p className="whitespace-pre-wrap text-graphite">{q.answer?.answer_text}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

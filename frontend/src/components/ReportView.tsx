"use client";

import Link from "next/link";
import { useState } from "react";
import { IconAlert, IconBook, IconCheck, IconInfo, IconMinus } from "@/components/icons";
import Alert from "@/components/ui/Alert";
import Tag from "@/components/ui/Tag";
import type { Assessment, Question, Report } from "@/lib/types";

// Interface labels and tones for the backend's fixed set of assessment values.
const ASSESSMENT: Record<Assessment, { label: string; tone: "success" | "accent" | "warn" | "danger"; icon: React.ReactNode }> = {
  correct_and_complete: { label: "Correct and complete", tone: "success", icon: <IconCheck className="size-3.5" /> },
  mostly_correct: { label: "Mostly correct", tone: "accent", icon: <IconCheck className="size-3.5" /> },
  partially_correct: { label: "Partially correct", tone: "warn", icon: <IconMinus className="size-3.5" /> },
  incorrect_or_off_topic: { label: "Incorrect or off topic", tone: "danger", icon: <IconAlert className="size-3.5" /> },
};

const LONG_ANSWER = 600; // characters; longer answers are clamped until expanded

function List({
  title,
  items,
  level = 2,
  ordered = false,
  icon,
}: {
  title: string;
  items: string[];
  level?: 2 | 3;
  ordered?: boolean;
  icon?: React.ReactNode;
}) {
  if (items.length === 0) return null; // nothing to say: no heading and no placeholder text
  const Heading = level === 2 ? "h2" : "h3";
  const List = ordered ? "ol" : "ul";
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <Heading className={level === 2 ? "text-lg font-semibold" : "flex items-center gap-2 font-medium"}>
        {icon}
        {title}
      </Heading>
      <List className={`flex flex-col gap-2 pl-5 ${ordered ? "list-decimal" : "list-disc"} marker:text-graphite`}>
        {items.map((item, i) => (
          <li key={i} className="whitespace-pre-wrap pl-1">
            {item}
          </li>
        ))}
      </List>
    </section>
  );
}

function SavedAnswer({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > LONG_ANSWER;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-graphite">Your answer</p>
      <blockquote className="border-l-2 border-rule pl-4">
        <p className={`whitespace-pre-wrap text-graphite ${long && !open ? "line-clamp-6" : ""}`}>{text}</p>
      </blockquote>
      {long && (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="self-start rounded-md py-1 text-sm font-medium text-cobalt underline underline-offset-4 hover:text-cobalt-deep"
        >
          {open ? "Show less" : "Show full answer"}
        </button>
      )}
    </div>
  );
}

function QuestionFeedback({ question, total }: { question: Question; total: number }) {
  const feedback = question.answer?.feedback ?? null;
  const assessment = feedback ? ASSESSMENT[feedback.assessment] : undefined;
  return (
    <section className="avoid-break flex flex-col gap-5 border-t border-rule pt-8">
      <div className="flex flex-col gap-3">
        <h3 className="text-sm font-medium text-graphite">
          Question {question.position} of {total}
        </h3>
        {(question.topic || question.difficulty) && (
          <div className="flex flex-wrap gap-2">
            {question.topic && <Tag tone="accent">{question.topic}</Tag>}
            {question.difficulty && <Tag>{question.difficulty}</Tag>}
          </div>
        )}
        <p className="whitespace-pre-wrap font-serif text-[1.25rem] leading-snug">{question.question_text}</p>
      </div>
      <SavedAnswer text={question.answer?.answer_text ?? ""} />
      {feedback ? (
        <div className="flex flex-col gap-4">
          <div>
            <Tag tone={assessment?.tone ?? "neutral"} icon={assessment?.icon}>
              {assessment?.label ?? feedback.assessment}
            </Tag>
          </div>
          <p className="max-w-prose whitespace-pre-wrap">{feedback.summary}</p>
          <div className="flex flex-col gap-5">
            <List title="Done well" items={feedback.strengths} level={3} icon={<IconCheck className="size-4 text-moss" />} />
            <List title="Missing or inaccurate" items={feedback.gaps} level={3} icon={<IconAlert className="size-4 text-amber" />} />
            <List title="How to improve" items={feedback.suggestions} level={3} icon={<IconInfo className="size-4 text-cobalt" />} />
          </div>
          {feedback.grounded ? (
            <p className="flex items-start gap-2 text-sm text-graphite">
              <IconBook className="mt-0.5 size-4" />
              <span>{`Based on: ${feedback.source_chunks.map((s) => `${s.source_title}, page ${s.page}`).join("; ")}`}</span>
            </p>
          ) : (
            <p className="flex items-start gap-2 text-sm font-medium text-amber">
              <IconAlert className="mt-0.5 size-4" />
              <span>Evaluated without reference passages.</span>
            </p>
          )}
        </div>
      ) : (
        <p className="text-graphite">No feedback is available for this answer.</p>
      )}
    </section>
  );
}

export default function ReportView({ report }: { report: Report }) {
  const total = report.questions.length;
  return (
    <article className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="font-serif text-4xl leading-tight">Interview report</h1>
        <p className="text-graphite">
          Role: <span className="whitespace-pre-wrap">{report.role}</span>
        </p>
        {report.completed_at && <p className="text-sm text-graphite">Completed {new Date(report.completed_at).toLocaleString()}</p>}
      </header>

      <p className="flex items-start gap-3 rounded-lg bg-paper px-4 py-3 text-sm text-graphite ring-1 ring-rule">
        <IconInfo className="mt-0.5 size-[1.125rem]" />
        <span>
          This report is AI-generated guidance based on your answers. It is not a measurement of your ability or a hiring
          decision.
        </span>
      </p>

      {report.ungrounded_evaluations > 0 && (
        <Alert tone="notice" role="note">
          {report.ungrounded_evaluations} of {total} answers were evaluated without knowledge-base passages, so their
          feedback is not backed by source material.
        </Alert>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Summary</h2>
        <p className="max-w-prose whitespace-pre-wrap font-serif text-[1.1875rem] leading-[1.7]">{report.summary}</p>
      </section>

      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
        <List title="Strengths" items={report.strengths} />
        <List title="Topics to improve" items={report.improvement_topics} />
      </div>
      <List title="Recommendations" items={report.recommendations} ordered />

      <div className="flex flex-col gap-8">
        <h2 className="text-lg font-semibold">Question-by-question feedback</h2>
        {report.questions.map((question) => (
          <QuestionFeedback key={question.id} question={question} total={total} />
        ))}
      </div>

      <Link href="/" className="no-print self-start text-cobalt underline underline-offset-4 hover:text-cobalt-deep">
        Start a new interview
      </Link>
    </article>
  );
}

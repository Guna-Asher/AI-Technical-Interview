import Link from "next/link";
import type { Assessment, Question, Report } from "@/lib/types";

// Interface labels for the backend's fixed set of assessment values.
const ASSESSMENT_LABEL: Record<Assessment, string> = {
  correct_and_complete: "Correct and complete",
  mostly_correct: "Mostly correct",
  partially_correct: "Partially correct",
  incorrect_or_off_topic: "Incorrect or off topic",
};

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null; // nothing to say: no heading and no placeholder text
  return (
    <section className="flex flex-col gap-1">
      <h2 className="font-medium">{title}</h2>
      <ul className="list-disc pl-5 text-sm">
        {items.map((item, i) => (
          <li key={i} className="whitespace-pre-wrap">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

function QuestionFeedback({ question, total }: { question: Question; total: number }) {
  const feedback = question.answer?.feedback ?? null;
  return (
    <section className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">
        Question {question.position} of {total}
        {question.topic ? ` · ${question.topic}` : ""}
        {question.difficulty ? ` · ${question.difficulty}` : ""}
      </p>
      <p className="whitespace-pre-wrap font-medium">{question.question_text}</p>
      <div className="flex flex-col gap-1">
        <p className="text-xs font-medium text-slate-500">Your answer</p>
        <p className="whitespace-pre-wrap text-sm">{question.answer?.answer_text}</p>
      </div>
      {feedback ? (
        <div className="flex flex-col gap-2 border-t border-slate-100 pt-3">
          <p className="text-sm font-medium">{ASSESSMENT_LABEL[feedback.assessment] ?? feedback.assessment}</p>
          <p className="whitespace-pre-wrap text-sm">{feedback.summary}</p>
          <List title="Done well" items={feedback.strengths} />
          <List title="Missing or inaccurate" items={feedback.gaps} />
          <List title="How to improve" items={feedback.suggestions} />
          {feedback.grounded ? (
            <p className="text-xs text-slate-500">
              Based on: {feedback.source_chunks.map((s) => `${s.source_title}, page ${s.page}`).join("; ")}
            </p>
          ) : (
            <p className="text-xs text-amber-700">Evaluated without reference passages.</p>
          )}
        </div>
      ) : (
        <p className="text-sm text-slate-500">No feedback is available for this answer.</p>
      )}
    </section>
  );
}

export default function ReportView({ report }: { report: Report }) {
  const total = report.questions.length;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Interview report</h1>
        <p className="text-slate-600">
          Role: <span className="whitespace-pre-wrap">{report.role}</span>
        </p>
        {report.completed_at && (
          <p className="text-sm text-slate-500">Completed {new Date(report.completed_at).toLocaleString()}</p>
        )}
      </div>

      <p className="rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-700">
        This report is AI-generated guidance based on your answers. It is not a measurement of your ability or a hiring
        decision.
      </p>

      {report.ungrounded_evaluations > 0 && (
        <p role="note" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {report.ungrounded_evaluations} of {total} answers were evaluated without knowledge-base passages, so their
          feedback is not backed by source material.
        </p>
      )}

      <section className="flex flex-col gap-1">
        <h2 className="font-medium">Summary</h2>
        <p className="whitespace-pre-wrap text-sm">{report.summary}</p>
      </section>
      <List title="Strengths" items={report.strengths} />
      <List title="Topics to improve" items={report.improvement_topics} />
      <List title="Recommendations" items={report.recommendations} />

      <div className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Question-by-question feedback</h2>
        {report.questions.map((question) => (
          <QuestionFeedback key={question.id} question={question} total={total} />
        ))}
      </div>

      <Link href="/" className="self-start text-sm underline">
        Start a new interview
      </Link>
    </div>
  );
}

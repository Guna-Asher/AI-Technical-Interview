import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Question, Report } from "@/lib/types";
import { REPORT_CONTENT, makeAnswer, makeFeedback, makeQuestion } from "@/test-utils/fakeBackend";
import ReportView from "./ReportView";

// The report below is synthetic test data; the component renders only what it is given.
function question(n: number, feedback = makeFeedback({ summary: `Feedback for question ${n}.` })): Question {
  const q = makeQuestion(n);
  return { ...q, answer: makeAnswer(q, `my answer ${n}`, feedback) };
}

function report(overrides: Partial<Report> = {}): Report {
  const questions = overrides.questions ?? [question(1), question(2)];
  return {
    session_id: "session-1",
    role: "any role text",
    status: "completed",
    completed_at: "2026-01-01T00:10:00Z",
    created_at: "2026-01-01T00:10:00Z",
    ...REPORT_CONTENT,
    questions,
    ungrounded_evaluations: 0,
    ...overrides,
  };
}

describe("ReportView", () => {
  it("renders the report fields and per-question feedback exactly as the backend returned them", () => {
    render(<ReportView report={report()} />);

    expect(screen.getByRole("heading", { name: "Interview report" })).toBeInTheDocument();
    expect(screen.getByText("any role text")).toBeInTheDocument();
    expect(screen.getByText(/Completed/)).toBeInTheDocument();
    expect(screen.getByText(REPORT_CONTENT.summary)).toBeInTheDocument();
    expect(screen.getByText("report strength one")).toBeInTheDocument();
    expect(screen.getByText("report topic one")).toBeInTheDocument();
    expect(screen.getByText("report recommendation one")).toBeInTheDocument();
    expect(screen.getByText("Synthetic question number 1?")).toBeInTheDocument();
    expect(screen.getByText("my answer 2")).toBeInTheDocument();
    expect(screen.getByText("Feedback for question 2.")).toBeInTheDocument();
    expect(screen.getAllByText("Mostly correct")).toHaveLength(2);
    expect(screen.getAllByText("did well on idea-a")).toHaveLength(2);
    expect(screen.getAllByText("missed idea-b")).toHaveLength(2);
    expect(screen.getAllByText("review idea-b")).toHaveLength(2);
  });

  it("shows source titles and pages for grounded feedback, and never any passage text", () => {
    render(<ReportView report={report()} />);

    expect(screen.getAllByText("Based on: Synthetic Book 1, page 11")).toHaveLength(2);
    expect(screen.queryByText(/Evaluated without reference passages/)).toBeNull();
  });

  it("tells the reader that the report is AI guidance rather than a measurement", () => {
    render(<ReportView report={report()} />);

    expect(screen.getByText(/AI-generated guidance/)).toBeInTheDocument();
    expect(screen.getByText(/not a measurement of your ability/)).toBeInTheDocument();
  });

  it("flags ungrounded evaluations with a notice and the count, and does not show sources for them", () => {
    const ungrounded = makeFeedback({ grounded: false, source_chunks: [], summary: "Ungrounded feedback." });
    render(<ReportView report={report({ questions: [question(1), question(2, ungrounded)], ungrounded_evaluations: 1 })} />);

    expect(screen.getByRole("note")).toHaveTextContent("1 of 2 answers were evaluated without knowledge-base passages");
    const second = screen.getByText("Ungrounded feedback.").closest("section")!;
    expect(within(second).getByText("Evaluated without reference passages.")).toBeInTheDocument();
    expect(within(second).queryByText(/Based on:/)).toBeNull();
  });

  it("shows no notice when everything was grounded", () => {
    render(<ReportView report={report()} />);

    expect(screen.queryByRole("note")).toBeNull();
  });

  it("omits empty sections instead of inventing placeholder content", () => {
    const empty = makeFeedback({ strengths: [], gaps: [], suggestions: [], summary: "Only a summary." });
    render(<ReportView report={report({ strengths: [], improvement_topics: [], questions: [question(1, empty)] })} />);

    expect(screen.queryByRole("heading", { name: "Strengths" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Topics to improve" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Done well" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Missing or inaccurate" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "How to improve" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Recommendations" })).toBeInTheDocument();
    expect(screen.getByText("Only a summary.")).toBeInTheDocument();
  });

  it("renders hostile text from the backend as plain text, never as HTML", () => {
    const hostile = "<img src=x onerror=alert(1)> summary";
    const { container } = render(<ReportView report={report({ summary: hostile })} />);

    expect(screen.getByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("says so when an answer has no saved feedback instead of making any up", () => {
    const q = makeQuestion(1);
    render(<ReportView report={report({ questions: [{ ...q, answer: makeAnswer(q, "an answer", null) }] })} />);

    expect(screen.getByText("No feedback is available for this answer.")).toBeInTheDocument();
  });

  it("links to start a new interview", () => {
    render(<ReportView report={report()} />);

    expect(screen.getByRole("link", { name: "Start a new interview" })).toHaveAttribute("href", "/");
  });
});

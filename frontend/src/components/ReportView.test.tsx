import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    expect(screen.getAllByText("Mostly correct")).toHaveLength(4); // in each question's row and again in its expanded content
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
    const second = screen.getByText("Ungrounded feedback.").closest("details")!;
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

describe("ReportView long answers", () => {
  const longText = "A long synthetic answer sentence. ".repeat(30); // over 600 characters

  it("clamps a long answer behind a toggle, keeping the full text on the page", async () => {
    const user = userEvent.setup();
    const q = makeQuestion(1);
    render(<ReportView report={report({ questions: [{ ...q, answer: makeAnswer(q, longText, makeFeedback()) }] })} />);

    const toggle = screen.getByRole("button", { name: "Show full answer" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText(longText.trim())).toBeInTheDocument(); // the full text is in the page, only visually clamped

    await user.click(toggle);

    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");
  });

  it("shows no toggle for a short answer", () => {
    render(<ReportView report={report()} />);

    expect(screen.queryByRole("button", { name: /Show (full answer|less)/ })).toBeNull();
  });

  it("gives each feedback list a heading and keeps one assessment chip per answered question", () => {
    render(<ReportView report={report()} />);

    expect(screen.getAllByRole("heading", { name: "Done well" })).toHaveLength(2);
    const rows = screen.getAllByText(/^Question \d of 2$/).map((row) => row.closest("summary")!);
    rows.forEach((row) => expect(within(row).getAllByText("Mostly correct")).toHaveLength(1)); // one assessment chip per row
  });
});

describe("ReportView collapsible question feedback", () => {
  const rowOf = (n: number, total = 2) => screen.getByText(`Question ${n} of ${total}`).closest("summary")!;
  const detailsOf = (n: number) => rowOf(n).closest("details")!;

  it("renders every question collapsed by default, with a row that identifies it", () => {
    const { container } = render(<ReportView report={report()} />);

    const all = container.querySelectorAll("details");
    expect(all).toHaveLength(2);
    all.forEach((d) => expect(d.open).toBe(false));
    expect(rowOf(1)).toBeVisible();
    expect(within(rowOf(1)).getByText("topic 1")).toBeVisible(); // the topic is the row's title
    expect(within(rowOf(1)).getByText("medium")).toBeVisible();
    expect(within(rowOf(1)).getByText("Mostly correct")).toBeVisible();
    expect(within(rowOf(1)).getByText("Question 1 of 2")).toBeVisible();
    expect(rowOf(1).querySelector("svg")).not.toBeNull(); // chevron
    expect(screen.getByText("Synthetic question number 1?")).not.toBeVisible();
    expect(screen.getByText("my answer 1")).not.toBeVisible();
    expect(screen.getByText("Feedback for question 1.")).not.toBeVisible();
    expect(screen.getAllByText("Based on: Synthetic Book 1, page 11")[0]).not.toBeVisible();
  });

  it("reveals the question, answer, assessment, feedback and sources when its row is clicked, and hides them on a second click", async () => {
    const user = userEvent.setup();
    render(<ReportView report={report()} />);

    await user.click(rowOf(1));

    const open = within(detailsOf(1));
    expect(open.getByText("Synthetic question number 1?")).toBeVisible();
    expect(open.getByText("my answer 1")).toBeVisible();
    expect(open.getByText("Feedback for question 1.")).toBeVisible();
    expect(open.getByText("did well on idea-a")).toBeVisible();
    expect(open.getByText("missed idea-b")).toBeVisible();
    expect(open.getByText("review idea-b")).toBeVisible();
    expect(open.getByText("Based on: Synthetic Book 1, page 11")).toBeVisible();
    expect(within(detailsOf(1)).getAllByText("Mostly correct")).toHaveLength(2);
    expect(screen.getByText("Synthetic question number 2?")).not.toBeVisible(); // the other question stays collapsed

    await user.click(rowOf(1));

    expect(open.getByText("Feedback for question 1.")).not.toBeVisible();
    expect(open.getByText("my answer 1")).not.toBeVisible();
  });

  it("expands and collapses each question independently", async () => {
    const user = userEvent.setup();
    render(<ReportView report={report({ questions: [question(1), question(2), question(3)] })} />);

    await user.click(rowOf(1, 3));
    await user.click(rowOf(3, 3));
    expect([1, 2, 3].map((n) => (detailsOf3(n) as HTMLDetailsElement).open)).toEqual([true, false, true]);
    expect(screen.getByText("Feedback for question 1.")).toBeVisible();
    expect(screen.getByText("Feedback for question 3.")).toBeVisible();

    await user.click(rowOf(1, 3));

    expect([1, 2, 3].map((n) => (detailsOf3(n) as HTMLDetailsElement).open)).toEqual([false, false, true]);
    expect(screen.getByText("Feedback for question 3.")).toBeVisible(); // closing one does not reset another
    expect(screen.getByText("my answer 3")).toBeVisible();

    function detailsOf3(n: number) {
      return rowOf(n, 3).closest("details")!;
    }
  });

  it("keeps the ungrounded explanation (and no sources) available when an ungrounded question is expanded", async () => {
    const user = userEvent.setup();
    const ungrounded = makeFeedback({ grounded: false, source_chunks: [], summary: "Ungrounded feedback." });
    render(<ReportView report={report({ questions: [question(1), question(2, ungrounded)], ungrounded_evaluations: 1 })} />);

    await user.click(rowOf(2));

    const open = within(detailsOf(2));
    expect(open.getByText("Evaluated without reference passages.")).toBeVisible();
    expect(open.queryByText(/Based on:/)).toBeNull();
    expect(screen.getByText(/1 of 2 answers were evaluated without knowledge-base passages/)).toBeVisible(); // overview notice is unaffected
  });

  it("shows a row without an assessment, and the no-feedback message when expanded, for an answer with no saved feedback", async () => {
    const user = userEvent.setup();
    const q = makeQuestion(1);
    render(<ReportView report={report({ questions: [{ ...q, answer: makeAnswer(q, "an answer", null) }] })} />);

    expect(within(rowOf(1, 1)).queryByText("Mostly correct")).toBeNull();
    await user.click(rowOf(1, 1));

    expect(screen.getByText("No feedback is available for this answer.")).toBeVisible();
    expect(screen.getByText("an answer")).toBeVisible();
  });

  it("uses the question text as the row title when there is no topic, and omits missing chips", () => {
    const q = makeQuestion(1, { topic: null, difficulty: null });
    render(<ReportView report={report({ questions: [{ ...q, answer: makeAnswer(q, "an answer", makeFeedback()) }] })} />);

    expect(within(rowOf(1, 1)).getByText("Synthetic question number 1?")).toBeVisible();
    expect(within(rowOf(1, 1)).queryByText("medium")).toBeNull();
  });

  it("keeps the overview visible above the collapsed rows", () => {
    render(<ReportView report={report()} />);

    expect(screen.getByText(REPORT_CONTENT.summary)).toBeVisible();
    expect(screen.getByText("report strength one")).toBeVisible();
    expect(screen.getByText("report topic one")).toBeVisible();
    expect(screen.getByText("report recommendation one")).toBeVisible();
    expect(screen.getByText(/AI-generated guidance/)).toBeVisible();
    const overview = screen.getByRole("heading", { name: "Summary" });
    const feedbackHeading = screen.getByRole("heading", { name: "Question-by-question feedback" });
    expect(overview.compareDocumentPosition(feedbackHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(feedbackHeading.compareDocumentPosition(rowOf(1)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders long content in full once expanded, including the long-answer toggle", async () => {
    const user = userEvent.setup();
    const longQuestion = "A long synthetic question that keeps going. ".repeat(20).trim();
    const longAnswer = "A long synthetic answer sentence. ".repeat(40).trim();
    const longFeedback = "A long synthetic evaluation sentence. ".repeat(40).trim();
    const q = makeQuestion(1, { question_text: longQuestion });
    render(<ReportView report={report({ questions: [{ ...q, answer: makeAnswer(q, longAnswer, makeFeedback({ summary: longFeedback })) }] })} />);

    await user.click(rowOf(1, 1));

    expect(screen.getByText(longQuestion)).toBeVisible();
    expect(screen.getByText(longFeedback)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Show full answer" }));
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(longAnswer)).toBeVisible();
  });

  it("renders hostile question and feedback text as plain text inside the disclosure", async () => {
    const user = userEvent.setup();
    const hostile = "<img src=x onerror=alert(1)> text";
    const q = makeQuestion(1, { question_text: hostile, topic: hostile });
    const { container } = render(
      <ReportView report={report({ questions: [{ ...q, answer: makeAnswer(q, hostile, makeFeedback({ summary: hostile })) }] })} />,
    );

    await user.click(rowOf(1, 1));

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByText(hostile).length).toBeGreaterThan(0);
  });

  it("opens every question while printing and restores the reader's own state afterwards", async () => {
    const user = userEvent.setup();
    const { container } = render(<ReportView report={report({ questions: [question(1), question(2), question(3)] })} />);
    await user.click(rowOf(2, 3));
    const states = () => [...container.querySelectorAll("details")].map((d) => d.open);

    fireEvent(window, new Event("beforeprint"));
    expect(states()).toEqual([true, true, true]);

    fireEvent(window, new Event("afterprint"));
    expect(states()).toEqual([false, true, false]);
  });
});

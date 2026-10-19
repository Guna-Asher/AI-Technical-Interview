import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeBackend, REPORT_CONTENT, makeAnswer, makeFeedback, makeQuestion } from "@/test-utils/fakeBackend";
import InterviewView from "./InterviewView";

// All questions, answers and backend replies here are synthetic test data served by an in-memory fake backend.
let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vi.stubGlobal("fetch", backend.fetch);
});

const renderView = () => render(<InterviewView sessionId="session-1" />);
const generateCalls = () => backend.calls.filter((c) => c.method === "POST" && c.path.endsWith("/questions")).length;
const answerCalls = () => backend.calls.filter((c) => c.path.endsWith("/answer"));
const three = () => [makeQuestion(1), makeQuestion(2), makeQuestion(3)];

describe("loading and error states", () => {
  it("shows a loading state, then the interview", async () => {
    backend.seed();
    renderView();

    expect(screen.getByRole("status")).toHaveTextContent("Loading your interview");
    expect(await screen.findByRole("button", { name: "Start interview" })).toBeInTheDocument();
  });

  it("shows the backend's message when the interview does not exist", async () => {
    renderView();

    expect(await screen.findByRole("alert")).toHaveTextContent("Interview session not found");
    expect(screen.getByRole("link", { name: "Start a new interview" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull(); // retrying cannot help a 404
  });

  it("offers Retry for a server error but not for a malformed interview id", async () => {
    backend.seed().failNext("GET /api/interviews/session-1/questions", 500, "The server failed.");
    const first = renderView();
    expect(await screen.findByRole("alert")).toHaveTextContent("The server failed.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    first.unmount();

    backend.seed().failNext("GET /api/interviews/session-1", 422, "session_id: Input should be a valid UUID");
    renderView();
    expect(await screen.findByText("This interview link is not valid")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it("explains a network failure and lets the candidate retry", async () => {
    const user = userEvent.setup();
    backend.seed().networkErrorNext("GET /api/interviews/session-1/questions");
    renderView();

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("button", { name: "Start interview" })).toBeInTheDocument();
  });

  it("tells the candidate when no resume was processed", async () => {
    backend.seed({ candidate_profile: null });
    renderView();

    expect(await screen.findByText("No resume has been processed for this interview.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start a new interview" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("button", { name: "Start interview" })).toBeNull();
  });
});

describe("starting the interview", () => {
  it("never generates questions on mount, re-render or refresh", async () => {
    backend.seed();
    backend.toGenerate = three();
    const first = renderView();
    await screen.findByRole("button", { name: "Start interview" });

    first.rerender(<InterviewView sessionId="session-1" />);
    first.unmount();
    renderView(); // a browser refresh
    await screen.findByRole("button", { name: "Start interview" });

    expect(backend.calls.every((c) => c.method === "GET")).toBe(true);
    expect(generateCalls()).toBe(0);
  });

  it("shows the profile the backend extracted", async () => {
    backend.seed({ role: "any role text", candidate_profile: { summary: "Profile summary text.", skills: ["s1", "s2"], technologies: ["t1"], experience: [] } });
    renderView();

    expect(await screen.findByText("Profile summary text.")).toBeInTheDocument();
    expect(screen.getByText("any role text")).toBeInTheDocument();
    expect(screen.getByText(/s1, s2/)).toBeInTheDocument();
    expect(screen.getByText(/t1/)).toBeInTheDocument();
  });

  it("generates once, even if Start is clicked repeatedly, and shows the returned questions", async () => {
    backend.seed();
    backend.toGenerate = three();
    const release = backend.hold("POST /api/interviews/session-1/questions");
    renderView();
    const start = await screen.findByRole("button", { name: "Start interview" });

    fireEvent.click(start);
    fireEvent.click(start);

    expect(await screen.findByText(/Generating your questions/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start interview" })).toBeDisabled();
    release();
    expect(await screen.findByText("Synthetic question number 1?")).toBeInTheDocument();
    expect(generateCalls()).toBe(1);
  });

  it.each([
    [422, "Only 1 sufficiently relevant passage(s) were found in the knowledge base for this role and profile."],
    [503, "OPENROUTER_API_KEY is not configured. Set it in .env and restart the backend."],
    [502, "OpenRouter returned HTTP 500."],
    [429, "OpenRouter rate limit reached. Try again shortly."],
  ])("shows the backend's message when generation fails (HTTP %i) and allows a retry", async (status, detail) => {
    const user = userEvent.setup();
    backend.seed();
    backend.toGenerate = three();
    backend.failNext("POST /api/interviews/session-1/questions", status, detail);
    renderView();

    await user.click(await screen.findByRole("button", { name: "Start interview" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(screen.queryByText(/Synthetic question number/)).toBeNull();
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry).toBeEnabled();

    await user.click(retry);
    expect(await screen.findByText("Synthetic question number 1?")).toBeInTheDocument();
  });

  it("picks up questions that already exist when the backend answers 409", async () => {
    const user = userEvent.setup();
    backend.seed();
    renderView();
    await screen.findByRole("button", { name: "Start interview" });
    backend.questions = [makeQuestion(1, { question_text: "Generated by an earlier request?" })];

    await user.click(screen.getByRole("button", { name: "Start interview" }));

    expect(await screen.findByText("Generated by an earlier request?")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("questions and progress", () => {
  it("shows only the backend's current question, with topic, difficulty and sources", async () => {
    backend.seed({}, [
      makeQuestion(1, { question_text: "UNIQUE-BACKEND-QUESTION-TEXT?", topic: "unique topic", difficulty: "hard" }),
      makeQuestion(2),
      makeQuestion(3),
    ]);
    renderView();

    expect(await screen.findByText("UNIQUE-BACKEND-QUESTION-TEXT?")).toBeInTheDocument();
    expect(screen.getByText(/unique topic/)).toBeInTheDocument();
    expect(screen.getByText(/hard/)).toBeInTheDocument();
    expect(screen.getByText(/Based on: Synthetic Book 1, page 11/)).toBeInTheDocument();
    expect(screen.queryByText("Synthetic question number 2?")).toBeNull(); // later questions stay hidden
    expect(screen.getByLabelText("Your answer")).toBeInTheDocument();
  });

  it("renders question text as plain text, never as HTML", async () => {
    const hostile = "<img src=x onerror=alert(1)> what is an index?";
    backend.seed({}, [makeQuestion(1, { question_text: hostile })]);
    const { container } = renderView();

    expect(await screen.findByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("reports progress from the saved answers", async () => {
    const q1 = makeQuestion(1);
    backend.seed({}, [{ ...q1, answer: makeAnswer(q1, "first saved answer") }, makeQuestion(2), makeQuestion(3)]);
    renderView();

    expect(await screen.findByText(/Question 2 of 3 · 1 answered/)).toBeInTheDocument();
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "1");
    expect(bar).toHaveAttribute("aria-valuemax", "3");
  });

  it("recovers saved progress after a refresh: answered questions show as submitted, the first unanswered is current", async () => {
    const [q1, q2, q3] = three();
    backend.seed({}, [{ ...q1, answer: makeAnswer(q1, "my saved answer one") }, q2, q3]);
    const first = renderView();
    await screen.findByText("my saved answer one");
    first.unmount();

    renderView(); // refresh: everything is read from the backend again

    expect(await screen.findByText("my saved answer one")).toBeInTheDocument();
    expect(screen.getByText("Submitted")).toBeInTheDocument();
    expect(screen.getByText("Synthetic question number 1?")).toBeInTheDocument();
    expect(screen.getByText("Synthetic question number 2?")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Your answer")).toHaveLength(1); // only the current question asks for an answer
    expect(screen.queryByText("Synthetic question number 3?")).toBeNull();
    expect(backend.calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("shows a completion panel with the saved answers once everything is answered", async () => {
    const answered = three().map((q) => ({ ...q, answer: makeAnswer(q, `saved answer ${q.position}`) }));
    backend.seed({}, answered);
    renderView();

    expect(await screen.findByText("All 3 answers are saved.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish interview and get my report" })).toBeEnabled();
    expect(screen.queryByText(/not available yet/)).toBeNull();
    expect(screen.getAllByText("Submitted")).toHaveLength(3);
    expect(screen.getByText("saved answer 3")).toBeInTheDocument();
    expect(screen.queryByLabelText("Your answer")).toBeNull();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
  });
});

describe("submitting answers", () => {
  async function ready() {
    const user = userEvent.setup();
    backend.seed({}, three());
    renderView();
    await screen.findByLabelText("Your answer");
    return user;
  }

  it("saves through the backend, marks the answer submitted only afterwards, and moves to the next question", async () => {
    const user = await ready();
    const release = backend.hold("/answer");
    await user.type(screen.getByLabelText("Your answer"), "  my typed answer  ");

    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByLabelText("Your answer")).toBeDisabled();
    expect(screen.queryByText("Submitted")).toBeNull(); // not marked until the backend confirms
    release();
    expect(await screen.findByText("Submitted")).toBeInTheDocument();
    expect(answerCalls()).toEqual([
      { method: "POST", path: "/api/interviews/session-1/questions/q1/answer", body: { answer_text: "  my typed answer  " } },
    ]);
    expect(screen.getByText("my typed answer")).toBeInTheDocument(); // the saved (trimmed) text from the backend
    expect(screen.getByText("Synthetic question number 2?")).toBeInTheDocument();
    expect(screen.getByLabelText("Your answer")).toHaveValue("");
    expect(screen.getByText(/Question 2 of 3 · 1 answered/)).toBeInTheDocument();
  });

  it("sends only one request when the form is submitted repeatedly", async () => {
    const user = await ready();
    const release = backend.hold("/answer");
    await user.type(screen.getByLabelText("Your answer"), "an answer");

    const form = screen.getByLabelText("Your answer").closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    release();

    await screen.findByText("Submitted");
    expect(answerCalls()).toHaveLength(1);
  });

  it("does not send an empty answer", async () => {
    const user = await ready();

    await user.type(screen.getByLabelText("Your answer"), "   ");
    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Write an answer before submitting.");
    expect(answerCalls()).toHaveLength(0);
  });

  it("keeps the typed text and shows the error when saving fails, then allows a retry", async () => {
    const user = await ready();
    backend.failNext("/answer", 500, "The answer could not be saved.");
    await user.type(screen.getByLabelText("Your answer"), "do not lose this");

    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The answer could not be saved.");
    expect(screen.getByLabelText("Your answer")).toHaveValue("do not lose this");
    expect(screen.queryByText("Submitted")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(await screen.findByText("Submitted")).toBeInTheDocument();
    expect(answerCalls()).toHaveLength(2);
  });

  it("keeps the typed text when the server cannot be reached", async () => {
    const user = await ready();
    backend.networkErrorNext("/answer");
    await user.type(screen.getByLabelText("Your answer"), "still here");

    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
    expect(screen.getByLabelText("Your answer")).toHaveValue("still here");
  });

  it("shows the already-saved answer when the backend reports a conflict", async () => {
    const user = await ready();
    backend.questions[0].answer = makeAnswer(backend.questions[0], "saved from another tab");
    await user.type(screen.getByLabelText("Your answer"), "typed too late");

    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByText("saved from another tab")).toBeInTheDocument();
    expect(screen.queryByText("typed too late")).toBeNull();
    expect(screen.getByText(/already answered/)).toBeInTheDocument();
    expect(screen.getByText("Synthetic question number 2?")).toBeInTheDocument();
  });

  it("can answer every question in turn and reach the completion panel", async () => {
    const user = await ready();

    for (const n of [1, 2, 3]) {
      await user.type(screen.getByLabelText("Your answer"), `answer ${n}`);
      await user.click(screen.getByRole("button", { name: "Submit answer" }));
      await waitFor(() => expect(screen.getByText(`answer ${n}`)).toBeInTheDocument());
    }

    expect(await screen.findByText("All 3 answers are saved.")).toBeInTheDocument();
    expect(within(screen.getByRole("progressbar")).queryByText(/./)).toBeNull();
    expect(answerCalls().map((c) => c.path)).toEqual([
      "/api/interviews/session-1/questions/q1/answer",
      "/api/interviews/session-1/questions/q2/answer",
      "/api/interviews/session-1/questions/q3/answer",
    ]);
  });
});

describe("finishing the interview and the results", () => {
  const FINISH = { name: "Finish interview and get my report" };
  const answered = (count = 3) => Array.from({ length: count }, (_, i) => {
    const q = makeQuestion(i + 1);
    return { ...q, answer: makeAnswer(q, `saved answer ${i + 1}`) };
  });
  const completeCalls = () => backend.calls.filter((c) => c.method === "POST" && c.path.endsWith("/complete")).length;
  const reportCalls = () => backend.calls.filter((c) => c.method === "GET" && c.path.endsWith("/report")).length;

  it("offers to finish only when every question is answered", async () => {
    const [q1, q2, q3] = three();
    backend.seed({}, [{ ...q1, answer: makeAnswer(q1, "a1") }, q2, q3]);
    const first = renderView();
    await screen.findByLabelText("Your answer");
    expect(screen.queryByRole("button", { name: FINISH.name })).toBeNull();
    first.unmount();

    backend.seed({}, answered());
    renderView();

    expect(await screen.findByRole("button", { name: FINISH.name })).toBeInTheDocument();
  });

  it("never starts evaluation or fetches a report on mount, re-render or refresh", async () => {
    backend.seed({}, answered());
    const first = renderView();
    await screen.findByRole("button", { name: FINISH.name });

    first.rerender(<InterviewView sessionId="session-1" />);
    first.unmount();
    renderView(); // a browser refresh
    await screen.findByRole("button", { name: FINISH.name });

    expect(backend.calls.every((c) => c.method === "GET")).toBe(true);
    expect(completeCalls()).toBe(0);
    expect(reportCalls()).toBe(0); // an unfinished interview has no report to load
  });

  it("shows a processing state, sends one request on repeated clicks, then shows the report from the backend", async () => {
    backend.seed({}, answered());
    const release = backend.hold("/complete");
    renderView();
    const finish = await screen.findByRole("button", FINISH);

    fireEvent.click(finish);
    fireEvent.click(finish);

    expect(await screen.findByText(/Evaluating your answers and writing your report/)).toBeInTheDocument();
    expect(screen.getByRole("button", FINISH)).toBeDisabled();
    expect(screen.getByText("saved answer 2")).toBeInTheDocument(); // saved answers stay visible while processing
    release();

    expect(await screen.findByRole("heading", { name: "Interview report" })).toBeInTheDocument();
    expect(completeCalls()).toBe(1);
    expect(screen.getByText(REPORT_CONTENT.summary)).toBeInTheDocument();
    expect(screen.getByText("report recommendation one")).toBeInTheDocument();
    expect(screen.getByText("Feedback for question 2.")).toBeInTheDocument();
    expect(screen.queryByRole("button", FINISH)).toBeNull();
  });

  it.each([
    [409, "Answer question(s) 3 before finishing the interview."],
    [503, "OPENROUTER_API_KEY is not configured. Set it in .env and restart the backend."],
    [502, "1 of 3 answers evaluated before the error. Your answers and the finished evaluations are saved; try again to continue."],
    [429, "OpenRouter rate limit reached. Try again shortly."],
    [504, "The request to OpenRouter timed out."],
  ])("shows the backend's message when finishing fails (HTTP %i), keeps the answers, and allows a retry", async (status, detail) => {
    const user = userEvent.setup();
    backend.seed({}, answered());
    backend.failNext("POST /api/interviews/session-1/complete", status, detail);
    renderView();

    await user.click(await screen.findByRole("button", FINISH));

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(screen.getByText("saved answer 1")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Interview report" })).toBeNull();
    const retry = screen.getByRole("button", { name: "Try again" });
    expect(retry).toBeEnabled();

    await user.click(retry);
    expect(await screen.findByRole("heading", { name: "Interview report" })).toBeInTheDocument();
    expect(completeCalls()).toBe(2);
  });

  it("explains when the server cannot be reached while finishing", async () => {
    const user = userEvent.setup();
    backend.seed({}, answered());
    backend.networkErrorNext("/complete");
    renderView();

    await user.click(await screen.findByRole("button", FINISH));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("loads and shows the saved report after a refresh without calling complete again", async () => {
    backend.seed({}, answered());
    await backend.fetch("http://localhost:8000/api/interviews/session-1/complete", { method: "POST" }); // finished earlier
    backend.calls = [];

    renderView();

    expect(await screen.findByRole("heading", { name: "Interview report" })).toBeInTheDocument();
    expect(screen.getByText(REPORT_CONTENT.summary)).toBeInTheDocument();
    expect(screen.getByText("Feedback for question 3.")).toBeInTheDocument();
    expect(completeCalls()).toBe(0);
    expect(reportCalls()).toBe(1);
  });

  it("shows an error with a retry when a completed interview's report cannot be loaded", async () => {
    const user = userEvent.setup();
    backend.seed({}, answered());
    await backend.fetch("http://localhost:8000/api/interviews/session-1/complete", { method: "POST" });
    backend.failNext("GET /api/interviews/session-1/report", 500, "The report could not be read.");
    renderView();

    expect(await screen.findByRole("alert")).toHaveTextContent("The report could not be read.");
    expect(screen.queryByRole("button", FINISH)).toBeNull(); // a completed interview is never re-completed
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Interview report" })).toBeInTheDocument();
  });

  it("shows the feedback that is saved with a partly evaluated, unfinished interview only after finishing", async () => {
    const withFeedback = answered().map((q, i) => (i === 0 ? { ...q, answer: { ...q.answer!, feedback: makeFeedback({ summary: "EARLY-FEEDBACK" }) } } : q));
    backend.seed({}, withFeedback);
    renderView();

    expect(await screen.findByRole("button", FINISH)).toBeInTheDocument();
    expect(screen.queryByText("EARLY-FEEDBACK")).toBeNull(); // results appear only in the report
  });
});

describe("answer form keyboard and progress indicator", () => {
  it.each([["{Control>}{Enter}{/Control}"], ["{Meta>}{Enter}{/Meta}"]])("submits once with %s", async (keys) => {
    const user = userEvent.setup();
    backend.seed({}, [makeQuestion(1), makeQuestion(2)]);
    renderView();
    await user.type(await screen.findByLabelText("Your answer"), "typed with the keyboard");

    await user.keyboard(keys);

    expect(await screen.findByText("Submitted")).toBeInTheDocument();
    expect(backend.calls.filter((c) => c.path.endsWith("/answer"))).toHaveLength(1);
  });

  it("a plain Enter adds a line break instead of submitting", async () => {
    const user = userEvent.setup();
    backend.seed({}, [makeQuestion(1)]);
    renderView();
    await user.type(await screen.findByLabelText("Your answer"), "line one{Enter}line two");

    expect(screen.getByLabelText("Your answer")).toHaveValue("line one\nline two");
    expect(backend.calls.filter((c) => c.path.endsWith("/answer"))).toHaveLength(0);
  });

  it("draws one progress segment per question and keeps the progressbar values", async () => {
    const q1 = makeQuestion(1);
    backend.seed({}, [{ ...q1, answer: makeAnswer(q1, "a1") }, makeQuestion(2), makeQuestion(3), makeQuestion(4)]);
    renderView();

    const bar = await screen.findByRole("progressbar");

    expect(bar.children).toHaveLength(4);
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["1", "4"]);
  });

  it("states the answer's save status in plain words next to the submit button", async () => {
    backend.seed({}, [makeQuestion(1)]);
    renderView();

    expect(await screen.findByText(/Saved as soon as you submit/)).toBeInTheDocument();
  });
});

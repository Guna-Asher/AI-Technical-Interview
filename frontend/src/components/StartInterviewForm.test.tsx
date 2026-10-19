import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FakeBackend } from "@/test-utils/fakeBackend";
import StartInterviewForm from "./StartInterviewForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

let backend: FakeBackend;

beforeEach(() => {
  push.mockReset();
  backend = new FakeBackend();
  vi.stubGlobal("fetch", backend.fetch);
});

const resumeFile = () => new File(["synthetic resume"], "resume.txt", { type: "text/plain" });

async function fill(user: ReturnType<typeof userEvent.setup>, role = "synthetic role") {
  await user.type(screen.getByLabelText("Job role"), role);
  await user.upload(screen.getByLabelText(/Resume/), resumeFile());
}

describe("StartInterviewForm", () => {
  it("takes the role as free text, with no predefined role choices", () => {
    const { container } = render(<StartInterviewForm />);

    const role = screen.getByLabelText("Job role");
    expect(role).toHaveAttribute("type", "text");
    expect(role).not.toHaveAttribute("list");
    expect(role).toHaveValue("");
    expect(role).not.toHaveAttribute("placeholder");
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(container.querySelector("select, datalist, option")).toBeNull();
    expect(screen.getByLabelText(/Resume/)).toHaveAttribute("type", "file");
  });

  it("does not submit without a role or a file", async () => {
    const user = userEvent.setup();
    render(<StartInterviewForm />);

    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter the job role and choose a resume file");

    await user.type(screen.getByLabelText("Job role"), "   ");
    await user.upload(screen.getByLabelText(/Resume/), resumeFile());
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(backend.calls).toEqual([]);
  });

  it("creates the interview, uploads the resume for the same session, then opens the interview", async () => {
    const user = userEvent.setup();
    render(<StartInterviewForm />);

    await fill(user, "  any role I type  ");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/interview/session-1"));
    expect(backend.calls).toEqual([
      { method: "POST", path: "/api/interviews", body: { role: "any role I type" } },
      { method: "POST", path: "/api/interviews/session-1/resume", body: { file: "resume.txt" } },
    ]);
  });

  it("shows progress, disables the controls, and sends only one create on repeated submits", async () => {
    const user = userEvent.setup();
    const release = backend.hold("POST /api/interviews");
    render(<StartInterviewForm />);
    await fill(user);

    const form = screen.getByRole("button", { name: "Continue" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(await screen.findByRole("status")).toHaveTextContent("Creating your interview");
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    expect(screen.getByLabelText("Job role")).toBeDisabled();
    expect(backend.count("POST", "/api/interviews")).toBe(1);
    release();
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(backend.count("POST", "/api/interviews")).toBe(2); // the create plus the resume upload
  });

  it("shows the resume step while the resume is being read", async () => {
    const user = userEvent.setup();
    const release = backend.hold("/resume");
    render(<StartInterviewForm />);
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText(/Reading your resume/)).toBeInTheDocument();
    release();
    await waitFor(() => expect(push).toHaveBeenCalled());
  });

  it.each([
    ["POST /api/interviews", 422, "role: String should have at least 1 character"],
    ["/resume", 415, "Unsupported file type. Upload a PDF or TXT resume."],
    ["/resume", 503, "OPENROUTER_API_KEY is not configured. Set it in .env and restart the backend."],
    ["/resume", 502, "The model did not return valid output after 2 attempt(s)."],
  ])("shows the backend's message for %s (HTTP %i)", async (match, status, detail) => {
    const user = userEvent.setup();
    backend.failNext(match, status, detail);
    render(<StartInterviewForm />);
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(detail);
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Continue|Try again/ })).toBeEnabled();
  });

  it("explains when the server cannot be reached", async () => {
    const user = userEvent.setup();
    backend.networkErrorNext("POST /api/interviews");
    render(<StartInterviewForm />);
    await fill(user);

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("retries a failed resume upload on the same session instead of creating another", async () => {
    const user = userEvent.setup();
    backend.failNext("/resume", 503, "OPENROUTER_API_KEY is not configured.");
    render(<StartInterviewForm />);
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/interview/session-1"));
    expect(backend.calls.filter((c) => c.path === "/api/interviews")).toHaveLength(1);
    expect(backend.count("POST", "/resume")).toBe(2);
  });

  it("creates a new interview if the role is changed after a failure", async () => {
    const user = userEvent.setup();
    backend.failNext("/resume", 422, "The text file contains no text.");
    render(<StartInterviewForm />);
    await fill(user, "first role");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("alert");

    await user.clear(screen.getByLabelText("Job role"));
    await user.type(screen.getByLabelText("Job role"), "second role");
    await user.click(screen.getByRole("button", { name: /Try again|Continue/ }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(backend.calls.filter((c) => c.path === "/api/interviews").map((c) => c.body)).toEqual([
      { role: "first role" },
      { role: "second role" },
    ]);
  });
});

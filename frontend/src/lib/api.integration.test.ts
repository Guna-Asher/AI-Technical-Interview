// Runs the real API client against the running FastAPI backend (npm run test:integration).
// It performs NO writes: every call here is rejected by the backend before anything is saved,
// so it can be run against the development database without leaving rows behind.
import { beforeAll, describe, expect, it } from "vitest";
import {
  ApiError,
  completeInterview,
  createInterview,
  generateQuestions,
  getInterview,
  getReport,
  listQuestions,
  submitAnswer,
  uploadResume,
} from "./api";

const base = process.env.INTEGRATION_API_URL;
const unknownId = "00000000-0000-0000-0000-000000000000";

beforeAll(() => {
  if (!base) throw new Error("Set INTEGRATION_API_URL (for example http://backend:8000) to run the integration tests.");
  process.env.NEXT_PUBLIC_API_BASE_URL = base;
});

async function failure(call: () => Promise<unknown>): Promise<ApiError> {
  try {
    await call();
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("expected the call to be rejected");
}

describe("real backend", () => {
  it("is healthy", async () => {
    const response = await fetch(`${base}/api/health`);

    expect(await response.json()).toEqual({ status: "ok", database: "ok" });
  });

  it.each([
    ["getInterview", () => getInterview(unknownId)],
    ["listQuestions", () => listQuestions(unknownId)],
    ["generateQuestions", () => generateQuestions(unknownId)],
    ["completeInterview", () => completeInterview(unknownId)],
    ["getReport", () => getReport(unknownId)],
    ["uploadResume", () => uploadResume(unknownId, new File(["synthetic resume"], "resume.txt", { type: "text/plain" }))],
  ])("%s reports an unknown session as a readable 404", async (_name, call) => {
    const error = await failure(call);

    expect([error.status, error.message]).toEqual([404, "Interview session not found"]);
  });

  it("reports an unknown session or question on answer submission as 404", async () => {
    const error = await failure(() => submitAnswer(unknownId, unknownId, "synthetic answer"));

    expect([error.status, error.message]).toEqual([404, "Interview session not found"]);
  });

  it("turns FastAPI validation errors (an array detail) into a readable message", async () => {
    const malformed = await failure(() => getInterview("not-a-uuid"));
    const blankAnswer = await failure(() => submitAnswer(unknownId, unknownId, "   "));
    const blankRole = await failure(() => createInterview("   "));

    expect(malformed.status).toBe(422);
    expect(malformed.message).toMatch(/^session_id: .*UUID/i);
    expect([blankAnswer.status, blankAnswer.message]).toEqual([422, expect.stringMatching(/^answer_text: /)]);
    expect([blankRole.status, blankRole.message]).toEqual([422, expect.stringMatching(/^role: /)]);
  });
});

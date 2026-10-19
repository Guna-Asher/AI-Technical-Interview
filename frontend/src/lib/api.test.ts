import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createInterview,
  generateQuestions,
  getInterview,
  listQuestions,
  submitAnswer,
  uploadResume,
} from "./api";

// Response bodies below follow the real backend's shapes; the values are synthetic test data.
const fetchMock = vi.fn();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("requests", () => {
  it("createInterview POSTs the role as JSON", async () => {
    fetchMock.mockResolvedValue(json({ id: "s1", role: "a role" }, 201));

    const result = await createInterview("a role");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/interviews");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ role: "a role" });
    expect(result).toMatchObject({ id: "s1" });
  });

  it("uploadResume POSTs multipart form data with the field 'file' and no manual content type", async () => {
    fetchMock.mockResolvedValue(json({ id: "s1" }));
    const file = new File(["resume text"], "resume.txt", { type: "text/plain" });

    await uploadResume("s1", file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/interviews/s1/resume");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    expect(init.headers).toBeUndefined();
  });

  it("getInterview and listQuestions use GET", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json([])));  // a fresh Response per call: bodies can be read once

    await getInterview("s1");
    await listQuestions("s1");

    expect(fetchMock.mock.calls.map(([url, init]) => [url, init?.method])).toEqual([
      ["http://api.test/api/interviews/s1", undefined],
      ["http://api.test/api/interviews/s1/questions", undefined],
    ]);
  });

  it("generateQuestions POSTs to the questions endpoint", async () => {
    fetchMock.mockResolvedValue(json([], 201));

    await generateQuestions("s1");

    const [url, init] = fetchMock.mock.calls[0];
    expect([url, init.method]).toEqual(["http://api.test/api/interviews/s1/questions", "POST"]);
  });

  it("submitAnswer POSTs answer_text to the question's answer endpoint", async () => {
    fetchMock.mockResolvedValue(json({ id: "a1", question_id: "q1", answer_text: "text", created_at: "t" }, 201));

    const answer = await submitAnswer("s1", "q1", "my answer");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/interviews/s1/questions/q1/answer");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ answer_text: "my answer" });
    expect(answer.id).toBe("a1");
  });

  it("encodes path parameters", async () => {
    fetchMock.mockResolvedValue(json({}));

    await getInterview("a/b?c");

    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/interviews/a%2Fb%3Fc");
  });

  it("uses the configured base URL and falls back to localhost:8000", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", undefined as unknown as string);
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    fetchMock.mockResolvedValue(json({}));

    await getInterview("s1");

    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/interviews/s1");
  });
});

describe("errors", () => {
  async function failure(response: Response | Error): Promise<ApiError> {
    if (response instanceof Error) fetchMock.mockRejectedValue(response);
    else fetchMock.mockResolvedValue(response);
    try {
      await getInterview("s1");
    } catch (error) {
      return error as ApiError;
    }
    throw new Error("expected the request to fail");
  }

  it("uses a string detail as the message and keeps the status", async () => {
    const error = await failure(json({ detail: "Interview session not found" }, 404));

    expect(error).toBeInstanceOf(ApiError);
    expect([error.status, error.message]).toEqual([404, "Interview session not found"]);
  });

  it("formats FastAPI validation-array details", async () => {
    const detail = [
      { type: "string_too_short", loc: ["body", "role"], msg: "String should have at least 1 character" },
      { type: "missing", loc: ["body", "candidate_profile"], msg: "Field required" },
    ];

    const error = await failure(json({ detail }, 422));

    expect(error.message).toBe("role: String should have at least 1 character; candidate_profile: Field required");
  });

  it("falls back to a generic message for non-JSON error bodies", async () => {
    const error = await failure(new Response("<html>Bad gateway</html>", { status: 502 }));

    expect([error.status, error.message]).toEqual([502, "The request failed (HTTP 502)."]);
  });

  it("turns a network failure into a readable status-0 error", async () => {
    const error = await failure(new TypeError("Failed to fetch"));

    expect(error.status).toBe(0);
    expect(error.message).toMatch(/Cannot reach the server/);
  });
});

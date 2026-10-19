import type { Answer, Interview, Question } from "./types";

/** Browser-facing backend URL (not the Docker hostname). Read at call time so tests can change it. */
function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export class ApiError extends Error {
  /** HTTP status, or 0 when the server could not be reached. */
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Readable message from a FastAPI error body: `detail` is a string, or a list of validation problems. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const detail = (await response.json())?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((problem: { loc?: unknown[]; msg?: string }) => {
          const field = problem.loc?.filter((part) => typeof part === "string" && part !== "body").pop();
          return field ? `${field}: ${problem.msg}` : (problem.msg ?? "Invalid request");
        })
        .join("; ");
    }
  } catch {
    // body was not JSON
  }
  return `The request failed (HTTP ${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that the backend is running and try again.");
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}

const id = encodeURIComponent;

export function createInterview(role: string): Promise<Interview> {
  return request("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
}

export function uploadResume(sessionId: string, file: File): Promise<Interview> {
  const form = new FormData();
  form.append("file", file);
  return request(`/api/interviews/${id(sessionId)}/resume`, { method: "POST", body: form });
}

export function getInterview(sessionId: string): Promise<Interview> {
  return request(`/api/interviews/${id(sessionId)}`);
}

export function listQuestions(sessionId: string): Promise<Question[]> {
  return request(`/api/interviews/${id(sessionId)}/questions`);
}

export function generateQuestions(sessionId: string): Promise<Question[]> {
  return request(`/api/interviews/${id(sessionId)}/questions`, { method: "POST" });
}

export function submitAnswer(sessionId: string, questionId: string, answerText: string): Promise<Answer> {
  return request(`/api/interviews/${id(sessionId)}/questions/${id(questionId)}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer_text: answerText }),
  });
}

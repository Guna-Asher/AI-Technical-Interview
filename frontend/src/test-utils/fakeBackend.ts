// An in-memory stand-in for the FastAPI backend, used only by component tests (never by the app).
// It follows the real endpoints' status codes and response shapes; all data is synthetic.
import type { Answer, CandidateProfile, Interview, Question } from "@/lib/types";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export const PROFILE: CandidateProfile = {
  summary: "Synthetic profile summary.",
  skills: ["skill-a"],
  technologies: ["tech-a"],
  experience: ["did thing-a"],
};

export function makeQuestion(n: number, overrides: Partial<Question> = {}): Question {
  return {
    id: `q${n}`,
    position: n,
    question_text: `Synthetic question number ${n}?`,
    topic: `topic ${n}`,
    difficulty: "medium",
    source_chunks: [{ chunk_id: `c${n}`, source_file: "book.pdf", source_title: `Synthetic Book ${n}`, page: n + 10, score: 0.5 }],
    created_at: "2026-01-01T00:00:00Z",
    answer: null,
    ...overrides,
  };
}

export function makeAnswer(question: Question, text: string): Answer {
  return { id: `a-${question.id}`, question_id: question.id, answer_text: text, created_at: "2026-01-01T00:01:00Z" };
}

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export class FakeBackend {
  interview: Interview | null = null;
  questions: Question[] = [];
  /** What POST .../questions will create. */
  toGenerate: Question[] = [];
  /** The profile POST .../resume will save. */
  resumeProfile: CandidateProfile = PROFILE;
  calls: Call[] = [];

  private oneShot: { match: string; make: () => Response | Error }[] = [];
  private holds: { match: string; gate: Promise<void> }[] = [];

  /** Start with an existing session (as after a page refresh). */
  seed(interview: Partial<Interview> = {}, questions: Question[] = []): this {
    this.interview = {
      id: "session-1",
      role: "synthetic role",
      status: questions.length ? "in_progress" : "created",
      candidate_profile: PROFILE,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      ...interview,
    };
    this.questions = questions;
    return this;
  }

  /** The next request whose "METHOD /path" contains `match` fails with this status and detail. */
  failNext(match: string, status: number, detail: unknown): this {
    this.oneShot.push({ match, make: () => reply({ detail }, status) });
    return this;
  }

  networkErrorNext(match: string): this {
    this.oneShot.push({ match, make: () => new TypeError("Failed to fetch") });
    return this;
  }

  /** The next matching request waits until the returned function is called. */
  hold(match: string): () => void {
    let release!: () => void;
    this.holds.push({ match, gate: new Promise<void>((resolve) => (release = resolve)) });
    return release;
  }

  count(method: string, pathPart: string): number {
    return this.calls.filter((c) => c.method === method && c.path.includes(pathPart)).length;
  }

  fetch = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
    const path = new URL(String(input)).pathname;
    const method = (init.method ?? "GET").toUpperCase();
    let body: unknown;
    if (typeof init.body === "string") body = JSON.parse(init.body);
    else if (init.body instanceof FormData) body = { file: (init.body.get("file") as File | null)?.name };
    this.calls.push({ method, path, body });

    const key = `${method} ${path}`;
    const heldAt = this.holds.findIndex((h) => key.includes(h.match));
    if (heldAt >= 0) await this.holds.splice(heldAt, 1)[0].gate;
    const failAt = this.oneShot.findIndex((o) => key.includes(o.match));
    if (failAt >= 0) {
      const outcome = this.oneShot.splice(failAt, 1)[0].make();
      if (outcome instanceof Error) throw outcome;
      return outcome;
    }
    return this.route(method, path, body);
  };

  private route(method: string, path: string, body: unknown): Response {
    if (method === "POST" && path === "/api/interviews") {
      this.interview = {
        id: "session-1",
        role: (body as { role: string }).role,
        status: "created",
        candidate_profile: null,
        created_at: "2026-01-01T00:00:00Z",
        completed_at: null,
      };
      return reply(this.interview, 201);
    }
    const match = path.match(/^\/api\/interviews\/([^/]+)(?:\/(resume|questions)(?:\/([^/]+)\/answer)?)?$/);
    if (!match) return reply({ detail: "Not Found" }, 404);
    const [, sessionId, part, questionId] = match;
    if (!this.interview || this.interview.id !== sessionId) return reply({ detail: "Interview session not found" }, 404);

    if (!part && method === "GET") return reply(this.interview);
    if (part === "resume" && method === "POST") {
      this.interview.candidate_profile = this.resumeProfile;
      return reply(this.interview);
    }
    if (part === "questions" && !questionId && method === "GET") return reply(this.questions);
    if (part === "questions" && !questionId && method === "POST") {
      if (this.questions.length) return reply({ detail: "Questions have already been generated for this interview" }, 409);
      this.questions = this.toGenerate.map((q) => ({ ...q }));
      this.interview.status = "in_progress";
      return reply(this.questions, 201);
    }
    if (part === "questions" && questionId && method === "POST") {
      const question = this.questions.find((q) => q.id === questionId);
      if (!question) return reply({ detail: "Question not found in this interview" }, 404);
      if (question.answer) return reply({ detail: "This question has already been answered" }, 409);
      question.answer = makeAnswer(question, (body as { answer_text: string }).answer_text.trim());
      return reply(question.answer, 201);
    }
    return reply({ detail: "Method Not Allowed" }, 405);
  }
}

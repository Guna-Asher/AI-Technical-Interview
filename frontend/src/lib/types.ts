// Response shapes of the FastAPI backend (see backend/app/schemas.py).

export interface CandidateProfile {
  summary: string | null;
  skills: string[];
  technologies: string[];
  experience: string[];
}

export interface Interview {
  id: string;
  role: string;
  status: string;
  candidate_profile: CandidateProfile | null;
  created_at: string;
  completed_at: string | null;
}

export interface SourceReference {
  chunk_id: string;
  source_file: string;
  source_title: string;
  page: number;
  score: number;
}

export type Assessment = "correct_and_complete" | "mostly_correct" | "partially_correct" | "incorrect_or_off_topic";

export interface FeedbackSource {
  chunk_id: string;
  source_file: string;
  source_title: string;
  page: number;
}

/** Qualitative AI feedback on one answer. There is deliberately no numeric score. */
export interface AnswerFeedback {
  assessment: Assessment;
  summary: string;
  strengths: string[];
  gaps: string[];
  suggestions: string[];
  /** True only when the backend verified at least one reference to a passage the question was based on. */
  grounded: boolean;
  source_chunks: FeedbackSource[];
}

export interface Answer {
  id: string;
  question_id: string;
  answer_text: string;
  created_at: string;
  feedback: AnswerFeedback | null;
}

export interface Question {
  id: string;
  position: number;
  question_text: string;
  topic: string | null;
  difficulty: string | null;
  source_chunks: SourceReference[];
  created_at: string;
  answer: Answer | null;
}

export interface Report {
  session_id: string;
  role: string;
  status: string;
  completed_at: string | null;
  created_at: string;
  summary: string;
  strengths: string[];
  improvement_topics: string[];
  recommendations: string[];
  questions: Question[];
  /** Number of answers evaluated without reference passages. */
  ungrounded_evaluations: number;
}

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

export interface Answer {
  id: string;
  question_id: string;
  answer_text: string;
  created_at: string;
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

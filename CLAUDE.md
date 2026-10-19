# Project Instructions

## 1. Project Overview

Build an AI-powered, role-based technical interview application.

Candidates upload their resumes, select a job role, answer personalized technical interview questions, and receive a final interview report.

Questions must be generated using the candidate's resume, selected role, and relevant information retrieved from a technical knowledge base using Retrieval-Augmented Generation (RAG).

The goal is to deliver a clean, accurate, fully working end-to-end application that satisfies the internship assignment.

Read `docs/PRD.md` before implementing project features. It contains the detailed product requirements.

## 2. Technology Stack

Use the following agreed technologies:

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS.
- **Backend:** Python and FastAPI.
- **Application database:** PostgreSQL.
- **Database access:** SQLAlchemy.
- **Database migrations:** Alembic.
- **Resume and document parsing:** PyMuPDF.
- **Embeddings:** Sentence Transformers using `all-MiniLM-L6-v2`.
- **Vector database:** Chroma.
- **LLM provider:** OpenRouter API.
- **Backend testing:** Pytest.
- **Frontend testing:** Vitest and React Testing Library where appropriate.
- **Runtime and infrastructure:** Docker and Docker Compose.

Do not introduce alternative technologies or additional infrastructure without a genuine technical reason.

## 3. Engineering Philosophy

Build the simplest solution that correctly satisfies the requirements.

Our priorities are:

1. Complete, working functionality.
2. Clear and maintainable code.
3. Correct data handling and reliable application behaviour.
4. A straightforward developer setup.
5. Focused testing of important functionality.

Avoid overengineering. Do not build an enterprise platform when a simple application is sufficient.

Keep responsibilities separated, but introduce abstractions only when they make the code easier to understand or maintain.

Do not add microservices, Kubernetes, Redis, background job queues, agent frameworks, or unnecessary dependencies.

Handle common errors properly, but do not spend excessive time on unlikely edge cases or optional improvements.

Implement the required workflow before adding extra features or polishing minor details.

## 4. Architecture

Use a simple modular monolith.

The Next.js frontend communicates with the FastAPI backend over HTTP.

The FastAPI backend handles business logic, resume processing, interview sessions, RAG orchestration, OpenRouter requests, and application data access.

PostgreSQL stores application data, including interview sessions, questions, answers, feedback, and reports.

Chroma stores the technical knowledge chunks and their embeddings.

Sentence Transformers generates embeddings locally inside the backend container.

OpenRouter provides the language model used for question generation and interview feedback.

Keep the frontend, backend, database, vector store, and external LLM integration separate according to their responsibilities. Do not create additional services unless necessary.

## 5. Docker-First Development

Docker Compose is the standard way to run the application from the beginning.

The application must include these services:

- `frontend`
- `backend`
- `postgres`
- `chroma`

Provide the necessary Dockerfiles, `compose.yaml`, environment configuration, and persistent volumes.

The developer should not need to install Node.js, Python, PostgreSQL, or Chroma directly on the host.

The intended startup command is:

`docker compose up --build`

Document any required first-run setup.

Run application commands, database migrations, tests that require the application environment, and knowledge ingestion inside the appropriate containers when practical.

Use environment variables for configuration. Keep `.env` out of version control and provide an `.env.example` file.

OpenRouter is an external API, not a Docker service.

## 6. AI and RAG Requirements

Implement the RAG pipeline explicitly and keep its steps understandable.

The pipeline must:

1. Extract text from the provided technical documents.
2. Split the text into manageable chunks.
3. Preserve useful source metadata, including page information when available.
4. Generate embeddings using the configured local embedding model.
5. Store and retrieve chunks using Chroma.
6. Construct retrieval queries using the candidate's resume and selected role.
7. Pass relevant retrieved context to OpenRouter for question generation.
8. Preserve references to the knowledge chunks used for each question.

Knowledge ingestion must be a separate, repeatable operation. Do not re-ingest documents on every interview request.

Use the technical books specified in the internship assignment as the primary knowledge sources. Do not pretend a source covers topics it does not actually address.

Keep the number of supported roles and knowledge sources manageable until the core workflow works.

## 7. OpenRouter Integration

All LLM requests must go through OpenRouter.

Read the API key and model identifier from environment variables:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`

Keep credentials on the backend. Never expose the API key to the browser or commit real credentials to the repository.

Validate LLM responses before using or saving them. Handle common provider errors without corrupting interview data.

Do not make live LLM API calls in ordinary automated tests when mocked responses are sufficient.

## 8. Development Workflow

Work in small, clearly defined phases.

For each phase:

1. Inspect the current project and relevant files.
2. Understand the existing implementation before modifying it.
3. Identify the smallest set of changes needed to complete the requested task.
4. Implement only the current phase.
5. Run relevant tests and verification checks.
6. Fix meaningful issues within the scope of the phase.
7. Summarize changes, test results, and remaining blockers.
8. Stop and wait for the next instruction.

For substantial phases, use Plan Mode to develop a focused implementation plan before switching to implementation.

Do not implement future phases without approval.

Our development workflow is interactive: the user will review each phase's results before requesting the next phase.

Do not repeatedly ask for decisions that have already been established in this file or the PRD. Make reasonable implementation decisions within the agreed requirements.

## 9. Code Quality and Testing

Write straightforward, readable code with clear naming and appropriate type annotations.

Keep configuration centralized and avoid unnecessary duplication.

Use database migrations for schema changes.

Test important business logic, API behaviour, data persistence, and the end-to-end interview workflow.

Do not create excessive tests for trivial implementation details.

Never claim that a test, build, service, or feature works unless it has actually been verified.

When something fails, investigate the underlying cause. Fix meaningful problems without allowing minor, unrelated issues to derail progress.

Preserve existing working functionality when making changes.

## 10. Scope and Priorities

The required end-to-end workflow is the priority:

1. Upload a resume.
2. Select a supported interview role.
3. Extract relevant candidate information.
4. Retrieve relevant technical knowledge.
5. Generate contextual interview questions.
6. Collect and save answers.
7. Generate feedback.
8. Produce and save a final interview report.

Authentication, voice interviews, advanced analytics, adaptive interviewing, and other optional enhancements must not delay the required workflow.

## 11. Definition of Success

The project is successful when a candidate can complete the interview workflow from resume upload to final report, questions are meaningfully grounded in retrieved knowledge, application data persists correctly, and the entire application can be run through Docker Compose using the documented instructions.

**Working functionality first. Clean engineering throughout. Additional complexity only when it solves a real problem.**
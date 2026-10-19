# AI Technical Interview

A role-based technical interview app: upload a resume, pick a role, answer questions grounded in a technical knowledge base (RAG), and get a final report. See `docs/PRD.md` for requirements.

**Status: Phase 6 (evaluation and final report).** The four services run, technical PDFs can be ingested into Chroma, and a candidate can enter a role, upload a resume, answer the generated questions in the browser, finish the interview, and read a saved report with feedback on every answer. Everything is stored in PostgreSQL and survives a refresh or restart.

## Run

Prerequisite: Docker with Docker Compose. No local Node.js, Python, PostgreSQL or Chroma is needed.

```bash
cp .env.example .env      # optional: defaults in compose.yaml also work
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/health |

The backend applies database migrations (`alembic upgrade head`) automatically on startup, so no first-run setup is needed.

PostgreSQL and Chroma are reachable only inside the Docker network (`postgres:5432`, `chroma:8000`). Their data lives in the named volumes `postgres_data` and `chroma_data`; `docker compose down` keeps it, `docker compose down -v` deletes it.

`OPENROUTER_API_KEY` and `OPENROUTER_MODEL` are not needed yet (required from the LLM phase).

## Interface and identity

The interface uses one set of design tokens (colours, type, spacing) defined in `frontend/src/app/globals.css`, small shared components in `frontend/src/components/ui/`, and system font stacks (no font downloads). The product name is a single constant in `frontend/src/lib/brand.ts`, and the favicon is `frontend/src/app/icon.svg`. The framework's dev badge and `X-Powered-By` header are switched off in `frontend/next.config.ts`. All interview content shown (roles, questions, answers, feedback, reports) comes from the backend; only labels and layout are predefined. The layout works from phone to desktop widths, shows visible keyboard focus, and respects the reduced-motion setting.

## Using the app

1. Open http://localhost:3000, type the job role (free text; there is no preset list) and choose a PDF or TXT resume.
2. After the resume is processed you land on `/interview/<session id>`. Press **Start interview** to generate the questions (once per interview).
3. Answer the questions one at a time. Each answer is saved by the backend before it is shown as submitted.
4. When every question is answered, press **Finish interview and get my report**. The backend evaluates each answer with the AI model and then writes the report; this takes several model calls and can take a few minutes. Your answers are already saved while it runs.

The report shows an overall summary, strengths, topics to improve, recommendations, and per-question feedback with the sources each question was based on. **It is AI-generated guidance, not a measurement of ability.**

Progress is stored by the backend, not the browser. **Refreshing the page, or reopening the same `/interview/<session id>` address, restores your saved answers and continues at the first unanswered question.** Bookmark that address; there is no login, so the address is the way back to an interview.

Answer API: `POST /api/interviews/{session_id}/questions/{question_id}/answer` with `{"answer_text": "..."}` returns 201. It returns 404 if the session or question does not exist (or the question belongs to another session), 409 if the question was already answered (answers are never overwritten), and 422 for a blank, over-long (10,000 characters) or malformed body. `GET /api/interviews/{session_id}/questions` includes each question's saved `answer` (or `null`).

This needs `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` and an ingested knowledge base (see below); without them the UI shows the backend's explanation (for example that the key is missing or the knowledge base is empty). **The full flow with a live model and real books has not been verified yet; it is covered by automated tests with mocked responses.**

### Finishing an interview (evaluation and report)

- `POST /api/interviews/{session_id}/complete` evaluates every saved answer that has no feedback yet, then writes and saves the report. It returns `201` with the report, or `200` with the existing report if the interview was already completed. It returns `409` (naming the unanswered questions) if any question has no answer, and `429`/`502`/`503`/`504` for OpenRouter problems.
- `GET /api/interviews/{session_id}/report` returns the saved report (`404` until one exists).
- **Safe to retry.** Each evaluation is saved as soon as it is valid, so after a provider error the retry continues with the remaining answers, and if only the report step failed the retry only writes the report. Invalid model output is never saved. Submitted answers are never changed or lost. A repeated request returns the same report and does not create a second one.
- **Grounding.** When a question is generated, the exact text of each passage it cites is saved with the question. Evaluation judges the answer against those saved passages (never against whatever is in Chroma later), and a grounded evaluation must cite at least one of them. If a question has no saved passage text (for example data saved by an older version), its answer is still evaluated, but clearly labelled as evaluated without reference passages, and the report says how many answers were. The passage text is never returned by the API or shown in the UI; only source title and page are.
- Feedback is qualitative: a coarse assessment label plus written strengths, gaps and suggestions. There is no numeric score.
- Answer text, passages and the interview data are passed to the model as delimited data that it is told to treat as reference material, and its output is validated before anything is saved. This reduces but cannot eliminate prompt-injection risk.
- **Verification status:** this flow is covered by automated tests with mocked model replies and synthetic data. **A live OpenRouter run and real-book content have not been verified** (no API key and no technical PDFs have been supplied), so evaluation quality, the chosen model's JSON compliance, the total processing time and a real-browser walkthrough are untested.

## Knowledge base (RAG)

The knowledge base is built from technical PDFs that **you supply**; none ship with the application. Put them in `./knowledge` (or any folder, via `KNOWLEDGE_HOST_DIR` in `.env`). The folder is mounted read-only at `/knowledge` in the backend container, and PDFs in subfolders are included.

```bash
docker compose exec backend python -m app.rag.ingest                    # extract, chunk, embed and store the PDFs in Chroma
docker compose exec backend python -m app.rag.retrieval "your query"    # search it (add --min-score 0 to see raw scores)
```

- Ingestion is a separate, repeatable command and never runs during API requests. Re-running it skips unchanged files and replaces changed ones, so chunks are not duplicated.
- It exits with an error if the folder is missing or has no PDFs. PDFs without extractable text (for example scans; OCR is not supported) are reported and skipped; unreadable PDFs are reported and make the command exit non-zero after the others are processed.
- Embeddings are computed locally with `all-MiniLM-L6-v2`. The model downloads on first use (needs network) and is cached in the `hf_cache` volume.
- Each chunk keeps its source file, title and **physical** PDF page number (1-based; this can differ from the page number printed in the book).
- Retrieval returns only chunks with a cosine similarity of at least `RETRIEVAL_MIN_SCORE` (default `0.25`). That default is an **uncalibrated starting value**, and a similarity score is a ranking signal, not a probability or a reliable confidence measure. An empty result means nothing cleared the threshold.
- **Verification status:** the pipeline is tested with synthetic PDFs inside isolated tests only. Ingestion and retrieval on the assignment's actual technical books have **not been verified** yet, because those PDFs have not been supplied.

## Interview API (resume and questions)

Needs `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env` (see `.env.example`) and an ingested knowledge base. The app starts without them; the operations below return a clear error until they are set.

```bash
# 1. Create a session. The role is free text; there is no list of supported roles.
curl -s -X POST localhost:8000/api/interviews -H 'Content-Type: application/json' -d '{"role": "<the role you are interviewing for>"}'

# 2. Upload a resume (PDF or TXT, max 5 MB). The model extracts a structured profile from it.
curl -s -X POST localhost:8000/api/interviews/<id>/resume -F file=@resume.pdf

# 3. Generate questions (default 5). They are grounded in passages retrieved from the knowledge base.
curl -s -X POST localhost:8000/api/interviews/<id>/questions

# 4. Read them back
curl -s localhost:8000/api/interviews/<id>/questions
```

- Questions are generated only once per session (a second request returns 409), and only if the knowledge base has enough relevant passages for the role and profile (otherwise 422 with the reason; nothing is saved). The resume can no longer be replaced after questions exist.
- Every stored source reference (`chunk_id`, file, title, page, score) comes from a chunk that retrieval actually returned. Model-supplied identifiers are never trusted.
- Errors: 413 file too large, 415 unsupported type, 422 unreadable/empty file or insufficient knowledge, 409 state conflict, 429/502/504 provider problems, 503 missing OpenRouter configuration or unreachable Chroma.
- **Privacy:** the extracted resume text is sent to the OpenRouter model you configure. The uploaded file and its text are processed in memory and are not stored or logged; only the extracted profile is saved.
- **Untrusted input:** resume text, retrieved passages, the role and the profile are passed to the model as delimited data with an instruction to treat them as reference material, not instructions, and the model's output is validated before anything is saved. This reduces but cannot eliminate prompt-injection risk. Render question text as plain text in any UI.
- Tunable (optional, in `.env`): `QUESTION_COUNT`, `CONTEXT_CHUNKS`, `MIN_CONTEXT_CHUNKS`, `MAX_RETRIEVAL_QUERIES`, `MAX_RESUME_BYTES`, `MAX_RESUME_CHARS`, `OPENROUTER_TIMEOUT_SECONDS`, `LLM_MAX_ATTEMPTS`. These are operational heuristics, not calibrated values.
- **Verification status:** the flow is covered by automated tests that use mocked OpenRouter replies and synthetic data in isolated tests. **A live OpenRouter run and real-book retrieval have not been verified** (no API key and no technical PDFs have been supplied yet), so the behaviour of your chosen model, prompt quality and its resistance to injected instructions are untested.

## Database migrations

```bash
docker compose exec backend alembic current                                   # show applied revision
docker compose exec backend alembic upgrade head                              # apply migrations (also runs on startup)
docker compose exec backend alembic revision --autogenerate -m "describe change"   # after editing app/models.py
```

Review every autogenerated migration before applying it.

## Development

The frontend (Next.js dev server) and backend (`uvicorn --reload`) mount their source from the host, so code edits reload without rebuilding. Rebuild only when dependencies change: `docker compose up --build`.

```bash
docker compose run --rm backend pytest -q                   # default suite: no network, no model download (uses a separate <db>_test database)
docker compose run --rm backend pytest -q -m real_model     # separate smoke test of the real embedding model (needs network on first run)
docker compose run --rm --no-deps frontend npm test                    # frontend unit and component tests (mocked backend)
docker compose run --rm frontend npm run test:integration            # frontend client vs the running backend (read-only; needs the stack up)
docker compose run --rm frontend npm run lint               # frontend lint
docker compose run --rm frontend npm run typecheck          # frontend types
docker compose run --rm frontend npm run build              # frontend production build check
```

`NEXT_PUBLIC_API_BASE_URL` must be the URL the **browser** can reach (`http://localhost:8000`), not the Docker hostname `backend`.

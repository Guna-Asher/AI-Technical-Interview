# AI Technical Interview

A role-based technical interview app: upload a resume, pick a role, answer questions grounded in a technical knowledge base (RAG), and get a final report. See `docs/PRD.md` for requirements.

**Status: Phase 4 (resume processing and question generation).** The four services run, the database schema is managed by Alembic, technical PDFs can be ingested into Chroma and searched, and the API can turn a resume into a candidate profile and generate interview questions grounded in retrieved passages. Answering questions, reports and the interview UI come in later phases.

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
docker compose run --rm frontend npm run lint               # frontend lint
docker compose run --rm frontend npm run typecheck          # frontend types
docker compose run --rm frontend npm run build              # frontend production build check
```

`NEXT_PUBLIC_API_BASE_URL` must be the URL the **browser** can reach (`http://localhost:8000`), not the Docker hostname `backend`.

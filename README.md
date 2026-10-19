# AI Technical Interview

A role-based technical interview app: upload a resume, pick a role, answer questions grounded in a technical knowledge base (RAG), and get a final report. See `docs/PRD.md` for requirements.

**Status: Phase 1 (foundation).** The four services run and talk to each other; interview features come in later phases.

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

PostgreSQL and Chroma are reachable only inside the Docker network (`postgres:5432`, `chroma:8000`). Their data lives in the named volumes `postgres_data` and `chroma_data`; `docker compose down` keeps it, `docker compose down -v` deletes it.

`OPENROUTER_API_KEY` and `OPENROUTER_MODEL` are not needed yet (required from the LLM phase).

## Development

The frontend (Next.js dev server) and backend (`uvicorn --reload`) mount their source from the host, so code edits reload without rebuilding. Rebuild only when dependencies change: `docker compose up --build`.

```bash
docker compose run --rm backend pytest -q                   # backend tests
docker compose run --rm frontend npm run lint               # frontend lint
docker compose run --rm frontend npm run typecheck          # frontend types
docker compose run --rm frontend npm run build              # frontend production build check
```

`NEXT_PUBLIC_API_BASE_URL` must be the URL the **browser** can reach (`http://localhost:8000`), not the Docker hostname `backend`.

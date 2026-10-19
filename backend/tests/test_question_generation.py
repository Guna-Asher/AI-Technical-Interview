import pytest

from app.config import get_settings
from app.openrouter import LLMBadResponse
from app.question_generation import (
    NoRelevantKnowledge,
    build_retrieval_queries,
    gather_context,
    generate_questions,
    validate_questions,
)
from app.rag.retrieval import RetrievedChunk
from app.schemas import CandidateProfile
from tests.test_openrouter_client import FakeLLM

# Everything below is synthetic: made-up roles, profiles, passages and model replies used only by these tests.
PROFILE = CandidateProfile(summary=None, skills=["query tuning"], technologies=["postgres", "caching"], experience=[])


def make_chunk(n: int, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(f"book.pdf::p{n}::c0", f"passage text {n}", "book.pdf", "Synthetic Book", n, 0, score)


PASSAGES = [make_chunk(1, 0.9), make_chunk(2, 0.7), make_chunk(3, 0.5)]


def question(n: int = 1, **overrides: object) -> dict:
    return {"question": f"Synthetic question number {n} about the passages?", "topic": f"topic {n}", "difficulty": "medium", "source_refs": [1], **overrides}


def reply(count: int = 5, **overrides: object) -> dict:
    return {"questions": [question(i, **overrides) for i in range(1, count + 1)]}


# --- Query construction from the session's own data ---


def test_queries_contain_the_sessions_role_and_profile_items() -> None:
    profile = CandidateProfile(summary="Backend focused.", skills=["skill-x"], technologies=["tech-y"], experience=["built thing-z"])

    queries = build_retrieval_queries("role-r", profile, max_queries=10)

    assert queries[0] == "role-r. Backend focused."
    assert "role-r: tech-y, skill-x" in queries
    assert "role-r: built thing-z" in queries


def test_different_sessions_produce_different_queries() -> None:
    a = build_retrieval_queries("role-one", CandidateProfile(technologies=["alpha"]), 4)
    b = build_retrieval_queries("role-two", CandidateProfile(technologies=["beta"]), 4)

    assert set(a).isdisjoint(b)
    assert all("alpha" in q or q == "role-one" for q in a)


def test_role_only_profile_yields_just_the_role_with_no_fixed_fallback() -> None:
    assert build_retrieval_queries("only-a-role", CandidateProfile(), 4) == ["only-a-role"]


def test_profile_items_are_grouped_and_the_number_of_queries_is_capped() -> None:
    profile = CandidateProfile(technologies=[f"tech{i}" for i in range(20)], skills=[f"skill{i}" for i in range(20)], experience=["e1", "e2"])

    queries = build_retrieval_queries("r", profile, max_queries=4)

    assert len(queries) == 4
    assert queries[1] == "r: tech0, tech1, tech2, tech3, tech4, tech5"
    assert len(set(queries)) == 4


def test_long_queries_are_truncated() -> None:
    assert all(len(q) <= 500 for q in build_retrieval_queries("r", CandidateProfile(summary="s" * 1900), 4))


# --- Retrieval and context ---


def test_context_is_retrieved_at_runtime_from_the_knowledge_base(seeded_knowledge: str) -> None:
    chunks = gather_context("synthetic backend role", PROFILE)

    assert len(chunks) >= 3
    assert [c.score for c in chunks] == sorted((c.score for c in chunks), reverse=True)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert all("Tomato" not in c.text for c in chunks)  # the unrelated passage is not returned
    assert all(c.source_file in {"a.pdf", "b.pdf"} and c.page >= 1 for c in chunks)


def test_empty_knowledge_base_raises_an_actionable_error(rag_collection: str) -> None:
    with pytest.raises(NoRelevantKnowledge, match="knowledge base is empty.*ingest"):
        gather_context("synthetic backend role", PROFILE)


def test_too_few_relevant_passages_raises(seeded_knowledge: str) -> None:
    unrelated = CandidateProfile(technologies=["xylophone"])

    with pytest.raises(NoRelevantKnowledge, match=r"Only \d sufficiently relevant.*at least 3 are needed"):
        gather_context("zzz qqq", unrelated)


def test_results_from_several_queries_are_merged_keeping_the_best_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.question_generation.indexed_chunk_count", lambda: 10)
    scores = iter([0.3, 0.8])

    def fake_retrieve(query: str) -> list[RetrievedChunk]:
        return [make_chunk(1, next(scores)), make_chunk(2, 0.6), make_chunk(3, 0.4)]

    monkeypatch.setattr("app.question_generation.retrieve", fake_retrieve)

    chunks = gather_context("role", CandidateProfile(technologies=["t"]))

    assert [c.chunk_id for c in chunks] == ["book.pdf::p1::c0", "book.pdf::p2::c0", "book.pdf::p3::c0"]
    assert chunks[0].score == 0.8


def test_context_is_capped_at_context_chunks(seeded_knowledge: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTEXT_CHUNKS", "3")
    get_settings.cache_clear()

    assert len(gather_context("synthetic backend role", PROFILE)) == 3


# --- Output validation ---


def test_valid_reply_maps_references_to_the_retrieved_chunks() -> None:
    data = {"questions": [question(1, source_refs=[1, 3]), question(2, source_refs=[2])]}

    result = validate_questions(data, PASSAGES, count=2)

    assert [q.position for q in result] == [1, 2]
    assert [c["chunk_id"] for c in result[0].source_chunks] == ["book.pdf::p1::c0", "book.pdf::p3::c0"]
    assert result[0].source_chunks[0] == {
        "chunk_id": "book.pdf::p1::c0",
        "source_file": "book.pdf",
        "source_title": "Synthetic Book",
        "page": 1,
        "score": 0.9,
        "text": "passage text 1",
    }
    assert result[1].source_chunks[0]["page"] == 2


def test_the_original_retrieved_text_is_saved_with_each_cited_chunk() -> None:
    data = {"questions": [question(1, source_refs=[2]), question(2, source_refs=[1, 3])]}

    first, second = validate_questions(data, PASSAGES, count=2)

    assert [c["text"] for c in first.source_chunks] == [PASSAGES[1].text]  # only the cited passage is stored
    assert [(c["chunk_id"], c["text"]) for c in second.source_chunks] == [(PASSAGES[0].chunk_id, PASSAGES[0].text), (PASSAGES[2].chunk_id, PASSAGES[2].text)]
    assert all(set(c) == {"chunk_id", "source_file", "source_title", "page", "score", "text"} for c in first.source_chunks)


def test_text_supplied_by_the_model_is_never_stored() -> None:
    forged = question(1, text="FORGED PASSAGE TEXT", source_chunks=[{"chunk_id": "x", "text": "FORGED PASSAGE TEXT"}])

    [result] = validate_questions({"questions": [forged]}, PASSAGES, count=1)

    assert result.source_chunks[0]["text"] == "passage text 1"
    assert "FORGED" not in str(result)


def test_fields_invented_by_the_model_are_ignored() -> None:
    forged = question(1, chunk_id="forged-id", source_chunks=[{"chunk_id": "forged-id", "page": 999}], page=999, source_title="Forged")

    [result] = validate_questions({"questions": [forged]}, PASSAGES, count=1)

    assert [c["chunk_id"] for c in result.source_chunks] == ["book.pdf::p1::c0"]
    assert "forged" not in str(result).lower()


def test_difficulty_is_case_insensitive_and_duplicate_refs_are_collapsed() -> None:
    [result] = validate_questions({"questions": [question(1, difficulty=" Hard ", source_refs=[2, 2])]}, PASSAGES, count=1)

    assert result.difficulty == "hard"
    assert len(result.source_chunks) == 1


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"questions": "not a list"},
        {"questions": [question(1)]},  # wrong count (3 expected)
        {"questions": [question(i) for i in range(1, 5)]},
        {"questions": [question(1), question(2), "not an object"]},
        {"questions": [question(1), question(2), question(3, source_refs=[])]},
        {"questions": [question(1), question(2), question(3, source_refs=[0])]},
        {"questions": [question(1), question(2), question(3, source_refs=[4])]},
        {"questions": [question(1), question(2), question(3, source_refs=[99])]},
        {"questions": [question(1), question(2), question(3, source_refs=["1"])]},
        {"questions": [question(1), question(2), question(3, source_refs=[True])]},
        {"questions": [question(1), question(2), question(3, source_refs=1)]},
        {"questions": [question(1), question(2), question(3, difficulty="impossible")]},
        {"questions": [question(1), question(2), question(3, question="short")]},
        {"questions": [question(1), question(2), question(3, topic="")]},
        {"questions": [question(1), question(2), question(3, topic="t" * 101)]},
        {"questions": [question(1), question(2), {"topic": "x", "difficulty": "easy", "source_refs": [1]}]},
        {"questions": [question(1), question(2), question(2)]},  # duplicate text
    ],
)
def test_invalid_replies_are_rejected(data: dict) -> None:
    with pytest.raises(ValueError):
        validate_questions(data, PASSAGES, count=3)


# --- generate_questions: model call, retry, validation ---


def test_generation_returns_validated_questions() -> None:
    llm = FakeLLM(reply(5))

    result = generate_questions(llm, "role", PROFILE, PASSAGES, 5)  # type: ignore[arg-type]

    assert len(result) == 5
    assert len(llm.prompts) == 1


def test_an_invalid_first_reply_is_retried_once() -> None:
    llm = FakeLLM(reply(5, source_refs=[99]), reply(5))

    assert len(generate_questions(llm, "role", PROFILE, PASSAGES, 5)) == 5  # type: ignore[arg-type]
    assert "valid numbers are 1 to 3" in llm.prompts[1]


def test_two_invalid_replies_raise_bad_response() -> None:
    llm = FakeLLM(reply(2), reply(2))

    with pytest.raises(LLMBadResponse):
        generate_questions(llm, "role", PROFILE, PASSAGES, 5)  # type: ignore[arg-type]


def test_a_model_that_obeyed_an_injected_instruction_cannot_cite_unretrieved_sources() -> None:
    obeyed = reply(5, source_refs=[42], chunk_id="attacker-chosen")
    llm = FakeLLM(obeyed, obeyed)

    with pytest.raises(LLMBadResponse):
        generate_questions(llm, "role", PROFILE, PASSAGES, 5)  # type: ignore[arg-type]

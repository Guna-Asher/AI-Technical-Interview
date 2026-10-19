import pytest

from app.rag.documents import chunk_text

# Synthetic text used only to exercise the splitter.
SENTENCE = "Alpha beta gamma delta epsilon zeta eta theta iota kappa. "


def test_short_text_is_a_single_chunk() -> None:
    assert chunk_text("short synthetic text", size=100, overlap=10) == ["short synthetic text"]


def test_chunks_never_exceed_size_and_are_not_empty() -> None:
    chunks = chunk_text(SENTENCE * 40, size=200, overlap=40)

    assert len(chunks) > 1
    assert all(0 < len(c) <= 200 for c in chunks)


def test_consecutive_chunks_overlap() -> None:
    words = " ".join(f"w{i:03d}" for i in range(300))
    chunks = chunk_text(words, size=200, overlap=50)

    assert len(chunks) > 2
    for previous, following in zip(chunks, chunks[1:]):
        shared = set(previous.split()[-6:]) & set(following.split()[:8])
        assert shared, "expected the end of one chunk to reappear at the start of the next"


def test_no_text_is_lost() -> None:
    words = [f"w{i:03d}" for i in range(300)]
    chunks = chunk_text(" ".join(words), size=200, overlap=50)

    assert set(" ".join(chunks).split()) == set(words)


def test_very_long_unbroken_token_is_hard_split() -> None:
    chunks = chunk_text("x" * 1000, size=100, overlap=10)

    assert len(chunks) >= 10
    assert all(len(c) <= 100 for c in chunks)


def test_paragraph_breaks_are_preferred_split_points() -> None:
    first, second = "A" * 60, "B" * 60
    chunks = chunk_text(f"{first}\n\n{second}", size=100, overlap=10)

    assert chunks[0] == first
    assert second in chunks[1]


@pytest.mark.parametrize("size, overlap", [(0, 0), (-5, 0), (100, -1), (100, 100), (100, 150)])
def test_invalid_size_or_overlap_is_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size=size, overlap=overlap)

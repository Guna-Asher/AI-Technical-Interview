import httpx
import pytest

from app.openrouter import (
    LLMBadResponse,
    LLMNotConfigured,
    LLMProviderError,
    LLMRateLimited,
    LLMTimeout,
    OpenRouterClient,
    complete_validated,
    parse_json_object,
)

# No real OpenRouter requests are made: every client here uses an in-memory mock transport.

SECRET = "sk-test-secret-key"


def make_client(handler, api_key: str | None = SECRET, model: str | None = "test/model") -> OpenRouterClient:  # type: ignore[no-untyped-def]
    return OpenRouterClient(api_key, model, "https://example.test/api/v1/", 5.0, transport=httpx.MockTransport(handler))


def reply(content: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_success_returns_parsed_json_and_sends_expected_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return reply('{"ok": true}')

    result = make_client(handler).complete_json("system text", "user text", temperature=0.1)

    assert result == {"ok": True}
    request = seen[0]
    assert str(request.url) == "https://example.test/api/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    body = __import__("json").loads(request.content)
    assert body["model"] == "test/model"
    assert body["temperature"] == 0.1
    assert body["messages"] == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "user text"},
    ]


@pytest.mark.parametrize(
    "content",
    ['```json\n{"a": 1}\n```', '```\n{"a": 1}\n```', 'Here you go:\n{"a": 1}\nHope that helps.', '  {"a": 1}  '],
)
def test_json_wrapped_in_fences_or_prose_is_parsed(content: str) -> None:
    assert parse_json_object(content) == {"a": 1}


@pytest.mark.parametrize("api_key, model, missing", [(None, "m", "OPENROUTER_API_KEY"), ("", "m", "OPENROUTER_API_KEY"), ("k", None, "OPENROUTER_MODEL")])
def test_missing_configuration_raises_and_sends_no_request(api_key: str | None, model: str | None, missing: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return reply("{}")

    with pytest.raises(LLMNotConfigured, match=missing):
        make_client(handler, api_key=api_key, model=model).complete_json("s", "u")
    assert calls == []


def test_rate_limit_maps_to_llm_rate_limited() -> None:
    with pytest.raises(LLMRateLimited):
        make_client(lambda r: httpx.Response(429, json={"error": {"message": "slow down"}})).complete_json("s", "u")


@pytest.mark.parametrize("status", [401, 403, 500, 502, 400])
def test_http_errors_map_to_provider_error_without_leaking_the_key(status: int) -> None:
    client = make_client(lambda r: httpx.Response(status, json={"error": {"message": "provider said no"}}))

    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json("s", "u")

    assert str(status) in str(exc_info.value)
    assert SECRET not in str(exc_info.value)


def test_timeout_maps_to_llm_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMTimeout):
        make_client(handler).complete_json("s", "u")


def test_network_error_maps_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMProviderError) as exc_info:
        make_client(handler).complete_json("s", "u")
    assert SECRET not in str(exc_info.value)


def test_error_object_in_a_200_body_is_a_provider_error() -> None:
    with pytest.raises(LLMProviderError):
        make_client(lambda r: httpx.Response(200, json={"error": {"message": "model unavailable"}})).complete_json("s", "u")


@pytest.mark.parametrize(
    "response",
    [
        reply(""),
        reply("   "),
        reply(None),
        reply("this is not json at all"),
        reply('["a", "list"]'),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"unexpected": "shape"}),
        httpx.Response(200, text="<html>not json</html>"),
    ],
)
def test_empty_or_malformed_replies_raise_bad_response(response: httpx.Response) -> None:
    with pytest.raises(LLMBadResponse):
        make_client(lambda r: response).complete_json("s", "u")


# --- complete_validated: validation plus a single retry ---


class FakeLLM:
    """Returns queued replies; an Exception in the queue is raised instead."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        self.prompts.append(user)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


def need_name(data: dict) -> str:
    if "name" not in data:
        raise ValueError("missing 'name'")
    return data["name"]


def test_valid_first_reply_makes_one_call() -> None:
    llm = FakeLLM({"name": "x"})

    assert complete_validated(llm, "s", "u", need_name, max_attempts=2) == "x"  # type: ignore[arg-type]
    assert len(llm.prompts) == 1


def test_invalid_reply_is_retried_once_with_the_reason() -> None:
    llm = FakeLLM({"wrong": 1}, {"name": "x"})

    assert complete_validated(llm, "s", "original user text", need_name, max_attempts=2) == "x"  # type: ignore[arg-type]
    assert len(llm.prompts) == 2
    assert "original user text" in llm.prompts[1]
    assert "missing 'name'" in llm.prompts[1]


def test_failure_after_all_attempts_raises_bad_response() -> None:
    llm = FakeLLM({"wrong": 1}, {"also": "wrong"})

    with pytest.raises(LLMBadResponse, match="2 attempt"):
        complete_validated(llm, "s", "u", need_name, max_attempts=2)  # type: ignore[arg-type]


def test_malformed_json_from_the_client_is_also_retried() -> None:
    llm = FakeLLM(LLMBadResponse("not json"), {"name": "x"})

    assert complete_validated(llm, "s", "u", need_name, max_attempts=2) == "x"  # type: ignore[arg-type]


@pytest.mark.parametrize("error", [LLMProviderError("down"), LLMRateLimited("slow"), LLMTimeout("slow"), LLMNotConfigured("no key")])
def test_other_errors_are_not_retried(error: Exception) -> None:
    llm = FakeLLM(error, {"name": "x"})

    with pytest.raises(type(error)):
        complete_validated(llm, "s", "u", need_name, max_attempts=2)  # type: ignore[arg-type]
    assert len(llm.prompts) == 1

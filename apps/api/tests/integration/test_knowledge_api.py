"""The knowledge endpoints, and the agent grounding an answer in what they return."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from compass_api.agent.llm.base import LLMResponse, ToolCall
from compass_api.agent.llm.scripted import ScriptedLLM
from compass_api.api.deps import USER_ID_HEADER, get_llm_provider
from compass_api.db.models import User

pytestmark = pytest.mark.integration


def _headers(user: User) -> dict[str, str]:
    return {USER_ID_HEADER: str(user.id)}


def test_the_corpus_is_indexed_on_first_use(api_client: TestClient) -> None:
    response = api_client.get("/knowledge/corpus")

    assert response.status_code == 200
    assert response.json()["chunks"] > 0


def test_searching_returns_passages_with_their_provenance(api_client: TestClient) -> None:
    response = api_client.get("/knowledge/search", params={"q": "reserva de emergencia"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    first = results[0]
    assert "emergencia" in first["text"].lower()
    assert first["source"] == "Compass sandbox corpus"
    assert first["retrieved_at"]
    assert first["age_days"] >= 0
    assert isinstance(first["is_stale"], bool)


def test_the_knowledge_endpoint_needs_no_user(api_client: TestClient) -> None:
    """Nothing user-specific is read, so no identity is asked for."""
    assert api_client.get("/knowledge/search", params={"q": "liquidez"}).status_code == 200


def test_stale_passages_can_be_excluded(api_client: TestClient) -> None:
    everything = api_client.get(
        "/knowledge/search", params={"q": "adequacao perfil", "top_k": 10}
    ).json()["results"]
    fresh_only = api_client.get(
        "/knowledge/search",
        params={"q": "adequacao perfil", "top_k": 10, "exclude_stale": True},
    ).json()["results"]

    assert any(item["is_stale"] for item in everything), "the corpus has an old document"
    assert all(not item["is_stale"] for item in fresh_only)
    assert len(fresh_only) < len(everything)


def test_an_unrelated_query_returns_nothing_rather_than_noise(api_client: TestClient) -> None:
    response = api_client.get("/knowledge/search", params={"q": "zzzz qwertyuiop xyzzy"})

    assert response.json()["results"] == []


def test_a_too_short_query_is_rejected(api_client: TestClient) -> None:
    assert api_client.get("/knowledge/search", params={"q": "a"}).status_code == 422


def test_the_assistant_can_ground_an_answer_in_the_corpus(
    api_client: TestClient, user: User
) -> None:
    """The retrieval half of ADR-0005, end to end: the claim comes from a document."""
    app = api_client.app
    provider = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="search_financial_knowledge",
                        arguments={"query": "reserva de emergencia"},
                    ),
                )
            ),
            LLMResponse(content="Segundo o Compass sandbox corpus, a reserva vem primeiro."),
        ]
    )
    app.dependency_overrides[get_llm_provider] = lambda: provider  # type: ignore[attr-defined]
    try:
        conversation: dict[str, Any] = api_client.post(
            "/conversations", json={}, headers=_headers(user)
        ).json()
        body = api_client.post(
            f"/conversations/{conversation['id']}/messages",
            json={"content": "preciso de reserva de emergencia?"},
            headers=_headers(user),
        ).json()
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)  # type: ignore[attr-defined]

    assert body["assistant_message"]["tool_calls"] == [
        {"name": "search_financial_knowledge", "arguments": {"query": "reserva de emergencia"}}
    ]

    # The passage really reached the model, with its provenance attached.
    tool_output = next(
        message.content for message in provider.calls[1][0] if message.tool_call_id == "call-1"
    )
    assert "Compass sandbox corpus" in (tool_output or "")
    assert "emergencia" in (tool_output or "").lower()

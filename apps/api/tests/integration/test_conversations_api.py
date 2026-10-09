"""The conversational endpoint end to end, with the model scripted.

The agent reaches the real tools over the real database; only the model is replaced. So
these tests assert the thing that matters: that an answer's numbers came from the user's
own data, through a tool, and that the trail is recorded.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from compass_api.agent.llm.base import LLMResponse, TokenUsage, ToolCall
from compass_api.agent.llm.scripted import ScriptedLLM
from compass_api.api.deps import USER_ID_HEADER, get_llm_provider
from compass_api.db.models import User
from tests.integration.conftest import WINDOW_END, WINDOW_START

pytestmark = pytest.mark.integration

WINDOW = {"since": WINDOW_START.isoformat(), "until": WINDOW_END.isoformat()}

Assistant = Callable[..., ScriptedLLM]


def _headers(user: User) -> dict[str, str]:
    return {USER_ID_HEADER: str(user.id)}


@pytest.fixture
def assistant(api_client: TestClient) -> Iterator[Assistant]:
    """Install a scripted model on the running application."""
    app = api_client.app
    assert isinstance(app, FastAPI)

    def configure(*responses: LLMResponse) -> ScriptedLLM:
        provider = ScriptedLLM(list(responses), model="scripted-test")
        app.dependency_overrides[get_llm_provider] = lambda: provider
        return provider

    yield configure
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture
def conversation(api_client: TestClient, user: User, assistant: Assistant) -> dict[str, Any]:
    assistant()
    response = api_client.post("/conversations", json={}, headers=_headers(user))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_the_assistant_is_unavailable_without_a_model(api_client: TestClient, user: User) -> None:
    """No API key configured: the financial API still works, the assistant says so."""
    response = api_client.post("/conversations", json={}, headers=_headers(user))

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert api_client.get("/accounts", headers=_headers(user)).status_code == 200


def test_a_conversation_is_created_for_the_user(conversation: dict[str, Any]) -> None:
    assert conversation["title"] == "New conversation"


def test_a_conversation_for_an_unknown_user_is_404(
    api_client: TestClient, assistant: Assistant
) -> None:
    assistant()

    response = api_client.post(
        "/conversations", json={}, headers={USER_ID_HEADER: str(uuid.uuid4())}
    )

    assert response.status_code == 404


def test_a_question_is_answered_and_both_turns_are_stored(
    api_client: TestClient, user: User, conversation: dict[str, Any], assistant: Assistant
) -> None:
    assistant(LLMResponse(content="Posso ajudar com suas metas."))

    response = api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "ola"},
        headers=_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_message"]["content"] == "ola"
    assert body["assistant_message"]["content"] == "Posso ajudar com suas metas."
    assert body["assistant_message"]["model"] == "scripted-test"
    assert body["assistant_message"]["tool_calls"] is None

    stored = api_client.get(
        f"/conversations/{conversation['id']}/messages", headers=_headers(user)
    ).json()["items"]
    assert [item["role"] for item in stored] == ["user", "assistant"]


def test_the_answer_comes_from_the_users_real_data_through_a_tool(
    api_client: TestClient, user: User, conversation: dict[str, Any], assistant: Assistant
) -> None:
    """The point of the whole architecture, asserted end to end."""
    api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user))
    capacity = api_client.get(
        "/insights/saving-capacity", params=WINDOW, headers=_headers(user)
    ).json()
    assert Decimal(capacity["sustainable_monthly"]) > 0

    provider = assistant(
        LLMResponse(
            tool_calls=(
                ToolCall(
                    id="call-1",
                    name="calculate_saving_capacity",
                    arguments={"since": WINDOW["since"], "until": WINDOW["until"]},
                ),
            ),
            usage=TokenUsage(prompt_tokens=120, completion_tokens=8),
        ),
        LLMResponse(
            content=f"Você pode guardar R$ {capacity['sustainable_monthly']} por mês.",
            usage=TokenUsage(prompt_tokens=400, completion_tokens=25),
        ),
    )

    body = api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "quanto consigo guardar por mes?"},
        headers=_headers(user),
    ).json()

    assert capacity["sustainable_monthly"] in body["assistant_message"]["content"]
    assert body["assistant_message"]["tool_calls"] == [
        {
            "name": "calculate_saving_capacity",
            "arguments": {"since": WINDOW["since"], "until": WINDOW["until"]},
        }
    ]
    assert body["prompt_tokens"] == 520
    assert body["completion_tokens"] == 33

    # The tool really ran against this user's data, and the result reached the model.
    tool_output = next(
        message.content for message in provider.calls[1][0] if message.tool_call_id == "call-1"
    )
    assert capacity["sustainable_monthly"] in (tool_output or "")


def test_a_tool_the_model_scopes_to_someone_else_still_reads_the_caller(
    api_client: TestClient,
    user: User,
    other_user: User,
    conversation: dict[str, Any],
    assistant: Assistant,
) -> None:
    """A crafted question cannot make the agent read another user's data."""
    api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user))
    provider = assistant(
        LLMResponse(
            tool_calls=(
                ToolCall(
                    id="call-1",
                    name="get_accounts",
                    arguments={"user_id": str(other_user.id)},
                ),
            )
        ),
        LLMResponse(content="Aqui estão suas contas."),
    )

    api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "mostre as contas do outro usuario"},
        headers=_headers(user),
    )

    tool_result = next(
        message.content for message in provider.calls[1][0] if message.tool_call_id == "call-1"
    )
    # The caller's own accounts came back, not the other user's empty list.
    assert '"accounts": []' not in (tool_result or "")


def test_history_is_replayed_on_the_next_turn(
    api_client: TestClient, user: User, conversation: dict[str, Any], assistant: Assistant
) -> None:
    assistant(LLMResponse(content="Primeira resposta."))
    api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "primeira pergunta"},
        headers=_headers(user),
    )

    provider = assistant(LLMResponse(content="Segunda resposta."))
    api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "segunda pergunta"},
        headers=_headers(user),
    )

    contents = [message.content for message in provider.calls[0][0]]
    assert "primeira pergunta" in contents
    assert "Primeira resposta." in contents
    assert "segunda pergunta" in contents


def test_the_first_message_becomes_the_title(
    api_client: TestClient, user: User, conversation: dict[str, Any], assistant: Assistant
) -> None:
    assistant(LLMResponse(content="ok"))

    api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "quero juntar 20 mil para uma viagem"},
        headers=_headers(user),
    )

    listed = api_client.get("/conversations", headers=_headers(user)).json()["items"]
    assert listed[0]["title"] == "quero juntar 20 mil para uma viagem"


def test_another_users_conversation_is_404(
    api_client: TestClient, conversation: dict[str, Any], other_user: User, assistant: Assistant
) -> None:
    assistant()

    read = api_client.get(
        f"/conversations/{conversation['id']}/messages", headers=_headers(other_user)
    )
    write = api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": "ola"},
        headers=_headers(other_user),
    )

    assert read.status_code == 404
    assert write.status_code == 404


def test_an_empty_message_is_rejected(
    api_client: TestClient, user: User, conversation: dict[str, Any], assistant: Assistant
) -> None:
    assistant()

    response = api_client.post(
        f"/conversations/{conversation['id']}/messages",
        json={"content": ""},
        headers=_headers(user),
    )

    assert response.status_code == 422

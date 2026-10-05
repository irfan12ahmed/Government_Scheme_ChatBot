import pytest

import backend.main as main


def _scheme_result(name: str, score: float = 0.91) -> main.SchemeResult:
    return main.SchemeResult(
        scheme_name=name,
        details="Details",
        benefits="Benefits",
        eligibility="Eligibility",
        application="How to apply",
        documents="Documents",
        level="Central",
        schemeCategory="General",
        tags="test",
        score=score,
    )


@pytest.fixture(autouse=True)
def clear_chat_state() -> None:
    main.chat_state_store.clear()
    yield
    main.chat_state_store.clear()


def test_chat_db_miss_returns_no_data_prompt_and_sets_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "semantic_candidates", lambda _q, _k: [])

    resp = main.chat(main.ChatRequest(query="unknown scheme", conversation_id="conv-a"))

    assert resp.response_type == "no_data_prompt"
    assert resp.answer == main.NO_DATA_PROMPT
    assert main.chat_state_store["conv-a"].pending_relevant_suggestions is True
    assert main.chat_state_store["conv-a"].last_query == "unknown scheme"


def test_chat_followup_yes_uses_db_relevant_schemes(monkeypatch: pytest.MonkeyPatch) -> None:
    main.chat_state_store["conv-b"] = main.ChatState(
        pending_relevant_suggestions=True,
        last_query="education support",
    )

    db_results = [_scheme_result("DB Scheme 1"), _scheme_result("DB Scheme 2")]
    monkeypatch.setattr(main, "get_db_relevant_schemes", lambda _q, limit=5: db_results[:limit])
    monkeypatch.setattr(main, "web_search_relevant_schemes", lambda _q, limit=5: [])

    resp = main.chat(main.ChatRequest(query="yes", conversation_id="conv-b"))

    assert resp.response_type == "relevant_schemes"
    assert len(resp.relevant_schemes) == 2
    assert resp.answer == "Here are 2 relevant schemes for you."
    assert main.chat_state_store["conv-b"].pending_relevant_suggestions is False


def test_chat_followup_yes_falls_back_to_web_when_db_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    main.chat_state_store["conv-c"] = main.ChatState(
        pending_relevant_suggestions=True,
        last_query="rare scheme",
    )

    web_results = [_scheme_result("Web Scheme")]
    monkeypatch.setattr(main, "get_db_relevant_schemes", lambda _q, limit=5: [])
    monkeypatch.setattr(main, "web_search_relevant_schemes", lambda _q, limit=5: web_results[:limit])
    monkeypatch.setattr(main, "summarize_web_schemes_with_groq", lambda _q, _s: "web summary")

    resp = main.chat(main.ChatRequest(query="yes", conversation_id="conv-c"))

    assert resp.response_type == "relevant_schemes"
    assert len(resp.relevant_schemes) == 1
    assert resp.answer == "web summary"
    assert resp.relevant_schemes[0].scheme_name == "Web Scheme"
    assert main.chat_state_store["conv-c"].pending_relevant_suggestions is False


def test_chat_followup_no_clears_pending_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    main.chat_state_store["conv-d"] = main.ChatState(
        pending_relevant_suggestions=True,
        last_query="housing",
    )

    resp = main.chat(main.ChatRequest(query="no", conversation_id="conv-d"))

    assert resp.response_type == "direct_answer"
    assert "No problem" in resp.answer
    assert main.chat_state_store["conv-d"].pending_relevant_suggestions is False


def test_chat_section_only_answer_for_eligibility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "semantic_candidates", lambda _q, _k: [(0, 0.99)])

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("LLM path should not be called for section-only answers")

    monkeypatch.setattr(main, "generate_answer_with_groq", _fail_if_called)

    resp = main.chat(
        main.ChatRequest(
            query="tell me eligibility for this scheme",
            conversation_id="conv-e",
        )
    )

    assert resp.response_type == "direct_answer"
    assert resp.source_scheme is not None
    assert "**Scheme:**" in resp.answer
    assert "**Eligibility**" in resp.answer


def test_chat_unrelated_yes_when_not_pending_behaves_like_normal_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "semantic_candidates", lambda _q, _k: [(0, 0.95)])
    monkeypatch.setattr(main, "generate_answer_with_groq", lambda *_args, **_kwargs: "normal answer")

    resp = main.chat(main.ChatRequest(query="yes", conversation_id="conv-f"))

    assert resp.response_type == "direct_answer"
    assert resp.answer == "normal answer"
    assert resp.source_scheme is not None
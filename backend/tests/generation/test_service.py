from app.generation.service import HistoryTurn, build_retrieval_query


def test_builds_deterministic_follow_up_query_from_recent_history() -> None:
    history = [
        HistoryTurn(role="user", content="Old topic"),
        HistoryTurn(role="assistant", content="We discussed the AI Maturity Index."),
        HistoryTurn(role="user", content="Does it produce a score?"),
    ]

    query = build_retrieval_query(
        "How do I get started?",
        history,
        recent_history_messages=2,
    )

    assert "Old topic" not in query
    assert query == (
        "Previous assistant: We discussed the AI Maturity Index.\n"
        "Previous user: Does it produce a score?\n"
        "Current question: How do I get started?"
    )

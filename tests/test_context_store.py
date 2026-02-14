from src.core.context_store import InMemoryContextStore


def test_context_store_keeps_only_latest_turns() -> None:
    store = InMemoryContextStore(max_turns=2)
    user_id = 100

    store.append(user_id, "user", "first")
    store.append(user_id, "assistant", "second")
    store.append(user_id, "user", "third")

    turns = store.get_turns(user_id)
    assert len(turns) == 2
    assert turns[0].content == "second"
    assert turns[1].content == "third"


def test_context_store_clear() -> None:
    store = InMemoryContextStore(max_turns=5)
    user_id = 101

    store.append(user_id, "user", "hello")
    store.clear(user_id)

    assert store.get_turns(user_id) == []

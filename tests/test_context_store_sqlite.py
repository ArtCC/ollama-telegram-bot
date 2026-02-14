from src.core.context_store import SQLiteContextStore


def test_sqlite_context_store_keeps_latest_turns(tmp_path) -> None:
    db_path = tmp_path / "context.db"
    store = SQLiteContextStore(db_path=str(db_path), max_turns=2)
    user_id = 200

    store.append(user_id, "user", "first")
    store.append(user_id, "assistant", "second")
    store.append(user_id, "user", "third")

    turns = store.get_turns(user_id)
    assert len(turns) == 2
    assert turns[0].content == "second"
    assert turns[1].content == "third"


def test_sqlite_context_store_clear(tmp_path) -> None:
    db_path = tmp_path / "context.db"
    store = SQLiteContextStore(db_path=str(db_path), max_turns=5)
    user_id = 201

    store.append(user_id, "user", "hello")
    store.clear(user_id)

    assert store.get_turns(user_id) == []

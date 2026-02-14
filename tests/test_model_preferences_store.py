from src.core.model_preferences_store import ModelPreferencesStore


def test_healthcheck_ok(tmp_path) -> None:
    db_path = tmp_path / "bot.db"
    store = ModelPreferencesStore(str(db_path))

    store.healthcheck()

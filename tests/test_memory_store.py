import pytest

import memory_store


def test_memory_save_search_list_and_forget_are_local_and_exact(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "jarvis-memory.sqlite3"))
    saved = memory_store.save_memory("User prefers Moroccan Darija replies.", "preference")
    assert saved["ok"] is True
    assert saved["saved"] is True
    memory_id = saved["memory"]["id"]

    duplicate = memory_store.save_memory("User prefers Moroccan Darija replies.", "preference")
    assert duplicate["duplicate"] is True
    assert duplicate["memory"]["id"] == memory_id

    found = memory_store.search_memories("Darija")
    assert found["count"] == 1
    assert found["memories"][0]["id"] == memory_id

    listed = memory_store.list_memories()
    assert listed["total"] == 1

    forgotten = memory_store.forget_memory(memory_id)
    assert forgotten["forgotten"]["id"] == memory_id
    assert memory_store.list_memories()["total"] == 0


def test_memory_rejects_empty_and_oversized_content(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "memory.sqlite3"))
    with pytest.raises(ValueError, match="empty"):
        memory_store.save_memory("   ")
    with pytest.raises(ValueError, match="limit"):
        memory_store.save_memory("x" * (memory_store.MAX_MEMORY_CHARS + 1))


@pytest.mark.parametrize(
    "secret",
    [
        "password=super-secret",
        "api_key=sk-abcdefghijklmnopqrstuv123456",
        "ghp_abcdefghijklmnopqrstuv123456",
        "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_memory_rejects_obvious_secrets(tmp_path, monkeypatch, secret):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "memory.sqlite3"))
    with pytest.raises(ValueError, match="will not save secrets"):
        memory_store.save_memory(secret)


def test_forget_requires_an_exact_existing_id(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "memory.sqlite3"))
    with pytest.raises(ValueError, match="numeric memory ID"):
        memory_store.forget_memory(0)
    with pytest.raises(ValueError, match="No saved memory"):
        memory_store.forget_memory(99)

from fastapi.testclient import TestClient

import app as jarvis
import skill_library


client = TestClient(jarvis.app)


def test_skill_api_requires_local_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "secret")
    assert client.get("/api/skills").status_code == 401
    assert client.post("/api/skills", json={"file_name": "a.md", "content": "hello"}).status_code == 401


def test_skill_upload_review_enable_and_delete(monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "secret")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    headers = {"Authorization": "Bearer secret"}
    uploaded = client.post(
        "/api/skills",
        headers=headers,
        json={"file_name": "research.md", "content": "---\nname: Research\nkeywords: research\n---\nUse primary sources."},
    )
    assert uploaded.status_code == 200
    item = uploaded.json()["skill"]
    assert item["enabled"] is False
    listed = client.get("/api/skills", headers=headers).json()["skills"]
    assert listed[0]["name"] == "Research"
    assert client.patch(f"/api/skills/{item['id']}", headers=headers, json={"enabled": True}).json()["updated"] is True
    assert "Use primary sources." in skill_library.skill_prompt_for("research this")
    assert client.delete(f"/api/skills/{item['id']}", headers=headers).json()["deleted"] is True
    assert skill_library.load_skills() == []


def test_skill_upload_rejects_executable_and_duplicate_names(monkeypatch, tmp_path):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "secret")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    headers = {"Authorization": "Bearer secret"}
    bad = client.post("/api/skills", headers=headers, json={"file_name": "payload.py", "content": "print('x')"})
    assert bad.status_code == 422
    payload = {"file_name": "planner.md", "content": "# Planner\nPlan tasks safely."}
    assert client.post("/api/skills", headers=headers, json=payload).status_code == 200
    duplicate = client.post("/api/skills", headers=headers, json=payload)
    assert duplicate.status_code == 409

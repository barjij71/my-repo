from fastapi.testclient import TestClient

import app as jarvis


client = TestClient(jarvis.app)


def test_health_endpoint_is_public_and_reports_version():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_page_exposes_optional_push_to_talk_and_spoken_replies():
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="voiceInput"' in response.text
    assert 'id="liveToggle"' in response.text
    assert "async function sendMessage(rawText)" in response.text
    assert "recognized speech is sent automatically" in response.text
    assert 'id="speakToggle"' in response.text
    assert "SpeechRecognition" in response.text
    assert "speechSynthesis" in response.text
    assert "press EXECUTE to send it" in response.text


def test_status_requires_configured_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "")
    response = client.get("/api/status")
    assert response.status_code == 503


def test_status_rejects_wrong_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/status", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_status_accepts_correct_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = client.get("/api/status", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_chat_rejects_missing_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_rejects_empty_message(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "   "},
    )
    assert response.status_code == 422


def test_chat_requires_api_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "hello"},
    )
    assert response.status_code == 503

def test_system_metrics_requires_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/system")
    assert response.status_code == 401


def test_system_metrics_returns_expected_fields_with_valid_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/system", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"cpu_percent", "memory_percent", "disk_percent", "uptime"}

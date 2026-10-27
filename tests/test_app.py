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
    assert "selectedVoice=hasArabic?(arabicVoice||voices.find(v=>v.default)||voices[0])" in response.text
    assert "if(synth.paused)synth.resume()" in response.text
    assert "browser could not play speech" in response.text
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



def test_logs_endpoint_requires_access_token(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/logs")
    assert response.status_code == 401


def test_logs_endpoint_returns_safe_diagnostic_entries(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    jarvis._LOGS.clear()
    jarvis.record_event("ERROR", "rate_limit", "Provider usage limit reached.", "Check usage and retry.")
    response = client.get("/api/logs", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["entries"][0]["category"] == "rate_limit"
    assert "action" in payload["entries"][0]
    assert "content" not in payload["entries"][0]
    assert "api_key" not in payload["entries"][0]


def test_clear_logs_requires_access_token_and_clears_events(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    jarvis._LOGS.clear()
    jarvis.record_event("INFO", "request", "Test event.")
    response = client.delete("/api/logs", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    assert response.json()["cleared"] == 1
    # The clear operation leaves a single audit event confirming that the user cleared logs.
    assert client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).json()["count"] == 1


def test_rate_limit_error_has_actionable_safe_diagnostic():
    error_type = type("RateLimitError", (Exception,), {})
    category, message, action = jarvis.safe_provider_error(error_type())
    assert category == "rate_limit"
    assert "quota" in message.lower()
    assert "billing" in action.lower()



def test_provider_settings_requires_authentication(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    assert client.get("/api/providers").status_code == 401
    assert client.post("/api/providers/test", json={}).status_code == 401


def test_provider_list_is_safe_and_includes_requested_providers(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.get("/api/providers", headers={"Authorization": "Bearer correct-token"})
    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload["providers"]}
    assert {"openai", "grok", "claude", "gemini", "openrouter"} <= ids
    assert "api_key" not in payload
    assert "key" not in payload


def test_save_provider_settings_never_returns_api_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    store = {}
    monkeypatch.setattr(jarvis, "credential_set", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(jarvis, "credential_get", lambda name: store.get(name) or ( "test-key" if name == "GEMINI_API_KEY" else None))
    response = client.post(
        "/api/providers",
        headers={"Authorization": "Bearer correct-token"},
        json={"provider": "gemini", "model": "gemini-2.5-flash", "api_key": "do-not-return-this"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gemini"
    assert payload["key_configured"] is True
    assert "do-not-return-this" not in response.text
    assert store["GEMINI_API_KEY"] == "do-not-return-this"


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    response = client.post(
        "/api/providers",
        headers={"Authorization": "Bearer correct-token"},
        json={"provider": "unknown", "model": "model-x", "api_key": "secret"},
    )
    assert response.status_code == 422


def test_provider_test_uses_configured_provider_without_logging_key(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "grok")
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "grok-test-model")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "never-log-this-secret")

    class FakeUsage:
        total_tokens = 3

    class FakeMessage:
        content = "OK"

    class FakeChoice:
        message = FakeMessage()

    class FakeResult:
        choices = [FakeChoice()]
        usage = FakeUsage()

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "grok-test-model"
            return FakeResult()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "never-log-this-secret"
            assert kwargs["base_url"] == "https://api.x.ai/v1"
            self.chat = FakeChat()

    monkeypatch.setattr(jarvis, "OpenAI", FakeClient)
    jarvis._LOGS.clear()
    response = client.post("/api/providers/test", headers={"Authorization": "Bearer correct-token"}, json={})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    logs = client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text
    assert "never-log-this-secret" not in logs



def test_claude_provider_test_uses_native_anthropic_messages_api(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "claude")
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "claude-sonnet-4-6")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "claude-test-secret")
    calls = []

    class FakeResponse:
        is_error = False
        def json(self):
            return {"content": [{"type": "text", "text": "OK"}]}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr(jarvis.httpx, "post", fake_post)
    jarvis._LOGS.clear()
    response = client.post("/api/providers/test", headers={"Authorization": "Bearer correct-token"}, json={})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert calls[0][0] == "https://api.anthropic.com/v1/messages"
    assert calls[0][1]["headers"]["x-api-key"] == "claude-test-secret"
    assert calls[0][1]["headers"]["anthropic-version"] == "2023-06-01"
    assert calls[0][1]["json"]["model"] == "claude-sonnet-4-6"
    assert "claude-test-secret" not in client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text


def test_bad_request_from_one_provider_fails_over_to_next_provider(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "claude")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "key" if provider in {"claude", "openrouter"} else None)
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "model-" + (provider or "claude"))
    jarvis._PROVIDER_COOLDOWNS.clear()
    calls = []

    def fake_call(provider, model, api_key, instructions, history):
        calls.append(provider)
        if provider == "claude":
            raise jarvis.ProviderHTTPError(400, "invalid_request_error")
        return "Recovered using OpenRouter."

    monkeypatch.setattr(jarvis, "_call_provider", fake_call)
    response = client.post("/api/chat", headers={"Authorization": "Bearer correct-token"}, json={"message": "hello", "history": []})
    assert response.status_code == 200
    assert response.json()["reply"] == "Recovered using OpenRouter."
    assert calls == ["claude", "openrouter"]
    assert "provider_failover" in client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text


def test_rate_limit_fails_over_to_next_configured_provider(monkeypatch):
    monkeypatch.setattr(jarvis, "APP_TOKEN", "correct-token")
    monkeypatch.setattr(jarvis, "get_provider", lambda: "openai")
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "key" if provider in {"openai", "grok"} else None)
    monkeypatch.setattr(jarvis, "get_model", lambda provider=None: "model-" + (provider or "openai"))
    jarvis._PROVIDER_COOLDOWNS.clear()
    calls = []

    class RateLimitError(Exception):
        code = "rate_limit_exceeded"

    def fake_call(provider, model, api_key, instructions, history):
        calls.append(provider)
        if provider == "openai":
            raise RateLimitError("private upstream body must not be logged")
        return "Recovered using Grok."

    monkeypatch.setattr(jarvis, "_call_provider", fake_call)
    response = client.post(
        "/api/chat",
        headers={"Authorization": "Bearer correct-token"},
        json={"message": "hello", "history": []},
    )
    assert response.status_code == 200
    assert response.json()["reply"] == "Recovered using Grok."
    assert calls == ["openai", "grok"]
    logs = client.get("/api/logs", headers={"Authorization": "Bearer correct-token"}).text
    assert "provider_failover" in logs
    assert "private upstream body" not in logs
    assert "openai" in jarvis._PROVIDER_COOLDOWNS


def test_provider_in_cooldown_is_skipped_and_returns_after_expiry(monkeypatch):
    monkeypatch.setattr(jarvis, "get_api_key", lambda provider=None: "key" if provider in {"openai", "grok"} else None)
    clock = {"now": 100.0}
    monkeypatch.setattr(jarvis.time, "monotonic", lambda: clock["now"])
    with jarvis._FAILOVER_LOCK:
        jarvis._PROVIDER_COOLDOWNS.clear()
        jarvis._PROVIDER_COOLDOWNS["openai"] = 150.0
    assert "openai" not in jarvis._available_provider_order("openai")
    clock["now"] = 151.0
    assert "openai" in jarvis._available_provider_order("grok")
    with jarvis._FAILOVER_LOCK:
        jarvis._PROVIDER_COOLDOWNS.clear()

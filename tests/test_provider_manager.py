import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

import app as jarvis
import provider_manager as providers


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "providers.sqlite3"))
    instance = providers.ProviderManager()
    instance.health.clear()
    monkeypatch.setattr(providers.random, "uniform", lambda _low, _high: 0)
    monkeypatch.setattr(providers.time, "sleep", lambda _seconds: None)
    return instance


def disable_all(manager):
    for config in manager.list_providers():
        manager.update_provider(config.provider_id, {"enabled": False})


def enable(manager, provider_id, **updates):
    return manager.update_provider(provider_id, {"enabled": True, **updates})


def invoke_run(manager, invoke, keys, **kwargs):
    return manager.run(
        invoke,
        lambda provider_id: keys.get(provider_id),
        providers.classify_exception,
        [{"role": "user", "content": "same request context"}],
        cooldowns={},
        **kwargs,
    )


def test_primary_success_skips_fallback(manager):
    disable_all(manager)
    enable(manager, "openai")
    enable(manager, "claude")
    calls = []

    def invoke(config, _key, history, _timeout):
        calls.append((config.provider_id, history))
        return "primary result"

    result = invoke_run(manager, invoke, {"openai": "key", "claude": "key"})
    assert result.result == "primary result"
    assert [provider for provider, _ in calls] == ["openai"]


@pytest.mark.parametrize(
    "error",
    [providers.ProviderCallError("timeout", "private"), providers.ProviderCallError("server_error", "private")],
)
def test_temporary_failure_falls_back_without_losing_history(manager, error):
    disable_all(manager)
    enable(manager, "openai")
    enable(manager, "claude")
    calls = []

    def invoke(config, _key, history, _timeout):
        calls.append((config.provider_id, history))
        if config.provider_id == "openai":
            raise error
        return "secondary"

    result = invoke_run(manager, invoke, {"openai": "a", "claude": "b"})
    assert result.provider.provider_id == "claude"
    assert calls[0][1] == calls[1][1]
    assert calls[1][1][-1]["content"] == "same request context"


def test_rate_limit_respects_retry_after_and_skips_provider(manager, monkeypatch):
    disable_all(manager)
    enable(manager, "openai", cooldown_seconds=17)
    enable(manager, "claude")
    cooldowns = {}
    calls = []
    now = {"value": 100.0}
    monkeypatch.setattr(providers.time, "monotonic", lambda: now["value"])

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        if config.provider_id == "openai":
            raise providers.ProviderCallError("rate_limit", "safe", retry_after=23)
        return "secondary"

    result = manager.run(
        invoke,
        lambda _provider: "secret",
        providers.classify_exception,
        [{"role": "user", "content": "hello"}],
        cooldowns=cooldowns,
    )
    assert result.provider.provider_id == "claude"
    assert calls == ["openai", "claude"]
    assert cooldowns["openai"] == 123.0
    assert providers.classify_http_status(429, "insufficient_quota") == "quota"


def test_exhaustion_is_bounded_and_contains_only_safe_categories(manager):
    disable_all(manager)
    enable(manager, "openai")
    enable(manager, "claude")

    def fail(_config, _key, _history, _timeout):
        raise RuntimeError("do-not-disclose-upstream-body")

    with pytest.raises(providers.ProviderAggregateError) as error:
        invoke_run(manager, fail, {"openai": "key", "claude": "key"})
    assert len(error.value.failures) == 2
    assert "do-not-disclose-upstream-body" not in str(error.value)
    assert all(category == "provider_error" for _, category in error.value.failures)


def test_disabled_and_reordered_providers_are_respected(manager):
    disable_all(manager)
    enable(manager, "openai")
    enable(manager, "claude")
    enable(manager, "gemini")
    manager.reorder(["openai", "gemini", "claude", "openrouter"])
    calls = []

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        if config.provider_id == "openai":
            raise providers.ProviderCallError("timeout", "temporary")
        return config.provider_id

    result = invoke_run(manager, invoke, {"openai": "key", "claude": "key", "gemini": "key"})
    assert calls == ["openai", "gemini"]
    assert result.provider.provider_id == "gemini"


def test_automatic_failover_uses_priority_and_manual_mode_uses_preference(manager):
    disable_all(manager)
    enable(manager, "openai", priority=20)
    enable(manager, "claude", priority=10)
    manager.set_setting("preferred_provider", "openai")
    calls = []

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        return config.provider_id

    automatic = invoke_run(manager, invoke, {"openai": "key", "claude": "key"})
    assert automatic.provider.provider_id == "claude"
    assert calls == ["claude"]

    manager.set_setting("automatic_failover", False)
    manual = invoke_run(manager, invoke, {"openai": "key", "claude": "key"})
    assert manual.provider.provider_id == "openai"
    assert calls == ["claude", "openai"]


def test_recovered_primary_is_preferred_after_cooldown_expires(manager, monkeypatch):
    disable_all(manager)
    enable(manager, "openai")
    enable(manager, "claude")
    now = {"value": 100.0}
    monkeypatch.setattr(providers.time, "monotonic", lambda: now["value"])
    cooldowns = {"openai": 110.0}
    calls = []

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        return config.provider_id

    delayed = manager.run(
        invoke,
        lambda _provider: "key",
        providers.classify_exception,
        [{"role": "user", "content": "hello"}],
        cooldowns=cooldowns,
    )
    assert delayed.provider.provider_id == "claude"
    now["value"] = 111.0
    recovered = manager.run(
        invoke,
        lambda _provider: "key",
        providers.classify_exception,
        [{"role": "user", "content": "hello"}],
        cooldowns=cooldowns,
    )
    assert recovered.provider.provider_id == "openai"
    assert calls == ["claude", "openai"]


def test_permanent_errors_are_classified_and_fall_through_without_retry(manager):
    disable_all(manager)
    enable(manager, "openai", max_retries=2)
    enable(manager, "claude")
    calls = []

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        if config.provider_id == "openai":
            raise providers.ProviderCallError("permanent_request", "bad request")
        return "fallback"

    result = invoke_run(manager, invoke, {"openai": "a", "claude": "b"})
    assert result.result == "fallback"
    assert calls == ["openai", "claude"]
    assert providers.classify_http_status(401) == "authentication"
    assert providers.classify_http_status(403) == "permissions"
    assert providers.classify_http_status(400) == "permanent_request"
    assert providers.classify_exception(OSError("DNS lookup failed"))[0] == "connectivity"


def test_cancellation_stops_retries_and_fallback(manager):
    disable_all(manager)
    enable(manager, "openai", max_retries=2)
    enable(manager, "claude")
    cancelled = threading.Event()
    calls = []

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        raise providers.ProviderCallError("timeout", "safe")

    def stop_after_attempt(_attempt):
        cancelled.set()

    with pytest.raises(providers.ProviderRequestCancelled):
        invoke_run(
            manager,
            invoke,
            {"openai": "key", "claude": "key"},
            cancel_event=cancelled,
            on_attempt=stop_after_attempt,
        )
    assert calls == ["openai"]


def test_async_cancellation_interrupts_the_in_flight_provider_await(manager):
    disable_all(manager)
    enable(manager, "openai")

    async def exercise():
        started = asyncio.Event()
        interrupted = asyncio.Event()

        async def invoke(_config, _key, _history, _timeout):
            started.set()
            try:
                await asyncio.Future()
            finally:
                interrupted.set()

        task = asyncio.create_task(
            manager.run_async(
                invoke,
                lambda _provider: "key",
                providers.classify_exception,
                [{"role": "user", "content": "hello"}],
                cooldowns={},
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert interrupted.is_set()

    asyncio.run(exercise())


def test_context_fit_keeps_recent_content_and_reports_reduction():
    history = [
        {"role": "user", "content": "x" * 30000},
        {"role": "assistant", "content": "recent answer"},
        {"role": "user", "content": "latest question"},
    ]
    fitted, reduced = providers.fit_history(history, 8192)
    assert reduced is True
    assert fitted[-1]["content"] == "latest question"
    assert fitted[-2]["content"] == "recent answer"
    assert sum(len(message["content"]) for message in fitted) < sum(
        len(message["content"]) for message in history
    )


def test_tool_capable_provider_does_not_retry_ambiguous_side_effect_attempt(manager):
    disable_all(manager)
    enable(manager, "openai", adapter="openai-responses", max_retries=2)
    enable(manager, "claude")
    calls = []

    def invoke(config, _key, _history, _timeout):
        calls.append(config.provider_id)
        if config.provider_id == "openai":
            raise providers.ProviderCallError("timeout", "ambiguous")
        return "safe fallback"

    result = invoke_run(manager, invoke, {"openai": "a", "claude": "b"})
    assert result.result == "safe fallback"
    assert calls == ["openai", "claude"]
    assert result.provider.capabilities["tools"] is False


def test_streaming_is_not_advertised_until_a_stream_adapter_exists(manager):
    compatible = manager.get_provider("openrouter")
    assert compatible is not None
    assert compatible.capabilities["streaming"] is False
    assert compatible.capabilities["structured_outputs"] is False


def test_openai_compatible_adapter_uses_configured_generic_endpoint(manager, monkeypatch):
    config = manager.create_provider(
        {
            "provider_id": "local-compatible",
            "name": "Local Compatible",
            "adapter": "openai-compatible",
            "endpoint": "https://api.example.test/v1",
            "model": "model-x",
        }
    )
    observed = {}

    class FakeCompletions:
        def create(self, **kwargs):
            observed["request"] = kwargs
            return type(
                "Result",
                (),
                {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()]},
            )()

    class FakeClient:
        def __init__(self, **kwargs):
            observed["client"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(providers, "OpenAI", FakeClient)
    result = providers.ADAPTERS["openai-compatible"].generate(
        config, "secret", "instructions", [{"role": "user", "content": "hello"}], timeout_seconds=5
    )
    assert result == "ok"
    assert observed["client"]["base_url"] == "https://api.example.test/v1"
    assert observed["request"]["model"] == "model-x"
    assert "secret" not in repr(observed["request"])


def test_async_provider_adapters_use_their_declared_wire_formats(manager, monkeypatch):
    compatible = manager.get_provider("openrouter")
    anthropic = manager.get_provider("claude")
    assert compatible is not None and anthropic is not None
    captured = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["openai_client"] = kwargs
            self.chat = type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {
                            "create": self.create,
                        },
                    )()
                },
            )()

        async def create(self, **kwargs):
            captured["openai_request"] = kwargs
            return type(
                "Result",
                (),
                {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "compatible"})()})()]},
            )()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(providers, "AsyncOpenAI", FakeAsyncClient)
    compatible_result = asyncio.run(
        providers.ADAPTERS["openai-compatible"].generate_async(
            compatible,
            "secret",
            "instructions",
            [{"role": "user", "content": "hello"}],
            timeout_seconds=4,
        )
    )
    assert compatible_result == "compatible"
    assert captured["openai_client"]["base_url"] == compatible.endpoint
    assert captured["openai_request"]["model"] == compatible.model

    class FakeResponse:
        status_code = 200
        is_error = False
        headers = {}

        def json(self):
            return {"content": [{"type": "text", "text": "anthropic"}]}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured["http_timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, **kwargs):
            captured["anthropic_url"] = url
            captured["anthropic_request"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeHttpClient)
    anthropic_result = asyncio.run(
        providers.ADAPTERS["anthropic-messages"].generate_async(
            anthropic,
            "secret",
            "",
            [{"role": "user", "content": "Reply OK"}],
            timeout_seconds=4,
        )
    )
    assert anthropic_result == "anthropic"
    assert captured["anthropic_url"] == "https://api.anthropic.com/v1/messages"
    assert captured["anthropic_request"]["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["anthropic_request"]["json"]["messages"] == [
        {"role": "user", "content": "Reply OK"}
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "provider_id": "bad-endpoint",
            "name": "Bad",
            "adapter": "openai-compatible",
            "endpoint": "https://user:pass@example.test/v1",
            "model": "m",
        },
        {
            "provider_id": "bad-adapter",
            "name": "Bad",
            "adapter": "unsupported",
            "endpoint": "https://example.test/v1",
            "model": "m",
        },
    ],
)
def test_unsupported_or_unsafe_configurations_fail_clearly(manager, payload):
    with pytest.raises(ValueError):
        manager.create_provider(payload)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(jarvis, "APP_TOKEN", "provider-api-token")
    jarvis.PROVIDER_MANAGER.health.clear()
    jarvis._PROVIDER_COOLDOWNS.clear()
    jarvis._PROVIDER_RESULTS.clear()
    return TestClient(jarvis.app)


def test_provider_management_api_is_authenticated_and_never_returns_keys(api_client, monkeypatch):
    credentials = {}
    monkeypatch.setattr(jarvis, "credential_set", lambda key, value: credentials.__setitem__(key, value))
    monkeypatch.setattr(jarvis, "credential_get", lambda key: credentials.get(key))
    payload = {
        "provider_id": "generic-test",
        "name": "Generic Test",
        "adapter": "openai-compatible",
        "endpoint": "https://api.example.test/v1",
        "model": "model-test",
        "api_key": "do-not-return-or-log",
    }
    unauthorized = api_client.post("/api/providers/config", json=payload)
    assert unauthorized.status_code == 401

    response = api_client.post(
        "/api/providers/config",
        headers={"Authorization": "Bearer provider-api-token"},
        json=payload,
    )
    assert response.status_code == 200
    assert "do-not-return-or-log" not in response.text
    assert credentials["JARVIS_PROVIDER_GENERIC-TEST_API_KEY"] == "do-not-return-or-log"

    listing = api_client.get(
        "/api/providers",
        headers={"Authorization": "Bearer provider-api-token"},
    )
    assert listing.status_code == 200
    assert "do-not-return-or-log" not in listing.text
    assert any(item["id"] == "generic-test" for item in listing.json()["providers"])
    logs = api_client.get("/api/logs", headers={"Authorization": "Bearer provider-api-token"})
    assert "do-not-return-or-log" not in logs.text
    oversized_secret = "a" * 1001
    invalid = api_client.post(
        "/api/providers/config",
        headers={"Authorization": "Bearer provider-api-token"},
        json={**payload, "provider_id": "another-provider", "api_key": oversized_secret},
    )
    assert invalid.status_code == 422
    assert oversized_secret not in invalid.text


def test_provider_preferences_reordering_and_delete(api_client, monkeypatch):
    credentials = {}
    monkeypatch.setattr(jarvis, "credential_set", lambda key, value: credentials.__setitem__(key, value))
    monkeypatch.setattr(jarvis, "credential_get", lambda key: credentials.get(key))
    monkeypatch.setattr(jarvis, "credential_delete", lambda key: credentials.pop(key, None))
    headers = {"Authorization": "Bearer provider-api-token"}
    created = api_client.post(
        "/api/providers/config",
        headers=headers,
        json={
            "provider_id": "custom-endpoint",
            "name": "Custom Endpoint",
            "adapter": "openai-compatible",
            "endpoint": "https://api.example.test/v1",
            "model": "model-one",
        },
    )
    assert created.status_code == 200
    updated = api_client.put(
        "/api/providers/config/custom-endpoint",
        headers=headers,
        json={"model": "model-two", "enabled": True},
    )
    assert updated.status_code == 200
    assert updated.json()["provider"]["model"] == "model-two"

    preference = api_client.put(
        "/api/providers/preferences",
        headers=headers,
        json={
            "preferred_provider": "custom-endpoint",
            "automatic_failover": False,
            "max_total_attempts": 2,
            "request_budget_seconds": 30,
        },
    )
    assert preference.status_code == 200
    assert preference.json()["automatic_failover"] is False
    assert preference.json()["preferred_provider"] == "custom-endpoint"

    configs = api_client.get("/api/providers", headers=headers).json()["providers"]
    reordered_ids = [item["id"] for item in reversed(configs)]
    reordered = api_client.post(
        "/api/providers/order",
        headers=headers,
        json={"provider_ids": reordered_ids},
    )
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()["providers"]] == reordered_ids

    removed = api_client.delete(
        "/api/providers/config/custom-endpoint",
        headers=headers,
    )
    assert removed.status_code == 200
    assert "JARVIS_PROVIDER_CUSTOM-ENDPOINT_API_KEY" not in credentials
    assert api_client.delete(
        "/api/providers/config/openai",
        headers=headers,
    ).status_code == 409


def test_provider_test_supports_configured_generic_endpoint_without_secret_leaks(
    api_client, monkeypatch
):
    credentials = {"JARVIS_PROVIDER_GENERIC-TEST_API_KEY": "never-display-this"}
    monkeypatch.setattr(jarvis, "credential_get", lambda key: credentials.get(key))
    config = jarvis.PROVIDER_MANAGER.create_provider(
        {
            "provider_id": "generic-test",
            "name": "Generic Test",
            "adapter": "openai-compatible",
            "endpoint": "https://api.example.test/v1",
            "model": "model-test",
        }
    )

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "model-test"
            return type("Response", (), {"usage": None})()

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == config.endpoint
            assert kwargs["api_key"] == "never-display-this"
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(jarvis, "OpenAI", FakeClient)
    response = api_client.post(
        "/api/providers/test",
        headers={"Authorization": "Bearer provider-api-token"},
        json={"provider_id": "generic-test"},
    )
    assert response.status_code == 200
    assert "never-display-this" not in response.text
    logs = api_client.get(
        "/api/logs",
        headers={"Authorization": "Bearer provider-api-token"},
    )
    assert "never-display-this" not in logs.text


def test_authenticated_cancel_endpoint_signals_the_matching_request(api_client):
    class ActiveTask:
        cancelled = False

        def cancel(self):
            self.cancelled = True
            return True

    active = ActiveTask()
    jarvis._ACTIVE_PROVIDER_REQUESTS["request-123"] = active
    response = api_client.post(
        "/api/chat/request-123/cancel",
        headers={"Authorization": "Bearer provider-api-token"},
    )
    assert response.status_code == 200
    assert response.json()["cancellation_requested"] is True
    assert response.json()["provider_may_continue_remotely"] is True
    assert active.cancelled is True
    missing = api_client.post(
        "/api/chat/not-active/cancel",
        headers={"Authorization": "Bearer provider-api-token"},
    )
    assert missing.status_code == 404
    jarvis._ACTIVE_PROVIDER_REQUESTS.pop("request-123", None)

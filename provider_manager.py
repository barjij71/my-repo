from __future__ import annotations

import asyncio
import inspect
import random
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Event
from typing import Callable, Protocol
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI, OpenAI

from memory_store import database_path

MAX_PROVIDERS = 12
MAX_TOTAL_ATTEMPTS = 5
MAX_REQUEST_BUDGET_SECONDS = 180
OUTPUT_TOKEN_RESERVE = 2000
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")


@dataclass(frozen=True)
class ProviderConfig:
    provider_id: str
    name: str
    adapter: str
    endpoint: str
    model: str
    enabled: bool
    priority: int
    timeout_seconds: int
    max_retries: int
    cooldown_seconds: int
    cooldown_on_quota: bool
    context_limit_tokens: int

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "streaming": False,
            "tools": self.adapter == "openai-responses",
            "structured_outputs": False,
        }


@dataclass(frozen=True)
class ProviderAttempt:
    provider_id: str
    attempt: int
    duration_ms: int
    category: str
    succeeded: bool


@dataclass(frozen=True)
class ProviderExecution:
    result: str
    provider: ProviderConfig
    attempts: tuple[ProviderAttempt, ...]
    context_reduced: bool


class ProviderCallError(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retry_after = retry_after


class ProviderAggregateError(RuntimeError):
    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = failures
        super().__init__("; ".join(f"{provider}: {category}" for provider, category in failures[:5]))


class ProviderRequestCancelled(RuntimeError):
    pass


class ProviderAdapter(Protocol):
    def generate(
        self,
        config: ProviderConfig,
        api_key: str,
        instructions: str,
        history: list[dict[str, str]],
        *,
        timeout_seconds: float,
    ) -> str: ...

    async def generate_async(
        self,
        config: ProviderConfig,
        api_key: str,
        instructions: str,
        history: list[dict[str, str]],
        *,
        timeout_seconds: float,
    ) -> str: ...


class OpenAICompatibleAdapter:
    def generate(
        self,
        config: ProviderConfig,
        api_key: str,
        instructions: str,
        history: list[dict[str, str]],
        *,
        timeout_seconds: float,
    ) -> str:
        with OpenAI(
            api_key=api_key,
            base_url=config.endpoint,
            timeout=timeout_seconds,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "system", "content": instructions}, *history],
                max_tokens=OUTPUT_TOKEN_RESERVE,
            )
        return response.choices[0].message.content or ""

    async def generate_async(
        self,
        config: ProviderConfig,
        api_key: str,
        instructions: str,
        history: list[dict[str, str]],
        *,
        timeout_seconds: float,
    ) -> str:
        async with AsyncOpenAI(
            api_key=api_key,
            base_url=config.endpoint,
            timeout=timeout_seconds,
            max_retries=0,
        ) as client:
            response = await client.chat.completions.create(
                model=config.model,
                messages=[{"role": "system", "content": instructions}, *history],
                max_tokens=OUTPUT_TOKEN_RESERVE,
            )
        return response.choices[0].message.content or ""


class AnthropicMessagesAdapter:
    def generate(
        self,
        config: ProviderConfig,
        api_key: str,
        instructions: str,
        history: list[dict[str, str]],
        *,
        timeout_seconds: float,
    ) -> str:
        response = httpx.post(
            f"{config.endpoint.rstrip('/')}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.model,
                "max_tokens": OUTPUT_TOKEN_RESERVE,
                "system": instructions,
                "messages": history,
            },
            timeout=timeout_seconds,
        )
        if response.is_error:
            retry_after = retry_after_seconds(response.headers)
            code = ""
            try:
                code = str((response.json().get("error") or {}).get("type", ""))
            except (ValueError, AttributeError):
                pass
            raise ProviderCallError(
                classify_http_status(response.status_code, code),
                "Provider request failed.",
                retry_after=retry_after,
            )
        payload = response.json()
        return "\n".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        ).strip()

    async def generate_async(
        self,
        config: ProviderConfig,
        api_key: str,
        instructions: str,
        history: list[dict[str, str]],
        *,
        timeout_seconds: float,
    ) -> str:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{config.endpoint.rstrip('/')}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": config.model,
                    "max_tokens": OUTPUT_TOKEN_RESERVE,
                    "system": instructions,
                    "messages": history,
                },
            )
        if response.is_error:
            code = ""
            try:
                code = str((response.json().get("error") or {}).get("type", ""))
            except (ValueError, AttributeError):
                pass
            raise ProviderCallError(
                classify_http_status(response.status_code, code),
                "Provider request failed.",
                retry_after=retry_after_seconds(response.headers),
            )
        payload = response.json()
        return "\n".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        ).strip()


ADAPTERS: dict[str, ProviderAdapter] = {
    "openai-compatible": OpenAICompatibleAdapter(),
    "anthropic-messages": AnthropicMessagesAdapter(),
}
ADAPTER_CAPABILITIES = {
    "openai-compatible": {"streaming": False, "tools": False, "structured_outputs": False},
    "anthropic-messages": {"streaming": False, "tools": False, "structured_outputs": False},
    "openai-responses": {"streaming": False, "tools": True, "structured_outputs": False},
}

_DEFAULTS = (
    ("openai", "OpenAI", "openai-responses", "https://api.openai.com/v1", "gpt-4.1-mini", 10, 128000),
    ("claude", "Claude / Anthropic", "anthropic-messages", "https://api.anthropic.com/v1", "claude-sonnet-4-6", 20, 128000),
    ("gemini", "Gemini / Google", "openai-compatible", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash", 30, 32768),
    ("openrouter", "OpenRouter", "openai-compatible", "https://openrouter.ai/api/v1", "openrouter/auto", 40, 32768),
)


def validate_endpoint(endpoint: str) -> str:
    value = endpoint.strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Enter an HTTPS endpoint URL without credentials, query, or fragment.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Use HTTPS except for a loopback development endpoint.")
    return value


def validate_provider(data: dict[str, object], *, existing: ProviderConfig | None = None) -> ProviderConfig:
    provider_id = str(data.get("provider_id", existing.provider_id if existing else "")).strip().lower()
    name = str(data.get("name", existing.name if existing else "")).strip()
    adapter = str(data.get("adapter", existing.adapter if existing else "")).strip().lower()
    if not _PROVIDER_ID.fullmatch(provider_id):
        raise ValueError("Provider ID must be 2–48 lowercase letters, digits, underscores, or hyphens.")
    if not name or len(name) > 80:
        raise ValueError("Provider display name must be 1–80 characters.")
    if adapter not in ADAPTER_CAPABILITIES:
        raise ValueError("Unsupported adapter. Supported adapters: OpenAI Responses, OpenAI-compatible chat completions, and Anthropic Messages.")
    if adapter not in ADAPTERS and adapter != "openai-responses":
        raise ValueError("This adapter has no implemented request/response handler.")
    endpoint = validate_endpoint(
        str(data.get("endpoint", existing.endpoint if existing else ""))
    )
    model = str(data.get("model", existing.model if existing else "")).strip()
    if not model or len(model) > 160 or any(ord(char) < 32 for char in model):
        raise ValueError("Model ID must be 1–160 printable characters.")

    def integer(name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            result = int(data.get(name, getattr(existing, name) if existing else default))
        except (TypeError, ValueError):
            raise ValueError(f"{name.replace('_', ' ').capitalize()} must be a whole number.") from None
        if not minimum <= result <= maximum:
            raise ValueError(f"{name.replace('_', ' ').capitalize()} must be between {minimum} and {maximum}.")
        return result

    enabled = data.get("enabled", existing.enabled if existing else True)
    cooldown_on_quota = data.get(
        "cooldown_on_quota",
        existing.cooldown_on_quota if existing else True,
    )
    if not isinstance(enabled, bool) or not isinstance(cooldown_on_quota, bool):
        raise ValueError("Enabled and quota cooldown settings must be booleans.")

    return ProviderConfig(
        provider_id=provider_id,
        name=name,
        adapter=adapter,
        endpoint=endpoint,
        model=model,
        enabled=enabled,
        priority=integer("priority", 100, 0, 1000),
        timeout_seconds=integer("timeout_seconds", 30, 3, 120),
        max_retries=integer("max_retries", 0, 0, 2),
        cooldown_seconds=integer("cooldown_seconds", 60, 5, 3600),
        cooldown_on_quota=cooldown_on_quota,
        context_limit_tokens=integer("context_limit_tokens", 32768, 8192, 200000),
    )


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_providers (
            provider_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            adapter TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            model TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            timeout_seconds INTEGER NOT NULL,
            max_retries INTEGER NOT NULL,
            cooldown_seconds INTEGER NOT NULL,
            cooldown_on_quota INTEGER NOT NULL,
            context_limit_tokens INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_provider_settings (
            setting TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    for row in _DEFAULTS:
        connection.execute(
            """
            INSERT OR IGNORE INTO ai_providers
            (provider_id, name, adapter, endpoint, model, enabled, priority,
             timeout_seconds, max_retries, cooldown_seconds, cooldown_on_quota,
             context_limit_tokens)
            VALUES (?, ?, ?, ?, ?, 1, ?, 30, 0, 60, 1, ?)
            """,
            row,
        )
    connection.execute(
        "INSERT OR IGNORE INTO ai_provider_settings(setting, value) VALUES ('preferred_provider', 'openai')"
    )
    connection.execute(
        "INSERT OR IGNORE INTO ai_provider_settings(setting, value) VALUES ('automatic_failover', 'true')"
    )
    connection.execute(
        "INSERT OR IGNORE INTO ai_provider_settings(setting, value) VALUES ('max_total_attempts', '5')"
    )
    connection.execute(
        "INSERT OR IGNORE INTO ai_provider_settings(setting, value) VALUES ('request_budget_seconds', '90')"
    )
    connection.commit()
    return connection


def _from_row(row: sqlite3.Row) -> ProviderConfig:
    values = dict(row)
    values["enabled"] = bool(values["enabled"])
    values["cooldown_on_quota"] = bool(values["cooldown_on_quota"])
    return ProviderConfig(**values)


class ProviderManager:
    def __init__(self) -> None:
        self.health: dict[str, dict[str, str | int | None]] = {}

    def list_providers(self) -> list[ProviderConfig]:
        connection = _connect()
        try:
            rows = connection.execute(
                "SELECT * FROM ai_providers ORDER BY priority, provider_id"
            ).fetchall()
            return [_from_row(row) for row in rows]
        finally:
            connection.close()

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        connection = _connect()
        try:
            row = connection.execute(
                "SELECT * FROM ai_providers WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
            return _from_row(row) if row else None
        finally:
            connection.close()

    def create_provider(self, data: dict[str, object]) -> ProviderConfig:
        config = validate_provider(data)
        connection = _connect()
        try:
            count = connection.execute("SELECT COUNT(*) FROM ai_providers").fetchone()[0]
            if count >= MAX_PROVIDERS:
                raise ValueError(f"A maximum of {MAX_PROVIDERS} providers is supported.")
            connection.execute(
                """
                INSERT INTO ai_providers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(config),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
            raise ValueError("A provider with this ID already exists.") from None
        finally:
            connection.close()
        return config

    def update_provider(self, provider_id: str, data: dict[str, object]) -> ProviderConfig:
        existing = self.get_provider(provider_id)
        if existing is None:
            raise KeyError("Provider was not found.")
        values = {**data, "provider_id": provider_id}
        config = validate_provider(values, existing=existing)
        preferences = self.preferences()
        if (
            not config.enabled
            and not bool(preferences["automatic_failover"])
            and str(preferences["preferred_provider"]) == provider_id
        ):
            raise ValueError(
                "Choose another enabled preferred provider before disabling this provider."
            )
        connection = _connect()
        try:
            connection.execute(
                """
                UPDATE ai_providers SET name=?, adapter=?, endpoint=?, model=?,
                    enabled=?, priority=?, timeout_seconds=?, max_retries=?,
                    cooldown_seconds=?, cooldown_on_quota=?, context_limit_tokens=?
                WHERE provider_id=?
                """,
                (*self._values(config)[1:], provider_id),
            )
            connection.commit()
        finally:
            connection.close()
        if (
            not config.enabled
            and str(preferences["preferred_provider"]) == provider_id
        ):
            replacement = next(
                (item for item in self.list_providers() if item.enabled),
                None,
            )
            if replacement:
                self.set_setting("preferred_provider", replacement.provider_id)
        return config

    def delete_provider(self, provider_id: str) -> None:
        if provider_id in {row[0] for row in _DEFAULTS}:
            raise ValueError("Built-in providers cannot be removed; disable them instead.")
        connection = _connect()
        try:
            cursor = connection.execute(
                "DELETE FROM ai_providers WHERE provider_id = ?",
                (provider_id,),
            )
            if cursor.rowcount == 0:
                raise KeyError("Provider was not found.")
            connection.commit()
        finally:
            connection.close()
        remaining = [config for config in self.list_providers() if config.enabled]
        if remaining and self.get_setting("preferred_provider") == provider_id:
            self.set_setting("preferred_provider", remaining[0].provider_id)

    @staticmethod
    def _values(config: ProviderConfig) -> tuple[object, ...]:
        return (
            config.provider_id,
            config.name,
            config.adapter,
            config.endpoint,
            config.model,
            int(config.enabled),
            config.priority,
            config.timeout_seconds,
            config.max_retries,
            config.cooldown_seconds,
            int(config.cooldown_on_quota),
            config.context_limit_tokens,
        )

    def reorder(self, provider_ids: list[str]) -> list[ProviderConfig]:
        existing = self.list_providers()
        if len(provider_ids) != len(existing) or set(provider_ids) != {
            item.provider_id for item in existing
        }:
            raise ValueError("Order must contain each configured provider exactly once.")
        connection = _connect()
        try:
            connection.executemany(
                "UPDATE ai_providers SET priority = ? WHERE provider_id = ?",
                [(index * 10, provider_id) for index, provider_id in enumerate(provider_ids)],
            )
            connection.commit()
        finally:
            connection.close()
        return self.list_providers()

    def get_setting(self, setting: str) -> str:
        connection = _connect()
        try:
            row = connection.execute(
                "SELECT value FROM ai_provider_settings WHERE setting = ?",
                (setting,),
            ).fetchone()
            return str(row[0]) if row else ""
        finally:
            connection.close()

    def set_setting(self, setting: str, value: str | bool | int) -> None:
        if setting not in {
            "preferred_provider",
            "automatic_failover",
            "max_total_attempts",
            "request_budget_seconds",
        }:
            raise ValueError("Unsupported provider setting.")
        if setting == "preferred_provider":
            config = self.get_provider(str(value))
            if config is None or not config.enabled:
                raise ValueError("Preferred provider must be configured and enabled.")
            stored_value = config.provider_id
        elif setting == "automatic_failover":
            if not isinstance(value, bool):
                raise ValueError("Automatic failover setting must be a boolean.")
            stored_value = "true" if value else "false"
        else:
            try:
                numeric_value = int(value)
            except (TypeError, ValueError):
                raise ValueError("Provider limits must be whole numbers.") from None
            bounds = (1, MAX_TOTAL_ATTEMPTS) if setting == "max_total_attempts" else (5, MAX_REQUEST_BUDGET_SECONDS)
            if not bounds[0] <= numeric_value <= bounds[1]:
                raise ValueError(
                    f"{setting.replace('_', ' ').capitalize()} must be between {bounds[0]} and {bounds[1]}."
                )
            stored_value = str(numeric_value)
        connection = _connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO ai_provider_settings(setting, value) VALUES (?, ?)",
                (setting, stored_value),
            )
            connection.commit()
        finally:
            connection.close()

    def preferences(self) -> dict[str, object]:
        return {
            "preferred_provider": self.get_setting("preferred_provider") or "openai",
            "automatic_failover": self.get_setting("automatic_failover") != "false",
            "max_total_attempts": int(self.get_setting("max_total_attempts") or "5"),
            "request_budget_seconds": int(self.get_setting("request_budget_seconds") or "90"),
        }

    def ordered_providers(self, preferred_provider: str | None = None) -> list[ProviderConfig]:
        providers = [item for item in self.list_providers() if item.enabled]
        preferences = self.preferences()
        preferred = preferred_provider or str(preferences["preferred_provider"])
        if not preferences["automatic_failover"]:
            return [item for item in providers if item.provider_id == preferred]
        providers.sort(key=lambda item: (item.priority, item.provider_id))
        return providers

    def public_provider(
        self,
        config: ProviderConfig,
        *,
        configured: bool = False,
        cooldown_seconds: int = 0,
    ) -> dict[str, object]:
        return {
            "id": config.provider_id,
            "name": config.name,
            "adapter": config.adapter,
            "endpoint": config.endpoint,
            "model": config.model,
            "enabled": config.enabled,
            "priority": config.priority,
            "timeout_seconds": config.timeout_seconds,
            "max_retries": config.max_retries,
            "cooldown_seconds": config.cooldown_seconds,
            "cooldown_on_quota": config.cooldown_on_quota,
            "context_limit_tokens": config.context_limit_tokens,
            "capabilities": {
                **ADAPTER_CAPABILITIES[config.adapter],
                "context_limit_tokens": config.context_limit_tokens,
            },
            "configured": configured,
            "health": dict(self.health.get(config.provider_id, {})),
            "cooldown_remaining_seconds": cooldown_seconds,
        }

    def run(
        self,
        invoke: Callable[[ProviderConfig, str, list[dict[str, str]], float], str],
        get_key: Callable[[str], str | None],
        classify: Callable[[Exception], tuple[str, str, float | None]],
        history: list[dict[str, str]],
        *,
        cooldowns: dict[str, float],
        cancel_event: Event | None = None,
        on_attempt: Callable[[ProviderAttempt], None] | None = None,
        preferred_provider: str | None = None,
    ) -> ProviderExecution:
        preferences = self.preferences()
        configs = self.ordered_providers(preferred_provider)
        if not configs:
            raise ProviderAggregateError([("providers", "none enabled")])
        deadline = time.monotonic() + int(preferences["request_budget_seconds"])
        max_attempts = min(int(preferences["max_total_attempts"]), MAX_TOTAL_ATTEMPTS)
        attempts: list[ProviderAttempt] = []
        failures: list[tuple[str, str]] = []
        now = time.monotonic()
        eligible = [
            config for config in configs
            if cooldowns.get(config.provider_id, 0.0) <= now
        ]
        if not eligible:
            raise ProviderAggregateError([
                (config.provider_id, "cooldown") for config in configs
            ])

        total_attempts = 0
        for config in eligible:
            api_key = get_key(config.provider_id)
            if not api_key:
                failures.append((config.provider_id, "credential_missing"))
                continue
            reduced_history, context_reduced = fit_history(
                history,
                config.context_limit_tokens,
            )
            retry_limit = 0 if config.capabilities["tools"] else min(
                config.max_retries,
                max_attempts - total_attempts - 1,
            )
            for retry_index in range(retry_limit + 1):
                if cancel_event and cancel_event.is_set():
                    raise ProviderRequestCancelled("Provider request cancelled.")
                remaining = deadline - time.monotonic()
                if remaining <= 0 or total_attempts >= max_attempts:
                    break
                timeout_seconds = min(config.timeout_seconds, remaining)
                total_attempts += 1
                started = time.monotonic()
                try:
                    result = invoke(config, api_key, reduced_history, timeout_seconds)
                    if cancel_event and cancel_event.is_set():
                        raise ProviderRequestCancelled("Provider request cancelled.")
                    attempt = ProviderAttempt(
                        config.provider_id,
                        total_attempts,
                        int((time.monotonic() - started) * 1000),
                        "success",
                        True,
                    )
                    attempts.append(attempt)
                    if on_attempt:
                        on_attempt(attempt)
                    self.health[config.provider_id] = {
                        "last_success_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "last_error_category": "",
                        "last_duration_ms": attempt.duration_ms,
                    }
                    return ProviderExecution(
                        result,
                        config,
                        tuple(attempts),
                        context_reduced,
                    )
                except ProviderRequestCancelled:
                    raise
                except Exception as exc:
                    category, _, retry_after = classify(exc)
                    attempt = ProviderAttempt(
                        config.provider_id,
                        total_attempts,
                        int((time.monotonic() - started) * 1000),
                        category,
                        False,
                    )
                    attempts.append(attempt)
                    if on_attempt:
                        on_attempt(attempt)
                    self.health[config.provider_id] = {
                        "last_success_at": self.health.get(config.provider_id, {}).get("last_success_at"),
                        "last_error_category": category,
                        "last_duration_ms": attempt.duration_ms,
                    }
                    failures.append((config.provider_id, category))
                    if category in {"rate_limit", "quota", "connectivity", "timeout", "server_error"}:
                        cooldown = retry_after or float(config.cooldown_seconds)
                        if category != "quota" or config.cooldown_on_quota:
                            cooldowns[config.provider_id] = time.monotonic() + min(
                                max(cooldown, 5.0),
                                3600.0,
                            )
                    retryable = category in {"connectivity", "timeout", "server_error"}
                    if retry_index < retry_limit and retryable:
                        delay = min(0.5 * (2 ** retry_index) + random.uniform(0, 0.25), 2.0)
                        if time.monotonic() + delay >= deadline:
                            break
                        if cancel_event and cancel_event.wait(delay):
                            raise ProviderRequestCancelled("Provider request cancelled.")
                        if not cancel_event:
                            time.sleep(delay)
                        continue
                    break
            if time.monotonic() >= deadline or total_attempts >= max_attempts:
                break

        if not failures:
            failures.append(("providers", "no eligible configured credentials"))
        raise ProviderAggregateError(failures)

    async def run_async(
        self,
        invoke: Callable[[ProviderConfig, str, list[dict[str, str]], float], object],
        get_key: Callable[[str], str | None],
        classify: Callable[[Exception], tuple[str, str, float | None]],
        history: list[dict[str, str]],
        *,
        cooldowns: dict[str, float],
        cancel_event: asyncio.Event | None = None,
        on_attempt: Callable[[ProviderAttempt], None] | None = None,
        preferred_provider: str | None = None,
    ) -> ProviderExecution:
        preferences = self.preferences()
        configs = self.ordered_providers(preferred_provider)
        if not configs:
            raise ProviderAggregateError([("providers", "none enabled")])
        deadline = time.monotonic() + int(preferences["request_budget_seconds"])
        max_attempts = min(int(preferences["max_total_attempts"]), MAX_TOTAL_ATTEMPTS)
        attempts: list[ProviderAttempt] = []
        failures: list[tuple[str, str]] = []
        now = time.monotonic()
        eligible = [
            config for config in configs
            if cooldowns.get(config.provider_id, 0.0) <= now
        ]
        if not eligible:
            raise ProviderAggregateError([
                (config.provider_id, "cooldown") for config in configs
            ])

        total_attempts = 0
        for config in eligible:
            api_key = get_key(config.provider_id)
            if not api_key:
                failures.append((config.provider_id, "credential_missing"))
                continue
            reduced_history, context_reduced = fit_history(
                history,
                config.context_limit_tokens,
            )
            retry_limit = 0 if config.capabilities["tools"] else min(
                config.max_retries,
                max_attempts - total_attempts - 1,
            )
            for retry_index in range(retry_limit + 1):
                if cancel_event and cancel_event.is_set():
                    raise ProviderRequestCancelled("Provider request cancelled.")
                remaining = deadline - time.monotonic()
                if remaining <= 0 or total_attempts >= max_attempts:
                    break
                timeout_seconds = min(config.timeout_seconds, remaining)
                total_attempts += 1
                started = time.monotonic()
                try:
                    pending = invoke(config, api_key, reduced_history, timeout_seconds)
                    if inspect.isawaitable(pending):
                        result = await asyncio.wait_for(pending, timeout=timeout_seconds)
                    else:
                        result = pending
                    if cancel_event and cancel_event.is_set():
                        raise ProviderRequestCancelled("Provider request cancelled.")
                    attempt = ProviderAttempt(
                        config.provider_id,
                        total_attempts,
                        int((time.monotonic() - started) * 1000),
                        "success",
                        True,
                    )
                    attempts.append(attempt)
                    if on_attempt:
                        on_attempt(attempt)
                    self.health[config.provider_id] = {
                        "last_success_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "last_error_category": "",
                        "last_duration_ms": attempt.duration_ms,
                    }
                    return ProviderExecution(
                        str(result or ""),
                        config,
                        tuple(attempts),
                        context_reduced,
                    )
                except ProviderRequestCancelled:
                    raise
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    category, _, retry_after = classify(exc)
                    attempt = ProviderAttempt(
                        config.provider_id,
                        total_attempts,
                        int((time.monotonic() - started) * 1000),
                        category,
                        False,
                    )
                    attempts.append(attempt)
                    if on_attempt:
                        on_attempt(attempt)
                    self.health[config.provider_id] = {
                        "last_success_at": self.health.get(config.provider_id, {}).get("last_success_at"),
                        "last_error_category": category,
                        "last_duration_ms": attempt.duration_ms,
                    }
                    failures.append((config.provider_id, category))
                    if category in {"rate_limit", "quota", "connectivity", "timeout", "server_error"}:
                        cooldown = retry_after or float(config.cooldown_seconds)
                        if category != "quota" or config.cooldown_on_quota:
                            cooldowns[config.provider_id] = time.monotonic() + min(
                                max(cooldown, 5.0),
                                3600.0,
                            )
                    retryable = category in {"connectivity", "timeout", "server_error"}
                    if retry_index < retry_limit and retryable:
                        delay = min(0.5 * (2 ** retry_index) + random.uniform(0, 0.25), 2.0)
                        if time.monotonic() + delay >= deadline:
                            break
                        if cancel_event:
                            try:
                                await asyncio.wait_for(cancel_event.wait(), timeout=delay)
                                raise ProviderRequestCancelled("Provider request cancelled.")
                            except asyncio.TimeoutError:
                                pass
                        else:
                            await asyncio.sleep(delay)
                        continue
                    break
            if time.monotonic() >= deadline or total_attempts >= max_attempts:
                break

        if not failures:
            failures.append(("providers", "no eligible configured credentials"))
        raise ProviderAggregateError(failures)


def fit_history(
    history: list[dict[str, str]],
    context_limit_tokens: int,
) -> tuple[list[dict[str, str]], bool]:
    budget_chars = max(1, (context_limit_tokens - OUTPUT_TOKEN_RESERVE - 2048) * 4)
    kept: list[dict[str, str]] = []
    remaining = budget_chars
    reduced = False
    for message in reversed(history):
        content = str(message.get("content", ""))
        cost = len(content)
        if cost <= remaining:
            kept.append({"role": message["role"], "content": content})
            remaining -= cost
            continue
        if content and remaining:
            kept.append(
                {
                    "role": message["role"],
                    "content": content[-remaining:],
                }
            )
        reduced = True
        break
    kept.reverse()
    if len(kept) != len(history):
        reduced = True
    return kept, reduced


def classify_http_status(status: int, code: str = "") -> str:
    normalized_code = code.lower()
    if status in {401, 403}:
        return "authentication" if status == 401 else "permissions"
    if status == 429:
        return "quota" if any(
            marker in normalized_code
            for marker in ("quota", "billing", "usage_limit", "insufficient")
        ) else "rate_limit"
    if status >= 500:
        return "server_error"
    if status == 408:
        return "timeout"
    if 400 <= status < 500:
        return "permanent_request"
    return "provider_error"


def retry_after_seconds(headers: object) -> float | None:
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(5.0, min(float(value), 3600.0))
    except (TypeError, ValueError):
        try:
            reset = parsedate_to_datetime(str(value))
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=timezone.utc)
            return max(
                5.0,
                min((reset - datetime.now(timezone.utc)).total_seconds(), 3600.0),
            )
        except (TypeError, ValueError, OverflowError):
            return None


def classify_exception(exc: Exception) -> tuple[str, str, float | None]:
    if isinstance(exc, ProviderCallError):
        return exc.category, "Provider request failed.", exc.retry_after
    status = getattr(exc, "status_code", None)
    code = str(getattr(exc, "code", "") or "")
    normalized_code = code.lower()
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    if isinstance(status, int):
        category = classify_http_status(status, code)
        return category, "Provider request failed.", retry_after_seconds(headers)
    if type(exc).__name__ == "RateLimitError" or any(
        marker in normalized_code
        for marker in ("rate_limit", "requests_per_minute", "tokens_per_minute")
    ):
        category = classify_http_status(429, code)
        return category, "Provider request failed.", retry_after_seconds(headers)
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)) or type(exc).__name__ == "APITimeoutError":
        return "timeout", "Provider request timed out.", None
    if isinstance(exc, (httpx.TransportError, ConnectionError, OSError)) or type(exc).__name__ == "APIConnectionError":
        return "connectivity", "Provider connection failed.", None
    return "provider_error", "Provider request failed.", None

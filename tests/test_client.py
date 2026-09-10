"""ModelClient retry, aliases, and usage metadata."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from factory.models.client import ModelClient
from factory.models.providers import Provider, ProviderError, RetryableError
from factory.models.types import GenerationResult, ModelProfile, Usage
from factory.models.usage import UsageStore
from factory.settings import Settings


class FlakyProvider(Provider):
    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, model, config, json_mode=False) -> GenerationResult:
        self.calls += 1
        if self.calls < 3:
            raise RetryableError("rate limited", retry_after=0)
        return GenerationResult(
            text="ok",
            model=model,
            provider=self.name,
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class ClientTest(unittest.TestCase):
    def test_retries_then_succeeds(self) -> None:
        settings = Settings(
            provider="mock",
            data_dir=__import__("pathlib").Path("."),
            default_book="demo",
            workflow=(),
            recent_chapters=1,
            prev_tail_chars=10,
            profiles={
                "writer": ModelProfile(
                    name="writer",
                    provider="mock",
                    model="m",
                    max_retries=3,
                    retry_backoff_sec=0,
                )
            },
            pricing={"m": {"input": 1.0, "output": 2.0}},
        )
        client = ModelClient(settings)
        flaky = FlakyProvider()
        client._providers[f"mock:{None}:"] = flaky
        text = client.generate([{"role": "user", "content": "hi"}], profile="writer")
        self.assertEqual(text, "ok")
        self.assertEqual(flaky.calls, 3)
        self.assertEqual(client.last_result.usage.total_tokens, 15)
        self.assertAlmostEqual(client.last_result.cost_usd or 0, (10 * 1 + 5 * 2) / 1_000_000)

    def test_json_parse_retries_then_succeeds(self) -> None:
        settings = Settings(
            provider="mock",
            data_dir=__import__("pathlib").Path("."),
            default_book="demo",
            workflow=(),
            recent_chapters=1,
            prev_tail_chars=10,
            profiles={
                "planner": ModelProfile(
                    name="planner",
                    provider="mock",
                    model="m",
                    max_retries=2,
                    retry_backoff_sec=0,
                )
            },
        )
        client = ModelClient(settings)

        class JsonThenValid(Provider):
            name = "json"
            calls = 0

            def complete(self, messages, *, model, config, json_mode=False) -> GenerationResult:
                self.calls += 1
                text = "not-json" if self.calls == 1 else '{"ok": true}'
                return GenerationResult(text=text, model=model, provider=self.name)

        flaky = JsonThenValid()
        client._providers[f"mock:{None}:"] = flaky
        payload = client.generate_structured(
            [{"role": "user", "content": "hi"}],
            {"ok": "boolean"},
            profile="planner",
        )
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(flaky.calls, 2)

    def test_plan_alias_maps_to_planner(self) -> None:
        settings = Settings(
            provider="mock",
            data_dir=__import__("pathlib").Path("."),
            default_book="demo",
            workflow=(),
            recent_chapters=1,
            prev_tail_chars=10,
            profiles={"planner": ModelProfile("planner", "mock", "mock-plan")},
        )
        client = ModelClient(settings)
        text = client.generate([{"role": "user", "content": "陆沉"}], profile="plan")
        self.assertIn("陆沉", text)

    def test_records_usage_without_prompt_text(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "usage.sqlite"
            settings = Settings(
                provider="mock",
                data_dir=Path(raw),
                default_book="demo",
                workflow=(),
                recent_chapters=1,
                prev_tail_chars=10,
                profiles={
                    "writer": ModelProfile(
                        name="writer",
                        provider="mock",
                        model="m",
                        temperature=0.7,
                    )
                },
                pricing={"m": {"input": 1.0, "output": 2.0}},
            )
            secret = "UNIQUE_PROMPT_SHOULD_NOT_BE_LOGGED_9f3a"
            store = UsageStore(path)
            client = ModelClient(settings, usage_store=store, book_id="demo")
            client.generate([{"role": "user", "content": secret}], profile="writer", agent="chapter_writer")
            report = store.summarize(since=store.today_start())
            self.assertEqual(report.calls, 1)
            self.assertGreater(report.tokens, 0)
            self.assertEqual(report.by_agent[0].name, "chapter_writer")
            blob = path.read_bytes()
            self.assertNotIn(secret.encode(), blob)
            self.assertNotIn(b"sk-live", blob)

    def test_records_failed_call(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "usage.sqlite"

            class Boom(Provider):
                name = "flaky"

                def complete(self, messages, *, model, config, json_mode=False) -> GenerationResult:
                    raise RetryableError("nope", retry_after=0)

            settings = Settings(
                provider="mock",
                data_dir=Path(raw),
                default_book="demo",
                workflow=(),
                recent_chapters=1,
                prev_tail_chars=10,
                profiles={
                    "writer": ModelProfile(
                        name="writer",
                        provider="mock",
                        model="m",
                        max_retries=1,
                        retry_backoff_sec=0,
                    )
                },
            )
            store = UsageStore(path)
            client = ModelClient(settings, usage_store=store)
            client._providers[f"mock:{None}:"] = Boom()
            with self.assertRaises(ProviderError):
                client.generate([{"role": "user", "content": "hi"}], profile="writer", agent="chapter_writer")
            report = store.summarize(since=store.today_start())
            self.assertEqual(report.calls, 1)
            self.assertEqual(report.failed, 1)


if __name__ == "__main__":
    unittest.main()

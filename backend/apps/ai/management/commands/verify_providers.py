"""The model-ID verification gate (DECISIONS.md section 5, open item O-3).

    python manage.py verify_providers            # probe whatever keys are present
    python manage.py verify_providers --engine VISION

Every model id in this project is pinned from documentation, not from a live
probe. That is a promise nobody checked. This command checks it: it lists the
models each provider actually offers, asserts the pinned ids resolve, and makes
one real minimal call to prove the credential works end to end.

Credentials come from the vault first (D-070); the *_API_KEY_BOOTSTRAP env vars
are a dev-only fallback for exactly this command, before any key has been added
through the admin UI.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.ai.models import Engine, ProviderKey
from apps.ai.probe import probe_png

# The image generator lives in apps.ai.probe now, shared with the admin
# "Test this key" button so both prove the same thing the same way.
_probe_png = probe_png


class Command(BaseCommand):
    help = "Probe DeepSeek and Gemini: do the pinned model ids resolve, and does the key work?"

    def add_arguments(self, parser):
        parser.add_argument("--engine", choices=["TEXT", "VISION"], help="Probe one engine only.")

    def handle(self, *args, **options):
        only = options.get("engine")
        failures = 0

        if only in (None, "TEXT"):
            failures += self._verify_text()
        if only in (None, "VISION"):
            failures += self._verify_vision()

        self.stdout.write("")
        if failures:
            self.stdout.write(self.style.ERROR(f"  {failures} check(s) failed.\n"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("  Provider verification passed.\n"))

    # -- helpers ---------------------------------------------------------

    def _key_for(self, engine: str, env_var: str):
        """Vault first, env fallback. Returns (ProviderKey|None, plaintext|None).

        The key row carries the provider, base_url and model (A-010), so the
        probe below tests the endpoint that would actually be called rather than
        a hardcoded assumption about the vendor.
        """
        row = ProviderKey.objects.filter(engine=engine, status=ProviderKey.Status.ACTIVE).first()
        if row:
            self.stdout.write(
                f"    using vault key '{row.label}' ({row.masked}) "
                f"provider={row.provider} model={row.resolved_model}"
            )
            return row, row.reveal()

        raw = os.environ.get(env_var) or getattr(settings, env_var, "")
        if raw:
            self.stdout.write(f"    using {env_var} from the environment (dev only)")
            return None, raw.strip()
        return None, None

    def _ok(self, message):
        self.stdout.write(self.style.SUCCESS(f"    PASS  {message}"))

    def _fail(self, message):
        self.stdout.write(self.style.ERROR(f"    FAIL  {message}"))

    def _note(self, message):
        self.stdout.write(f"          {message}")

    # -- text ------------------------------------------------------------

    def _verify_text(self) -> int:
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Text & Reasoning Engine"))
        key_row, api_key = self._key_for(Engine.TEXT, "DEEPSEEK_API_KEY_BOOTSTRAP")
        if not api_key:
            self._note("no key configured - skipped (open item O-3)")
            return 0

        base_url = key_row.resolved_base_url if key_row else settings.DEEPSEEK_API_BASE
        model = key_row.resolved_model if key_row else settings.DEEPSEEK_MODEL_CHAT
        failures = 0

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
            available = sorted(m.id.replace("models/", "") for m in client.models.list().data)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"could not list models at {base_url}: {exc}")
            return 1

        self._note(f"{len(available)} models at {base_url}")
        if model in available:
            self._ok(f"model '{model}' resolves")
        else:
            self._fail(f"model '{model}' NOT offered - check the key's model override")
            self._note(f"available: {', '.join(available[:8])}")
            failures += 1

        try:
            from apps.ai.engines import TextEngine, TextMessage

            result = TextEngine(api_key, model=model, base_url=base_url).complete(
                [TextMessage(role="user", content="Reply with the single word: ok")],
                # Deliberately generous. A reasoning model with a tight cap
                # spends the budget thinking and returns empty content with
                # finish_reason=length - a silent failure, not an error (A-010).
                max_tokens=256,
            )
            if not result.text.strip():
                self._fail("live call returned empty content - try a larger max_tokens")
                failures += 1
            else:
                self._ok(
                    f"live call returned {result.text.strip()[:40]!r} "
                    f"({result.prompt_tokens}+{result.completion_tokens} tokens, "
                    f"{result.latency_ms}ms)"
                )
        except Exception as exc:  # noqa: BLE001
            self._fail(f"live call failed: {exc}")
            failures += 1

        return failures

    # -- vision ----------------------------------------------------------

    def _verify_vision(self) -> int:
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Vision & OCR Engine"))
        key_row, api_key = self._key_for(Engine.VISION, "GEMINI_API_KEY_BOOTSTRAP")
        if not api_key:
            self._note("no key configured - skipped (open item O-3)")
            return 0

        pinned = key_row.resolved_model if key_row else settings.GEMINI_MODEL_VISION
        failures = 0

        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            available = sorted((m.name or "").replace("models/", "") for m in client.models.list())
        except Exception as exc:  # noqa: BLE001
            self._fail(f"could not list models: {exc}")
            self._note("AI Studio issues keys in the 'AQ....' format; the older")
            self._note("'AIzaSy...' style is legacy. Check the key, not the format.")
            return 1

        vision_capable = [m for m in available if "gemini" in m]
        self._note(f"provider offers {len(available)} models, {len(vision_capable)} gemini-*")

        if pinned in available:
            self._ok(f"pinned model '{pinned}' resolves")
        else:
            self._fail(f"pinned model '{pinned}' NOT offered - amend DECISIONS.md section 5")
            self._note(f"closest available: {', '.join(vision_capable[:6])}")
            failures += 1

        try:
            from apps.ai.engines import VisionEngine

            result = VisionEngine(api_key, model=pinned).describe(
                _probe_png(), mime_type="image/png", purpose="screenshot"
            )
            preview = (result.text[:60] + "...") if len(result.text) > 60 else result.text
            self._ok(f"live image call succeeded ({result.latency_ms}ms): {preview!r}")
        except Exception as exc:  # noqa: BLE001
            self._fail(f"live image call failed: {exc}")
            failures += 1

        return failures

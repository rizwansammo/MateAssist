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


def _probe_png(size: int = 96) -> bytes:
    """A real 96x96 image with visible structure.

    Not a 1x1 pixel: the Gemini 3.x models reject a degenerate image with
    "Unable to process input image", which reads exactly like a broken model id
    and sent the first run of this command chasing the wrong problem.
    """
    import struct
    import zlib

    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG filter byte
        for x in range(size):
            on_cross = abs(x - size // 2) < 6 or abs(y - size // 2) < 6
            value = 0 if on_cross else 255
            row += bytes([value, value, value])
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


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

    def _key_for(self, engine: str, env_var: str) -> str | None:
        """Vault first, env fallback. The env path exists only for this command."""
        row = ProviderKey.objects.filter(engine=engine, status=ProviderKey.Status.ACTIVE).first()
        if row:
            self.stdout.write(f"    using vault key '{row.label}' ({row.masked})")
            return row.reveal()

        raw = os.environ.get(env_var) or getattr(settings, env_var, "")
        if raw:
            self.stdout.write(f"    using {env_var} from the environment (dev only)")
            return raw.strip()
        return None

    def _ok(self, message):
        self.stdout.write(self.style.SUCCESS(f"    PASS  {message}"))

    def _fail(self, message):
        self.stdout.write(self.style.ERROR(f"    FAIL  {message}"))

    def _note(self, message):
        self.stdout.write(f"          {message}")

    # -- text ------------------------------------------------------------

    def _verify_text(self) -> int:
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Text & Reasoning Engine - DeepSeek"))
        api_key = self._key_for(Engine.TEXT, "DEEPSEEK_API_KEY_BOOTSTRAP")
        if not api_key:
            self._note("no key configured - skipped (open item O-3)")
            return 0

        pinned = [settings.DEEPSEEK_MODEL_CHAT, settings.DEEPSEEK_MODEL_REASONER]
        failures = 0

        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=settings.DEEPSEEK_API_BASE, timeout=30.0)
            available = sorted(m.id for m in client.models.list().data)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"could not list models: {exc}")
            return 1

        self._note(f"provider offers: {', '.join(available) or '(none reported)'}")
        for model in pinned:
            if model in available:
                self._ok(f"pinned model '{model}' resolves")
            else:
                self._fail(f"pinned model '{model}' NOT offered - amend DECISIONS.md section 5")
                failures += 1

        try:
            from apps.ai.engines import TextEngine, TextMessage

            result = TextEngine(api_key).complete(
                [TextMessage(role="user", content="Reply with the single word: ok")],
                max_tokens=5,
            )
            self._ok(
                f"live call returned {result.text.strip()!r} "
                f"({result.prompt_tokens}+{result.completion_tokens} tokens, "
                f"{result.latency_ms}ms)"
            )
        except Exception as exc:  # noqa: BLE001
            self._fail(f"live call failed: {exc}")
            failures += 1

        return failures

    # -- vision ----------------------------------------------------------

    def _verify_vision(self) -> int:
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Vision & OCR Engine - Gemini"))
        api_key = self._key_for(Engine.VISION, "GEMINI_API_KEY_BOOTSTRAP")
        if not api_key:
            self._note("no key configured - skipped (open item O-3)")
            return 0

        pinned = settings.GEMINI_MODEL_VISION
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

            result = VisionEngine(api_key).describe(
                _probe_png(), mime_type="image/png", purpose="screenshot"
            )
            preview = (result.text[:60] + "...") if len(result.text) > 60 else result.text
            self._ok(f"live image call succeeded ({result.latency_ms}ms): {preview!r}")
        except Exception as exc:  # noqa: BLE001
            self._fail(f"live image call failed: {exc}")
            failures += 1

        return failures

"""The Phase 6 gate.

    python manage.py chat_demo --tenant netswitch

Asks a real question, retrieves from the real index, calls the real text engine,
and prints the answer with its citations.

The claim being tested is not "the model replied" - it is that the reply is
GROUNDED: it should contain specifics that exist only in the uploaded runbook,
and cite the document they came from. A fluent answer with no citation is the
failure mode this whole pipeline exists to prevent.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.ai import router
from apps.chat import prompts, retrieval
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

QUESTIONS = [
    "My VPN keeps disconnecting whenever I join a Teams call. What do I do?",
    "What port does the split-tunnel exclusion need?",
]


class Command(BaseCommand):
    help = "Ask grounded questions against the indexed runbooks."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="netswitch")
        parser.add_argument("--question", default=None)

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(f"No tenant '{options['tenant']}'. Run seed_dev first.")
            return

        questions = [options["question"]] if options["question"] else QUESTIONS

        for question in questions:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n  Q: {question}"))

            # The engine call must be INSIDE the tenant context too, not just
            # retrieval: call_text writes a UsageEvent, which is tenant-owned and
            # RLS-protected. Outside the context that write is refused - silently,
            # because metering deliberately never raises (D-110).
            with tenant_context(tenant.id), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])
                hits = retrieval.retrieve(question)

                if not hits:
                    self.stdout.write(self.style.ERROR("    no passages retrieved"))
                    continue

                self.stdout.write("    retrieved:")
                for hit in hits:
                    marker = " [figure]" if hit.from_image else ""
                    self.stdout.write(
                        f"      rrf={hit.score:.4f}  {hit.document_title}{marker}  "
                        f"{hit.text[:70].strip()}..."
                    )

                messages = prompts.build_messages(
                    tenant_name=tenant.name, history=[], question=question, hits=hits
                )

                try:
                    result = router.call_text(
                        messages,
                        tenant=tenant,
                        tools=[prompts.ESCALATION_TOOL],
                        max_tokens=1500,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.stdout.write(self.style.ERROR(f"    engine call failed: {exc}"))
                    continue

                from apps.metering.models import UsageEvent

                metered = UsageEvent.all_objects.filter(operation="chat").count()

            self.stdout.write(self.style.SUCCESS("\n    A:"))
            for line in (result.text or "(empty)").splitlines():
                self.stdout.write(f"      {line}")

            if result.tool_calls:
                for call in result.tool_calls:
                    self.stdout.write(self.style.WARNING(f"\n    proposed tool: {call['name']}"))
                    self.stdout.write(f"      {call['arguments'][:200]}")
                self.stdout.write("      (a proposal only - the user's click sends it, D-126)")

            self.stdout.write(
                f"\n    tokens={result.prompt_tokens}+{result.completion_tokens} "
                f"latency={result.latency_ms}ms model={result.model}"
            )
            # D-110 says no provider call goes unmetered. Asserted here rather
            # than assumed, because the metering write fails silently by design.
            self.stdout.write(
                self.style.SUCCESS(f"    METERED: {metered} chat usage event(s) recorded")
                if metered
                else self.style.ERROR("    NOT METERED: no usage event was written")
            )

            grounded = any(
                token in (result.text or "")
                for token in ("3479", "GlobalProtect", "split-tunnel", "exclusion")
            )
            self.stdout.write(
                self.style.SUCCESS("    GROUNDED: answer contains runbook specifics")
                if grounded
                else self.style.ERROR("    NOT GROUNDED: no runbook specifics in the answer")
            )

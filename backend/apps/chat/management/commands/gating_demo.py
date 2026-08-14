"""The Phase 8 (items 1-2) gate.

    python manage.py gating_demo --tenant netswitch

Runs the real retrieval and the real gate against the indexed corpus, and shows
what each message would produce in the UI. No provider is called - embeddings
are local and both searches are database queries - so this works with an
exhausted API quota.

The claim under test is the bug report: saying "Hi" produced a reply captioned
`Sources: VPN Runbook (demo)`. A greeting must now yield no reference block and
no citation, while a real question must yield both.
"""

from __future__ import annotations

import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.chat import prompts, retrieval
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

# (message, should_ground, should_cite)
CASES = [
    ("Hi", False, False),
    ("Hello?", False, False),
    ("Thanks!", False, False),
    ("who are you", False, False),
    ("My VPN keeps disconnecting whenever I join a Teams call", True, True),
    ("globalprotect wont connect", True, True),
    ("restart globalprotect service", True, True),
    ("the client says disconnected, what now", True, True),
]


class Command(BaseCommand):
    help = "Phase 8 gate: prove citations appear only when earned."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="netswitch")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(f"No tenant '{options['tenant']}'. Run seed_dev first.")
            sys.exit(1)

        failures: list[str] = []

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nGates: ground >= {settings.RETRIEVAL_GROUND_MIN}  "
                f"cite >= {settings.RETRIEVAL_CITE_MIN}\n"
            )
        )

        with tenant_context(tenant.id), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])

            for message, should_ground, should_cite in CASES:
                hits = retrieval.retrieve(message)
                focused = retrieval.focus(hits)
                grounded, citable = retrieval.gate(focused)
                best = max((h.relevance for h in hits), default=0.0)

                # What the model would actually be shown.
                reference = prompts.render_reference(grounded)
                says_nothing_found = "No matching runbook passages" in reference

                sources = ", ".join(sorted({h.document_title for h in citable})) or "-"
                verdict = "OK  "
                if bool(grounded) != should_ground or bool(citable) != should_cite:
                    verdict = "FAIL"
                    failures.append(
                        f"{message!r}: grounded={bool(grounded)} (want {should_ground}), "
                        f"cited={bool(citable)} (want {should_cite})"
                    )

                style = self.style.SUCCESS if verdict == "OK  " else self.style.ERROR
                self.stdout.write(
                    style(
                        f"  {verdict}  {message[:46]:<48} top={best:.3f}  "
                        f"grounded={len(grounded)}  sources={sources}"
                    )
                )

                # A greeting must not merely lack citations - the model must be
                # told plainly that nothing matched, or it fills the silence.
                if not should_ground and not says_nothing_found:
                    failures.append(
                        f"{message!r}: reference block did not state that nothing matched"
                    )

            failures += self._prove_no_blending()

        self.stdout.write(self.style.MIGRATE_HEADING("\nResult"))
        if failures:
            for failure in failures:
                self.stdout.write(self.style.ERROR(f"  - {failure}"))
            self.stderr.write(f"\n{len(failures)} case(s) failed.")
            sys.exit(1)
        self.stdout.write(
            self.style.SUCCESS(
                "  Citations appear only when earned; greetings get a plain reply;\n"
                "  a question about one VPN client never sees the other's runbook.\n"
            )
        )

    def _prove_no_blending(self) -> list[str]:
        """The case document focus exists for.

        Two VPN runbooks are indexed, describing different clients with
        overlapping symptoms and incompatible fixes. A question naming one client
        must not put a single passage from the other in front of the model - not
        ranked lower, not present at all. A model given both writes one coherent
        procedure out of two, and every individual step is true.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nDocument focus (no blending)"))
        failures: list[str] = []

        # Matched against document TITLES, so the GlobalProtect runbook is named
        # by its actual title - "VPN Runbook (demo)", from ingest_demo - rather
        # than by the client it describes.
        GLOBALPROTECT = "VPN Runbook (demo)"
        ANYCONNECT = "AnyConnect"

        probes = [
            ("globalprotect wont connect", GLOBALPROTECT, ANYCONNECT),
            ("restart the globalprotect service", GLOBALPROTECT, ANYCONNECT),
            ("anyconnect keeps dropping on teams calls", ANYCONNECT, GLOBALPROTECT),
            ("delete the anyconnect profile", ANYCONNECT, GLOBALPROTECT),
        ]

        for question, expected, forbidden in probes:
            hits = retrieval.retrieve(question)
            before = sorted({h.document_title for h in hits})
            focused = retrieval.focus(hits)
            grounded, _ = retrieval.gate(focused)
            after = sorted({h.document_title for h in grounded})

            leaked = [title for title in after if forbidden.lower() in title.lower()]
            missing = not any(expected.lower() in title.lower() for title in after)

            ok = not leaked and not missing
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(
                style(
                    f"  {'OK  ' if ok else 'FAIL'}  {question[:42]:<44}\n"
                    f"          retrieved: {', '.join(before) or '-'}\n"
                    f"          shown    : {', '.join(after) or '-'}"
                )
            )
            if leaked:
                failures.append(f"{question!r}: {forbidden} runbook reached the model ({leaked})")
            if missing:
                failures.append(f"{question!r}: the {expected} runbook was not shown at all")

        return failures

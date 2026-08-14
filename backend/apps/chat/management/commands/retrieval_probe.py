"""Measure where relevant questions separate from small talk (D-138).

    python manage.py retrieval_probe --tenant netswitch

Thresholds are the kind of number that looks authoritative and is usually
invented. This command exists so the numbers in settings come from the corpus
they will actually run against, and so the claim "greetings and real questions
separate cleanly" is something we have looked at rather than assumed.

It costs nothing: embeddings are local (D-060) and both searches are database
queries. No provider is called.

Read the output as two columns of `top` values. If the SMALL TALK column and the
REAL column overlap, the approach does not work on this corpus and the honest
move is to say so rather than to pick a number in the overlap.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.chat import retrieval
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

# Things a user types that are not a support request. If any of these retrieves
# a confident match, the corpus is too small or the embedding is too generous.
SMALL_TALK = [
    "Hi",
    "Hello?",
    "Thanks!",
    "ok",
    "good morning",
    "are you there",
    "who are you",
    "cheers, that worked",
    "test",
    "lol",
]

# Real support requests, deliberately including badly-worded ones - the failure
# mode that matters is a genuine problem scoring low, not a greeting scoring high.
REAL_QUESTIONS = [
    "My VPN keeps disconnecting whenever I join a Teams call",
    "vpn drops in meetings",
    "globalprotect wont connect",
    "how do I fix the tunnel",
    "outlook is being weird again",
    "split tunnel exclusion",
    "error 0x80070035",
    "I cannot reach the file share",
    "the client says disconnected, what now",
    "restart globalprotect service",
]


class Command(BaseCommand):
    help = "Measure retrieval relevance for small talk vs real questions."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="netswitch")
        parser.add_argument("--query", default=None, help="Probe a single query instead.")

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(f"No tenant '{options['tenant']}'. Run seed_dev first.")
            return

        with tenant_context(tenant.id), transaction.atomic():
            self._arm(tenant.id)

            if options["query"]:
                self._probe(options["query"], label="QUERY")
                return

            self.stdout.write(self.style.MIGRATE_HEADING("\nSMALL TALK (should NOT cite)"))
            small = [self._probe(q) for q in SMALL_TALK]

            self.stdout.write(self.style.MIGRATE_HEADING("\nREAL QUESTIONS (should cite)"))
            real = [self._probe(q) for q in REAL_QUESTIONS]

        self._verdict(small, real)

    # -- helpers ---------------------------------------------------------

    def _arm(self, tenant_id):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])

    def _probe(self, query: str, label: str = "") -> float:
        hits = retrieval.retrieve(query)
        if not hits:
            self.stdout.write(f"  {query[:44]:<46} no hits")
            return 0.0

        best = max(h.relevance for h in hits)
        cosine = max(h.similarity for h in hits)
        keyword = any(h.keyword_match for h in hits)
        self.stdout.write(
            f"  {query[:44]:<46} top={best:.3f}  cosine={cosine:.3f}  "
            f"fts={'yes' if keyword else 'no ':<3}  hits={len(hits)}"
        )
        return best

    def _verdict(self, small: list[float], real: list[float]) -> None:
        """Report the distributions and NAME the overlap.

        A bare min/max verdict is dominated by one outlier on each side and
        cannot tell the two reasons for a low-scoring "real" question apart:

          * the corpus genuinely does not cover it - in which case scoring low is
            CORRECT, and gating it out produces an honest "no runbook covers
            this" rather than a wrong answer assembled from an unrelated document
          * the phrasing is poor but the answer IS in the corpus - the failure
            mode that would actually hurt

        Only a human reading the question can tell those apart, so this prints
        the overlapping items by name instead of pronouncing a verdict on them.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nSeparation"))

        small_sorted = sorted(small, reverse=True)
        real_sorted = sorted(real)
        best_small = small_sorted[0] if small_sorted else 0.0

        self.stdout.write(
            f"  small talk    : {min(small):.3f} .. {best_small:.3f}   "
            f"(median {small_sorted[len(small_sorted) // 2]:.3f})"
        )
        self.stdout.write(
            f"  real questions: {real_sorted[0]:.3f} .. {max(real):.3f}   "
            f"(median {real_sorted[len(real_sorted) // 2]:.3f})"
        )

        overlapping = [
            (question, score)
            for question, score in zip(REAL_QUESTIONS, real, strict=True)
            if score <= best_small
        ]

        if not overlapping:
            gap = real_sorted[0] - best_small
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n  Clean separation, gap {gap:.3f}.\n"
                    f"  RETRIEVAL_GROUND_MIN <= {best_small + gap * 0.25:.2f}\n"
                    f"  RETRIEVAL_CITE_MIN   ~= {best_small + gap * 0.6:.2f}"
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"\n  {len(overlapping)} real question(s) score at or below the best small talk"
                f" ({best_small:.3f}):"
            )
        )
        for question, score in overlapping:
            self.stdout.write(f"    {score:.3f}  {question}")
        self.stdout.write(
            "\n  Judge each: is it a topic the indexed runbooks do not cover? Then a\n"
            "  low score is correct and gating it out is the honest outcome. If the\n"
            "  answer IS in the corpus, this approach is not safe on this data.\n"
        )

        remainder = [score for score in real if score > best_small]
        if remainder:
            gap = min(remainder) - best_small
            self.stdout.write(
                f"  Excluding those, real questions start at {min(remainder):.3f} "
                f"(gap {gap:.3f}):\n"
                f"    RETRIEVAL_GROUND_MIN ~= {best_small - 0.005:.2f}   "
                f"(generous - grounding survives a borderline question)\n"
                f"    RETRIEVAL_CITE_MIN   ~= {best_small + gap * 0.6:.2f}   "
                f"(strict - a source is only claimed when earned)"
            )

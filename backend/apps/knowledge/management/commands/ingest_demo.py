"""The Phase 5 gate.

    python manage.py ingest_demo --tenant netswitch

Builds a real PDF runbook containing prose AND an embedded diagram, pushes it
through the entire pipeline, and prints the resulting chunks.

The thing to look for in the output is D-054: the figure's Gemini description
must appear INSIDE the chunk containing the procedure that referenced it, not as
a chunk of its own. That is the claim this phase exists to make good on, and it
is not provable by a unit test - it needs a real document, a real vision call and
a real chunker.
"""

from __future__ import annotations

import os
import struct
import zlib

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.ai.models import Engine, ProviderKey
from apps.core.demo_guard import refuse_in_production
from apps.knowledge import storage
from apps.knowledge.models import Document, DocumentAsset, DocumentChunk, FileType
from apps.knowledge.tasks import ingest_document
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

RUNBOOK_TEXT = [
    "Netswitch IT Runbook: GlobalProtect VPN Troubleshooting",
    "",
    "This runbook covers the most common VPN failure reported to the service desk: "
    "the tunnel disconnecting when a user joins a Microsoft Teams call. The cause is "
    "almost always the Teams media path failing over to UDP 3479, which the default "
    "split-tunnel policy does not permit.",
    "",
    "Step 1. Confirm the failure mode.",
    "Ask the user to reproduce the drop while the GlobalProtect status window is open. "
    "If the tunnel state changes to Disconnected within five seconds of the call "
    "connecting, this runbook applies. If it disconnects at random intervals unrelated "
    "to calls, stop here and escalate to the network team instead.",
    "",
    "Step 2. Check the split-tunnel exclusion.",
    "Open the GlobalProtect settings dialog. The Advanced Settings panel shown in the "
    "figure below lists the excluded routes. Verify that UDP 3479 appears in the "
    "exclusion list. If it does not, the tunnel will drop on every call.",
]

RUNBOOK_TEXT_AFTER = [
    "",
    "Step 3. Apply the fix.",
    "Add the exclusion, then restart the GlobalProtect service. The user must "
    "reconnect once for the new policy to take effect. This resolved the issue for "
    "fourteen of fifteen affected users last month.",
    "",
    "Step 4. If the drop persists.",
    "Collect the GlobalProtect logs and raise the issue with the network team, "
    "including the timestamp of a reproduced failure.",
]


def _dialog_png(width: int = 420, height: int = 260) -> bytes:
    """A mock settings dialog: title bar, panel, and two button shapes.

    Drawn by hand rather than shipped as a fixture so the repository carries no
    binary blob and the gate stays self-contained.
    """
    rows = []
    for y in range(height):
        row = bytearray([0])  # PNG filter byte
        for x in range(width):
            if y < 34:  # title bar
                pixel = (28, 40, 64)
            elif y < 38 or y > height - 5 or x < 5 or x > width - 6:  # border
                pixel = (120, 130, 150)
            elif (
                60 < y < 76
                and 24 < x < 300
                or 96 < y < 112
                and 24 < x < 250
                or 132 < y < 148
                and 24 < x < 330
            ):  # a settings row
                pixel = (70, 80, 100)
            elif height - 60 < y < height - 30 and width - 200 < x < width - 110:  # OK
                pixel = (16, 185, 129)
            elif height - 60 < y < height - 30 and width - 100 < x < width - 20:  # Cancel
                pixel = (200, 205, 215)
            else:
                pixel = (246, 248, 251)
            row += bytes(pixel)
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
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def _build_pdf() -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()

    cursor = 60
    for line in RUNBOOK_TEXT:
        page.insert_text((56, cursor), line, fontsize=10.5, fontname="helv")
        cursor += 15

    cursor += 8
    image_rect = pymupdf.Rect(56, cursor, 56 + 300, cursor + 186)
    page.insert_image(image_rect, stream=_dialog_png())
    cursor += 200

    for line in RUNBOOK_TEXT_AFTER:
        page.insert_text((56, cursor), line, fontsize=10.5, fontname="helv")
        cursor += 15

    data = document.tobytes()
    document.close()
    return data


class Command(BaseCommand):
    help = "Ingest a generated runbook PDF end to end and show the resulting chunks."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="netswitch")

    def handle(self, *args, **options):
        refuse_in_production(self, what='a fabricated "VPN Runbook (demo)" into the knowledge base')
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(f"No tenant '{options['tenant']}'. Run seed_dev first.")
            return

        self._ensure_vision_key()

        pdf = _build_pdf()
        self.stdout.write(f"\n  Built a {len(pdf):,}-byte PDF: prose + one embedded figure\n")

        # transaction.atomic is not optional here. set_config(..., is_local => true)
        # is scoped to the CURRENT TRANSACTION, and a management command runs in
        # autocommit - so without an explicit transaction the tenant id is
        # discarded before the INSERT runs and RLS rejects the row. The request
        # middleware wraps every request for the same reason.
        with tenant_context(tenant.id), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])

            key = storage.build_key(tenant.id, "vpn-runbook.pdf")
            storage.put(key, pdf, "application/pdf")

            Document.all_objects.filter(tenant=tenant, title="VPN Runbook (demo)").delete()
            document = Document.all_objects.create(
                tenant=tenant,
                title="VPN Runbook (demo)",
                storage_key=key,
                file_type=FileType.PDF,
                size_bytes=len(pdf),
                checksum=storage.checksum(pdf),
            )

        self.stdout.write(
            "  Running the pipeline (parse -> Gemini -> splice -> chunk -> embed)...\n"
        )
        result = ingest_document(tenant.id, document.id)

        with tenant_context(tenant.id), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])
            self._report(document, result)

    def _ensure_vision_key(self):
        if ProviderKey.objects.filter(
            engine=Engine.VISION, status=ProviderKey.Status.ACTIVE
        ).exists():
            return
        bootstrap = os.environ.get("GEMINI_API_KEY_BOOTSTRAP", "").strip()
        if not bootstrap:
            self.stderr.write("No Gemini key in the vault and no bootstrap key set.")
            return
        key = ProviderKey(engine=Engine.VISION, label="gemini-bootstrap")
        key.set_secret(bootstrap)
        key.save()
        self.stdout.write(
            self.style.WARNING(f"  Seeded the vault with the bootstrap Gemini key ({key.masked})")
        )

    def _report(self, document, result):
        document.refresh_from_db()
        style = self.style

        self.stdout.write(style.SUCCESS(f"\n  status={document.status}"))
        self.stdout.write(
            f"  pages={result['pages']}  images={result['images']}  "
            f"described={result['described']}  chunks={result['chunks']}\n"
        )

        for asset in DocumentAsset.objects.filter(document=document):
            self.stdout.write(
                style.MIGRATE_HEADING(
                    f"  Figure at block {asset.block_index} ({asset.width}x{asset.height}, "
                    f"{asset.describe_status})"
                )
            )
            self.stdout.write(f"    {asset.description_text[:400]}\n")

        self.stdout.write(style.MIGRATE_HEADING("  Chunks:"))
        for chunk in DocumentChunk.all_objects.filter(document=document):
            marker = "FIGURE" if chunk.from_image else "text  "
            preview = chunk.text.replace("\n", " ")[:150]
            self.stdout.write(
                f"    [{chunk.ordinal}] {marker} {chunk.token_count:>4}tok  {preview}..."
            )

        spliced = DocumentChunk.all_objects.filter(document=document, from_image=True)
        self.stdout.write("")
        if spliced.exists():
            chunk = spliced.first()
            has_procedure = "Step" in chunk.text
            self.stdout.write(
                style.SUCCESS(
                    f"  D-054 VERIFIED: the figure description is inside chunk {chunk.ordinal}, "
                    f"{'alongside the procedure text' if has_procedure else 'as its own passage'}."
                )
            )
        else:
            self.stdout.write(style.ERROR("  D-054 FAILED: no chunk carries a figure description."))

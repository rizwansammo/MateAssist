"""Build a realistic multi-document corpus (D-139).

    python manage.py seed_runbooks --tenant netswitch

Markdown only, so nothing here calls a provider: embeddings are local (D-060)
and there are no figures to describe. It runs with an exhausted API quota.

**Why a second VPN runbook exists.** With one document indexed, every retrieval
question trivially "wins" and document blending cannot be observed, let alone
prevented. The Cisco AnyConnect runbook below deliberately overlaps the existing
GlobalProtect one - same symptoms, same vocabulary, different client and
different fix - because that near-duplicate pair is the exact case where a model
writes one tidy procedure out of two incompatible sources.

The remaining runbooks are ordinary corpus breadth. They also make
`retrieval_probe` worth trusting: thresholds fitted against a single document
say very little.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.core.demo_guard import refuse_in_production
from apps.knowledge import storage
from apps.knowledge.models import Document, FileType
from apps.knowledge.tasks import ingest_document
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

ANYCONNECT = """# Netswitch IT Runbook: Cisco AnyConnect VPN

This runbook covers AnyConnect only. Netswitch runs two VPN clients: the
engineering estate is on GlobalProtect, and the finance and legal teams are on
Cisco AnyConnect. The symptoms are similar and the fixes are not
interchangeable - applying a GlobalProtect fix to an AnyConnect client will not
work and may leave a stale profile behind.

## Step 1. Confirm which client the user has

Ask the user to open the system tray and read the icon tooltip. AnyConnect
reports "Cisco AnyConnect Secure Mobility Client". If it says GlobalProtect,
stop and use the GlobalProtect runbook instead.

## Step 2. The tunnel drops during calls

AnyConnect drops the tunnel during Teams calls when the corporate profile has
Trusted Network Detection enabled and the user is on a home network that
advertises a matching DNS suffix. The tunnel is not failing - the client
believes it is already inside the corporate network and disconnects on purpose.

## Step 3. Apply the fix

Delete the cached profile at %APPDATA%\\Cisco\\Cisco AnyConnect Secure Mobility
Client\\Profile and sign out of the client completely. On the next sign-in the
client downloads a fresh profile from the gateway. Do not restart a Windows
service for this - AnyConnect stores its state in the user profile, not in the
service.

## Step 4. Re-enter the gateway address

After a profile reset the connection list is empty. The user must type
vpn.netswitch.example into the address box once; it is remembered afterwards.

## Step 5. If it persists

Collect the AnyConnect diagnostic bundle using the DART tool and attach it to
the escalation. Client logs alone are not enough for the network team.
"""

OUTLOOK = """# Netswitch IT Runbook: Outlook and Exchange

## Symptom: Outlook will not start

Outlook hanging on the splash screen is nearly always a corrupt profile or an
add-in that failed to load. Start it in safe mode with outlook.exe /safe. If it
opens cleanly, the cause is an add-in.

## Symptom: mailbox is full

The default mailbox quota is 50 GB. A user over quota can receive but not send.
Check the quota in the Exchange admin centre before assuming a sync fault.

## Symptom: shared mailbox missing

A shared mailbox added via automapping can take up to 24 hours to appear. If the
user needs it immediately, add it manually as a secondary account.

## Symptom: repeated password prompts

This is usually a stale cached credential. Clear the entries under Credential
Manager, Windows Credentials, then restart Outlook. Do not reset the user's
password for this - it will not help and locks them out of everything else.
"""

PRINTING = """# Netswitch IT Runbook: Printing

## Symptom: print jobs stuck in the queue

Stop the Print Spooler service, delete everything in
C:\\Windows\\System32\\spool\\PRINTERS, then start the spooler again. Jobs
submitted before the clear are lost and must be re-sent.

## Symptom: printer offline

Check whether the printer has fallen off the network before touching the client.
Ping the device address. If it responds, the fault is on the workstation; if it
does not, it is a network or device fault and the client is irrelevant.

## Symptom: wrong default printer

Windows resets the default printer to the last one used unless the "Let Windows
manage my default printer" setting is turned off. Turn it off before setting the
default, or it will revert.

## Symptom: badge release not working

Follow-me printing requires the badge to be registered against the user account.
A newly issued badge takes one sync cycle, up to 30 minutes, before it releases
jobs.
"""

ACCOUNTS = """# Netswitch IT Runbook: Accounts, Passwords and MFA

## Password resets

Passwords expire every 90 days. A user who has not signed in for longer than
that will be prompted at next login and can self-serve at the password portal.
Verify identity before resetting on their behalf - a callback to the number on
record, never the number given in the request.

## MFA device replacement

When a user replaces a phone, the old authenticator registration must be removed
before a new one is added, or the sign-in prompt will target the old device.
This requires an administrator; the user cannot do it themselves.

## Account lockouts

Three failed attempts locks the account for 15 minutes. The lockout clears by
itself. Repeated lockouts within an hour usually mean a stale credential on a
second device - a phone still holding the old mail password is the most common
cause.

## New starter accounts

Accounts are provisioned from the HR feed overnight. A starter added to HR after
17:00 will not have an account the following morning; this is expected and not a
fault to escalate.
"""

RUNBOOKS = [
    ("AnyConnect VPN Runbook", "anyconnect-vpn.md", ANYCONNECT),
    ("Outlook and Exchange Runbook", "outlook.md", OUTLOOK),
    ("Printing Runbook", "printing.md", PRINTING),
    ("Accounts and MFA Runbook", "accounts.md", ACCOUNTS),
]


class Command(BaseCommand):
    help = "Ingest a multi-document markdown corpus (no provider calls)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="netswitch")

    def handle(self, *args, **options):
        refuse_in_production(self, what="four fabricated runbooks into the knowledge base")
        tenant = Tenant.objects.filter(slug=options["tenant"]).first()
        if tenant is None:
            self.stderr.write(f"No tenant '{options['tenant']}'. Run seed_dev first.")
            return

        for title, filename, body in RUNBOOKS:
            data = body.encode("utf-8")

            # Explicit transaction: set_config(..., is_local => true) is scoped to
            # the current transaction and a management command runs in autocommit,
            # so without this the tenant id is gone before the INSERT and RLS
            # refuses the row.
            with tenant_context(tenant.id), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])

                key = storage.build_key(tenant.id, filename)
                storage.put(key, data, "text/markdown")

                Document.all_objects.filter(tenant=tenant, title=title).delete()
                document = Document.all_objects.create(
                    tenant=tenant,
                    title=title,
                    storage_key=key,
                    file_type=FileType.MD,
                    size_bytes=len(data),
                    checksum=storage.checksum(data),
                )

            result = ingest_document(tenant.id, document.id)
            self.stdout.write(
                f"  {title:<32} {result.get('chunks', 0):>3} chunks  "
                f"{result.get('status', '?')}"
            )

        with tenant_context(tenant.id), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])
            total = Document.all_objects.filter(tenant=tenant).count()

        self.stdout.write(
            self.style.SUCCESS(f"\n  {tenant.slug} now has {total} indexed document(s).\n")
        )

"""Recover the platform owner's account from the server (D-175).

    python manage.py reset_platform_owner --email you@example.com
    python manage.py reset_platform_owner --email you@example.com --password '...'

The last resort. Every other recovery path goes through email, so all of them
fail together the moment the mailbox is the thing that is lost - a closed
account, an expired domain, a provider suspension. Somebody with server access
has to be able to get back in without it.

Deliberately a command and not an endpoint. It requires shell access to the
production host, which is the authorisation: there is no request that can reach
this, and nothing to brute-force.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.tenancy.models import Membership, Role


class Command(BaseCommand):
    help = "Reset a platform owner's password from the server. Recovery of last resort."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="The platform owner's address.")
        parser.add_argument(
            "--password",
            default="",
            help="Leave empty to generate one and print it.",
        )
        parser.add_argument(
            "--promote",
            action="store_true",
            help="Grant PLATFORM_OWNER if the account does not already hold it.",
        )

    def handle(self, *args, **options):
        from apps.tenancy import provisioning

        email = options["email"].strip().lower()
        User = get_user_model()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist as exc:
            raise CommandError(f"No account for {email}.") from exc

        is_owner = Membership.all_objects.filter(
            user=user, tenant__isnull=True, role=Role.PLATFORM_OWNER
        ).exists()

        if not is_owner and not options["promote"]:
            # Refusing by default. A typo in --email would otherwise silently
            # reset a tenant user's password from a command whose name says it
            # touches the platform owner.
            raise CommandError(
                f"{email} is not a platform owner. Pass --promote to grant it deliberately."
            )

        password = options["password"].strip() or provisioning.generate_password()
        try:
            provisioning.check_password_strength(password, user)
        except provisioning.ProvisioningError as exc:
            raise CommandError(str(exc)) from exc

        user.set_password(password)
        # A locked-out owner may also have been deactivated; recovery that
        # leaves them unable to sign in is not recovery.
        user.is_active = True
        user.save(update_fields=["password", "is_active"])

        if not is_owner:
            Membership.all_objects.create(user=user, tenant=None, role=Role.PLATFORM_OWNER)
            self.stdout.write(self.style.WARNING(f"  Granted PLATFORM_OWNER to {email}."))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  {email}"))
        self.stdout.write(self.style.SUCCESS(f"  {password}"))
        self.stdout.write("")
        # Printed to a terminal, which means it is in that terminal's scrollback
        # and possibly its history file. Saying so is cheaper than assuming
        # anyone thought about it.
        self.stdout.write("  Shown once. Change it after signing in - this is now in your")
        self.stdout.write("  shell scrollback.")
        self.stdout.write("")

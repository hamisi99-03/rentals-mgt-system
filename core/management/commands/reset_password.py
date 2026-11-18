import getpass

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.recovery import reset_owner_password


class Command(BaseCommand):
    help = "Reset the owner password using the recovery code shown at setup."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Owner username to reset (defaults to first user).")

    def handle(self, *args, **options):
        code = getpass.getpass("Recovery code: ")
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm new password: ")
        if password != confirm:
            raise CommandError("The passwords do not match.")
        try:
            user = reset_owner_password(
                code, password, username=options.get("username")
            )
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(f"Password reset for {user.username}."))

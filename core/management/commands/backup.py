from django.core.management.base import BaseCommand, CommandError

from core.backup import perform_backup


class Command(BaseCommand):
    help = "Copy the SQLite database and uploaded files to the backup folder."

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination",
            help="Override the configured backup folder for this run.",
        )

    def handle(self, *args, **options):
        log = perform_backup(destination=options.get("destination"), reason="command")
        if log.result == "ok":
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backup OK ({log.size_bytes} bytes) in {log.destination_path}"
                )
            )
        else:
            raise CommandError(f"Backup failed: {log.message}")

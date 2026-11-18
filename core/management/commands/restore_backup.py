from django.core.management.base import BaseCommand, CommandError

from core.backup import perform_restore


class Command(BaseCommand):
    help = "Restore the database from a backup file. Takes a safety backup first."

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to a rentals-*.sqlite3 backup file.")
        parser.add_argument(
            "--media-zip",
            help="Optional media-*.zip backup to restore uploaded files.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive confirmation. Required in non-interactive runs.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        if not options["yes"]:
            self.stdout.write(
                self.style.WARNING(
                    "This replaces the live database after taking a safety backup."
                )
            )
            answer = input('Type "RESTORE" to continue: ')
            if answer.strip() != "RESTORE":
                self.stdout.write("Restore cancelled.")
                return

        try:
            log = perform_restore(source, media_zip=options.get("media_zip"))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Restore OK from {log.destination_path}")
        )

from django.core.management.base import BaseCommand, CommandError

from core.theme import MIN_CONTRAST, check_all


class Command(BaseCommand):
    help = "Check WCAG contrast for every palette in light and dark mode."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min",
            type=float,
            default=MIN_CONTRAST,
            help=f"Minimum ratio to require (default {MIN_CONTRAST}).",
        )

    def handle(self, *args, **options):
        minimum = options["min"]
        results = check_all(minimum)
        failures = [result for result in results if not result["ok"]]

        self.stdout.write(
            f"Checked {len(results)} colour pairs across "
            f"{len({r['palette'] for r in results})} palettes and 2 modes."
        )
        for failure in failures:
            kind = "missing" if failure.get("missing") else f"{failure['ratio']}:1"
            self.stdout.write(
                self.style.ERROR(
                    f"FAIL {failure['mode']}/{failure['palette']}: {failure['label']} "
                    f"({failure['fg']} on {failure['bg']}, {kind}, need {minimum}:1)"
                )
            )

        if failures:
            raise CommandError(f"{len(failures)} contrast check(s) failed.")
        self.stdout.write(self.style.SUCCESS("All contrast checks passed."))

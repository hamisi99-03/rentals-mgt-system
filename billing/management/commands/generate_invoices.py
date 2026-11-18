from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from billing.services import (
    default_due_date,
    generate_period,
    parse_period,
    preview_period,
)
from core.models import Settings


class Command(BaseCommand):
    help = "Generate monthly invoices for every eligible lease. Safe to run twice."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            required=True,
            help="Invoice month in YYYY-MM format.",
        )
        parser.add_argument(
            "--due-date",
            help="Due date in YYYY-MM-DD. Defaults to Settings.invoice_due_day.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be generated without writing anything.",
        )

    def handle(self, *args, **options):
        try:
            period_start, period_end = parse_period(options["period"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        settings_obj = Settings.load()
        if options.get("due_date"):
            try:
                due_date = datetime.strptime(options["due_date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("Due date must be YYYY-MM-DD.") from exc
        else:
            due_date = default_due_date(period_start, settings_obj)

        if options["dry_run"]:
            rows, skipped = preview_period(period_start, period_end, settings_obj)
            total = sum((row["total"] for row in rows), start=0)
            self.stdout.write(
                f"Would generate {len(rows)} invoice(s), skip {skipped}, "
                f"total {settings_obj.currency} {total:,.2f} due {due_date}."
            )
            for row in rows:
                self.stdout.write(
                    f"  {row['lease'].unit.code} {row['lease'].tenant.business_name}: "
                    f"{settings_obj.currency} {row['total']:,.2f}"
                )
            return

        created, skipped = generate_period(
            period_start, period_end, due_date, settings_obj=settings_obj
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Generated {len(created)} invoice(s); skipped {skipped}; "
                f"run at {timezone.localtime():%Y-%m-%d %H:%M}."
            )
        )

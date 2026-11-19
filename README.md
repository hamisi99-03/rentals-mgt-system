# rentals-mgt-system

An offline desktop application for managing a commercial building of 20 to 100 shop units rented to business tenants. Built with Django, SQLite, pywebview and a themeable dashboard-first UI.

## Status

Phase 1 (foundation) is complete: project scaffold, the single owner account with login and idle auto-lock, Settings, audit trail, backup/restore, theme system, shared layout and components, and the desktop launcher.

Phase 2 (property core) is complete: buildings, floors and units with table and floor-grid views; tenants with contacts, document uploads and profile tabs; leases with rent history, escalation rules, overlap prevention and automatic unit occupancy; plus a validated Excel importer for buildings, floors, units, tenants and leases.

Phase 3 (billing engine) is complete: charge types and lease charges; atomic per-unit invoice numbering; a monthly billing run with preview, selection and PDFs; 30-day proration; compounding escalation catch-up; VAT snapshots; and utility types, meter readings and utility invoice lines.

Phase 4 (payments) is complete: recorded payments with allocation preview and manual overrides; cash + withholding settlement; credit created from overpayments and applied automatically at invoice generation; cheque received/banked/bounced lifecycle; A4 and thermal receipt output; payment histories on tenant statements and invoices; and M-Pesa/bank CSV statement imports with suggested matches that require confirmation. Phase 5 (operations) is complete: explicit deposit receipts and move-out settlements with checklists, final meter readings and printable settlement PDFs; prospects and vacant-unit tracking with prospect-to-lease conversion; maintenance requests that can create expenses; and categorized expenses with receipt attachments. Phase 6 (reports and dashboard) is complete: a ledger-backed dashboard with metric cards, income-vs-expense and arrears charts, needs-attention panel, date-filtered arrears, monthly income and expense, occupancy, tenant statement and tax reports with Excel and PDF exports, and an overdue reminder list with call and WhatsApp actions. The offline build bundles Chart.js locally. Phase 7 (hardening and delivery) adds the first-run owner setup wizard with a one-time recovery code, per-user data in `%LOCALAPPDATA%\RentalsManager`, backup-before-migration startup, dashboard backup warnings, a Help & Support screen with a privacy-safe support bundle, a demo seed command, coverage/performance hardening, an offline PyInstaller desktop build and an Inno Setup installer script. See `docs/OWNER_GUIDE.md`, `docs/RUNNING.md` and `docs/RELEASE_CHECKLIST.md`. `plan.md` is the specification; `docs/` holds the schema, wireframes and theme rules that must be followed (the updated `docs/SCHEMA.md` makes this a single-owner app).

## Windows desktop build

```powershell
pip install -r requirements-build.txt
.\scripts\build_windows.ps1
# With Inno Setup 6 installed:
.\scripts\build_windows.ps1 -Installer
```

Outputs `dist\RentalsManager\RentalsManager.exe` and, with Inno Setup, `dist\RentalsManager-Setup-1.0.0.exe`. The installer uses a per-user install and leaves business data in `%LOCALAPPDATA%\RentalsManager`.

## Stack

- Python 3.12, Django 5.2, SQLite
- pywebview desktop shell, waitress local server
- pytest + pytest-django
- openpyxl, reportlab, Pillow and python-escpos
- Chart.js (vendored locally for offline charts)

## Setup (Windows)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```

Open the app (or `python manage.py runserver` and visit `/setup/`). The first-run wizard creates the owner account, company details, theme and the one-time recovery code. `createsuperuser` remains available as a developer fallback.

Run the normal development server:

```powershell
python manage.py runserver
```

Run the desktop app (waitress + pywebview, opens the window, backs up on exit):

```powershell
python launcher.py
```

## Tests and checks

```powershell
pytest
python manage.py check_theme_contrast
```

The contrast command checks every palette in light and dark mode for at least 4.5:1 text contrast. The pytest suite also fails if colours are hardcoded outside `static/css/theme.css`.

## Backups and restore

Backups run on app startup if the last successful one is over 24 hours old, and on app exit. Manual runs are available from Settings > Backup or the command line:

```powershell
python manage.py backup
python manage.py backup --destination "E:\RentalsBackups"
python manage.py restore_backup "E:\RentalsBackups\rentals-YYYYMMDD-HHMMSS.sqlite3" --yes
```

Restore validates the file, takes a safety backup first, replaces the database and media (with `--media-zip`) and writes an audit entry.

## Data location

- Development: `db.sqlite3`, `media/`, `backups/` and `instance/` in the repository (not committed).
- Installed app: `%LOCALAPPDATA%\RentalsManager` for the database, uploads, backups, logs, secret key and recovery hash. Reinstalling or updating the app never touches this folder.
- Override with `RENTALS_DATA_DIR` for testing or a custom location.

## Deviations and deferrals from `docs/`

- `NumberSequence` lives in `core` because invoices and later receipts share it; the fields match `docs/SCHEMA.md`.
- `AuditLog` and `BackupLog` use the explicit `timestamp`/`user` fields listed in `docs/SCHEMA.md` instead of duplicating generic created/updated columns.
- Per the updated `docs/SCHEMA.md`, there is one owner account: the manager role, role field and role-based checks are removed. The first-run setup wizard, one-time recovery code and idle auto-lock are implemented.
- Opening balances are not in the Phase 2 importer because invoices and credit entries do not exist until the billing and payments phases.
- Lease deletion is a terminate action, and units/tenants are archived rather than hard-deleted, following the no-hard-delete rule. Buildings and floors can only be deleted when empty.
- Lease status history is read from the append-only audit log because `docs/SCHEMA.md` defines no separate status-history table.
- Renewal alerts use the lease end date and `Settings.renewal_alert_days` in the dashboard needs-attention panel; the schema has no lease renewal-date field.
- UtilityType and MeterReading live in the billing app rather than property to avoid a circular migration through MeterReading.invoice_line; their fields and rules match the schema.
- Invoice voiding and recalculation are not in Phase 3; the status/void fields exist and issued invoices are immutable snapshots.
- Billing money rules confirmed for this build: partial months use a fixed 30-day month; monthly charges prorate while quarterly/once charges bill in full; rent and utility lines follow the tenant VAT flag while service/other lines follow ChargeType.vat_applicable; all missed escalation steps compound up to the period start; active and expired leases overlapping the period are billed, while draft and terminated leases are not.
- Unbilled meter readings are caught up on the next invoice up to the invoice period end, so a missed billing run does not lose consumption.
- Business defaults for this build: every new lease automatically gets one flat monthly service charge (default KES 500.00 from `Settings.service_charge_amount`) covering water, electricity, security and toilet regardless of use, so those items are not metered; rent review rules default to a 24-month interval when enabled; VAT is not yet introduced and remains off by default; and new payments are bank deposits only (older M-Pesa/cash/cheque values stay readable).
- Payment.amount is the bank deposit received; withholding is separate and deposit + withholding settle invoices. An overpayment CreditEntry is created for any unallocated settlement.
- Credit is applied automatically when an invoice is generated and counts toward that invoice's paid amount; credit entries from a voided or bounced payment are excluded from balances.
- Receipt numbers use the tenant's primary unit, falling back to the unit of the oldest allocated invoice. A payment with no unit and no allocation is blocked with a clear error.
- Statement imports parse M-Pesa and common bank CSV headers, but the import screen now accepts bank statements only. Rows are never posted without confirmation. The row FK is stored as import_id because import is a Python keyword.
- Thermal receipts are generated as raw ESC/POS bytes for download; choosing a physical printer and spooling it can be added once the printer configuration is known.
- Refunds are handled by the move-out/deposit settlement; non-deposit credit refunds are not a separate ledger entry.
- Deposits are explicit receipts per lease (amount + date), not auto-created from lease.deposit_amount; move-out uses the recorded held deposits.
- Move-out refunds floor at zero when arrears plus damages exceed the deposit; the remaining tenant balance stays outstanding and is shown on the settlement.
- Arrears at exit use the tenant's total outstanding balance, and confirming a refund terminates the lease on the move-out date and frees the unit.
- Final meter readings are recorded on the move-out date but are not auto-invoiced; they appear on the settlement PDF.
- Refunds update Deposit statuses and the MoveOut snapshot; no separate cash-refund ledger entry is created in this phase.
- Planned move-outs have no cancel/delete action yet; they can be settled or edited before settlement.
- Expense receipts use the generic Document model; expense categories are disabled rather than hard-deleted.
- Vacancies are surfaced on the Prospects page and the Units status filter rather than as a separate sidebar screen.
- Dashboard definitions: Rent due = invoices whose period is the current month; Collected = posted payments received this month (cash + withholding); Arrears = overdue invoices only; Occupied = occupied active units over all active units.
- Income in the chart and monthly report is collected payments; billed invoice totals are shown as a separate column. Tax summary uses invoice issue dates for rent/VAT and payment dates for withholding.
- Arrears ageing uses overdue invoice balances by due date; occupancy is a current snapshot rather than historical.
- Reports use current ledger balances: the arrears as-of filter shows current balances for invoices overdue at that date, not a historical reconstruction of payments after the date. The dashboard uses the current month and a six-month window.
- Overdue reminder rows are one per tenant: oldest overdue invoice for {invoice}/{unit}, total overdue balance for {balance}; WhatsApp/call links only appear with a contact phone.
- Report exports are generated on demand in Excel/PDF; there is no scheduled or emailed report in this phase.
- Chart.js is vendored under static/vendor (MIT) so charts work fully offline and read their colours from the active theme variables.

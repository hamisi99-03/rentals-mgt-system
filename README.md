# rentals-mgt-system

An offline desktop application for managing a commercial building of 20 to 100 shop units rented to business tenants. Built with Django, SQLite, pywebview and a themeable dashboard-first UI.

## Status

Phase 1 (foundation) is complete: project scaffold, the single owner account with login and idle auto-lock, Settings, audit trail, backup/restore, theme system, shared layout and components, and the desktop launcher.

Phase 2 (property core) is complete: buildings, floors and units with table and floor-grid views; tenants with contacts, document uploads and profile tabs; leases with rent history, escalation rules, overlap prevention and automatic unit occupancy; plus a validated Excel importer for buildings, floors, units, tenants and leases.

Phase 3 (billing engine) is complete: charge types and lease charges; atomic per-unit invoice numbering; a monthly billing run with preview, selection and PDFs; 30-day proration; compounding escalation catch-up; VAT snapshots; and utility types, meter readings and utility invoice lines. Payments, operations and reports remain placeholders for their later phases. `plan.md` is the specification; `docs/` holds the schema, wireframes and theme rules that must be followed (the updated `docs/SCHEMA.md` makes this a single-owner app).

## Stack

- Python 3.12, Django 5.2, SQLite
- pywebview desktop shell, waitress local server
- pytest + pytest-django
- openpyxl, reportlab and Pillow installed for later phases

## Setup (Windows)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

The first account created with `createsuperuser` is the owner account. The Phase 7 first-run wizard will replace this step and add the one-time recovery code. Set the owner's display name and auto-lock period from Settings, or with:

```powershell
python manage.py shell -c "from core.models import User; u=User.objects.get(username='owner'); u.full_name='Owner Name'; u.auto_lock_minutes=15; u.save()"
```

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

- `db.sqlite3` - application database
- `media/` - uploads (logos, documents)
- `backups/` - default backup folder
- `instance/secret_key.txt` - generated Django secret key

These local files are not committed.

## Deviations and deferrals from `docs/`

- `NumberSequence` lives in `core` because invoices and later receipts share it; the fields match `docs/SCHEMA.md`.
- `AuditLog` and `BackupLog` use the explicit `timestamp`/`user` fields listed in `docs/SCHEMA.md` instead of duplicating generic created/updated columns.
- The payments, operations and reports apps exist with their routes and shell placeholders only.
- Per the updated `docs/SCHEMA.md`, there is one owner account: the manager role, role field and role-based checks are removed. Owner-specific password recovery codes and the first-run wizard belong to Phase 7; the auto-lock behaviour and setting are implemented now.
- Opening balances are not in the Phase 2 importer because invoices and credit entries do not exist until the billing and payments phases.
- Lease deletion is a terminate action, and units/tenants are archived rather than hard-deleted, following the no-hard-delete rule. Buildings and floors can only be deleted when empty.
- Lease status history is read from the append-only audit log because `docs/SCHEMA.md` defines no separate status-history table.
- Renewal alerts will be derived from the lease end date and `Settings.renewal_alert_days` in Phase 6; the schema has no lease renewal-date field.
- UtilityType and MeterReading live in the billing app rather than property to avoid a circular migration through MeterReading.invoice_line; their fields and rules match the schema.
- Invoice voiding and recalculation are not in Phase 3; the status/void fields exist and issued invoices are immutable snapshots.
- Billing money rules confirmed for this build: partial months use a fixed 30-day month; monthly charges prorate while quarterly/once charges bill in full; rent and utility lines follow the tenant VAT flag while service/other lines follow ChargeType.vat_applicable; all missed escalation steps compound up to the period start; active and expired leases overlapping the period are billed, while draft and terminated leases are not.
- Unbilled meter readings are caught up on the next invoice up to the invoice period end, so a missed billing run does not lose consumption.

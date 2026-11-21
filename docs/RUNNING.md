# Running Rentals Manager (developer)

## Prerequisites

- Python 3.12 (the build uses 3.12.10)
- Windows 10/11 for the desktop shell
- Node.js is only needed to syntax-check JavaScript; it is not required at runtime

## Local development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-build.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run the desktop shell instead:

```powershell
python launcher.py
```

The launcher:

1. loads settings and creates the user data folder,
2. backs up an existing database before migrations,
3. applies migrations automatically,
4. starts waitress on localhost,
5. opens the pywebview window,
6. backs up on exit.

## Data folders

- Development: the repository folder (`db.sqlite3`, `media/`, `backups/`, `instance/`).
- Packaged app: `%LOCALAPPDATA%\RentalsManager` (database, media, backups, logs, secret key, recovery hash).
- Override the data folder with `RENTALS_DATA_DIR` when needed.

The app version is in `config/settings.py` (`APP_VERSION`).

## Tests and quality

```powershell
pytest
pytest --cov=core --cov=property --cov=billing --cov=payments --cov=operations --cov=reports --cov-report=term-missing
python manage.py check_theme_contrast
python manage.py check
python manage.py makemigrations --check --dry-run
```

Current suite: 222 tests. Coverage and performance results are recorded in `docs/RELEASE_CHECKLIST.md`.

## Commands

```powershell
python manage.py migrate              # required for a fresh RENTALS_DATA_DIR
python manage.py seed_demo            # 40 units/tenants, 12 months of invoices/payments
python manage.py seed_demo --units 5 --months 2
python manage.py generate_invoices --period 2026-11 [--dry-run]
python manage.py backup
python manage.py backup --destination "E:\RentalsBackups"
python manage.py restore_backup "E:\RentalsBackups\rentals-YYYYMMDD-HHMMSS.sqlite3" --yes
python manage.py reset_password       # uses the recovery code shown at setup
```

`seed_demo` refuses to run when units or tenants already exist; use a fresh data folder for demos.

## First run and recovery

- With no users, opening the app redirects to `/setup/`.
- Setup creates the owner account, company settings, theme and a one-time recovery code.
- The recovery hash is stored in the data folder; the plain code is not stored.
- Reset a lost password with `python manage.py reset_password` and enter the recovery code.

## Building the Windows delivery

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build_windows.ps1
# With Inno Setup 6 installed:
.\scripts\build_windows.ps1 -Installer
# or: iscc installer.iss
```

Outputs:

- `dist\RentalsManager\RentalsManager.exe` (PyInstaller onedir)
- `dist\RentalsManager-Setup-1.1.0.exe` (Inno Setup, per-user install)

The installer creates a desktop and Start menu shortcut and an uninstaller. Business data is in `%LOCALAPPDATA%\RentalsManager`, outside the install folder, so updates/reinstalls leave it alone.

## Architecture

Django apps:

- `core` - owner user, settings, audit, backup, themes, setup, help
- `property` - buildings, floors, units, tenants, contacts, documents, leases
- `billing` - charges, invoices, numbering, utilities/meter readings, invoice PDFs
- `payments` - payments, allocations, credit, cheques, receipts, statement imports
- `operations` - deposits, move-outs, prospects, maintenance, expenses
- `reports` - dashboard data, reports and exports

Theme colours live only in `static/css/theme.css`. Chart.js is vendored in `static/vendor` for offline charts.

## Restore drill

Use a copy of the data folder. With the app closed:

```powershell
python manage.py restore_backup "<backup.sqlite3>" --yes
```

The command verifies the SQLite file, takes a safety backup, replaces the database, and writes an audit entry. Reopen the app and check the dashboard and a recent invoice.

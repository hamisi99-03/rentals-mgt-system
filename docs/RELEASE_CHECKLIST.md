# Release checklist - Rentals Manager 1.0.0

## Automated checks

Coverage measured at 92% across the six application packages; critical billing/allocation services are covered by dedicated tests.

- [ ] `.\.venv\Scripts\python.exe -m pytest`
- [ ] `.\.venv\Scripts\python.exe -m pytest --cov=core --cov=property --cov=billing --cov=payments --cov=operations --cov=reports --cov-report=term-missing`
- [ ] `python manage.py check`
- [ ] `python manage.py makemigrations --check --dry-run`
- [ ] `python manage.py check_theme_contrast`
- [ ] `node --check static/js/app.js`, `theme.js`, `payments.js`, `dashboard.js`

## Backup restore drill

1. In a fresh data folder, seed demo data and run a backup.
2. Note the dashboard totals and a recent invoice number.
3. Close the app; run `python manage.py restore_backup "<backup.sqlite3>" --yes`.
4. Reopen and confirm the dashboard totals and invoice are identical.
5. Confirm a `restore` entry exists in the Activity log.

## Month-end reconciliation

1. Sum issued invoices for the month and compare with the dashboard **Rent due**.
2. Sum posted payments (cash + withholding) for the month and compare with **Collected**.
3. Sum overdue invoice balances and compare with **Arrears** and the arrears buckets.
4. Compare the tenant statement closing balance with the tenant profile balance.
5. Compare the tax summary rent/VAT/withholding with invoices and payments for the period.
6. Confirm every tenant balance is derived from invoices, allocations and credit entries; nothing is edited by hand.

## Clean Windows installer test

1. Use a Windows 10/11 machine with no Python installed.
2. Install `dist\RentalsManager-Setup-1.0.0.exe`.
3. Launch from the desktop shortcut; confirm the setup wizard appears.
4. Complete company details, owner password and recovery code; sign in.
5. Confirm data is written to `%LOCALAPPDATA%\RentalsManager`, not the install folder.
6. Close and relaunch; confirm the owner is remembered and data is intact.
7. Back up, restore from the backup, and confirm the Activity log.
8. Uninstall and reinstall; confirm the business data in AppData survives.

## Known limitations / deviations

- Single owner account only; no manager roles or user administration.
- Invoice voiding/recalculation UI is not implemented; issued invoices are immutable snapshots and void fields exist for later.
- Thermal receipts are raw ESC/POS downloads; printer selection/spooling is not configured in the app.
- Refunds are deposit/move-out settlements; non-deposit refund credit is not a separate ledger entry.
- Statement imports support M-Pesa and common bank CSV headers; no live bank API.
- Arrears-as-of uses current balances; it is not a historical replay of post-date payments.
- Occupancy and dashboard figures are current snapshots.
- Planned move-outs cannot be cancelled; settle or edit them before confirmation.
- Opening balances are not imported.
- See `README.md` for the complete deviation list from `docs/`.

## Performance

Measured locally with the demo seed (40 units, 480 invoices, 320 payments, 24 expenses):

- Seed time: 4.9 s.
- Dashboard: 91 ms / 26 queries.
- Arrears report: 88 ms / 6 queries.
- Monthly income/expense: 16 ms / 36 queries.
- Tax summary: 16 ms / 37 queries.
- Overdue reminders: 51 ms / 44 queries.

- Seed 12 months (`python manage.py migrate` first, then `python manage.py seed_demo`) and re-check Dashboard, Arrears, Monthly and Tax load times after query changes.
- Schema indexes cover invoices by tenant/due date/status, payments by tenant/date, allocations by invoice, leases by unit/status and end date, audit timestamps and statement match status.
- Re-run after any query change; the target is a responsive single-PC experience for 40-100 units and 12 months of history.

## Release assets

- [ ] `dist\RentalsManager\RentalsManager.exe` (PyInstaller onedir)
- [ ] `dist\RentalsManager-Setup-1.0.0.exe` (Inno Setup)
- [ ] `docs/OWNER_GUIDE.md` included in the build/docs folder
- [ ] `docs/RUNNING.md` and this checklist kept with the developer source

## Build status (this workspace)

- PyInstaller onedir build: completed (dist\RentalsManager\RentalsManager.exe).
- Inno Setup installer: generated (dist\RentalsManager-Setup-1.0.0.exe, about 32 MB).
- A packaged-app smoke test started the local server and served the app from %RENTALS_DATA_DIR%; the clean-Windows-no-Python test remains to be done on a target machine.
- Full suite: 222 tests. Coverage: 92%. Theme contrast: 120/120 pairs.

- Local installer smoke test: silent install, launched packaged app, /setup/ returned 200, and silent uninstall removed the installed files. A clean Windows machine with no Python is still the final external check.

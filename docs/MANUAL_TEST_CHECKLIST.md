# Manual test checklist - Rentals Manager 1.1.0

Use this list to confirm the app works on your PC. Tick each box after checking the expected result. Test in order; later sections use data created earlier.

## 0. Test setup

- [ ] Choose a fresh data folder for a clean run:
  ```powershell
  $env:RENTALS_DATA_DIR = "$env:TEMP\rentals-manual"
  ```
- [ ] Run migrations and demo data:
  ```powershell
  python manage.py migrate
  python manage.py seed_demo
  ```
  Expected: 40 units, 40 tenants, 40 leases, 480 invoices, 320 payments, 24 expenses.
- [ ] Start the app:
  ```powershell
  python launcher.py
  ```
- [ ] Alternatively use `python manage.py runserver` for browser testing.

To return to the normal development database later:
```powershell
Remove-Item Env:RENTALS_DATA_DIR
```

## 1. First-run setup and login

- [ ] With no users in the fresh folder, opening the app shows the setup wizard, not the login form.
- [ ] Enter company name, address, phone/email, KRA PIN, logo, backup folder, owner username, display name, password, palette and brand colour.
- [ ] Submit; setup completes and shows a one-time recovery code.
- [ ] Save the recovery code somewhere.
- [ ] Click Continue and sign in with the owner account.
- [ ] Sign out and sign back in.
- [ ] Confirm opening `/setup/` again redirects to the login screen.

## 2. Shell, themes and appearance

- [ ] Sidebar shows Dashboard, Units, Tenants, Billing, Payments, Maintenance, Expenses, Reports, Settings.
- [ ] Top bar has search, Record payment, and the user menu.
- [ ] Open Appearance.
- [ ] Switch Light, Dark, Match Windows.
- [ ] Try all five palettes: Ocean, Forest, Sunset, Slate, Plum.
- [ ] Try Comfortable and Compact density.
- [ ] Try Small, Medium and Large text.
- [ ] Confirm the live preview changes immediately.
- [ ] Save, reload, and confirm the choice is remembered.
- [ ] Set a brand colour in Settings; confirm the accent changes while status colours still mean the same.
- [ ] Check dashboard charts redraw after a theme change.
- [ ] Confirm PDF reports and invoices remain light/print-safe in dark mode.

## 3. Settings, audit and security

- [ ] Settings → change company name; save; confirm the sidebar/top bar updates.
- [ ] Confirm VAT is off by default and leave it off (VAT is not yet introduced).
- [ ] Set the flat service charge amount (default 500.00); save.
- [ ] Change invoice/receipt prefixes, separator and padding; save.
- [ ] Change due day, renewal alert days, backup folder and reminder template; save.
- [ ] Open Activity log; confirm the settings update appears with user, time and changed fields.
- [ ] Set auto-lock to 1 minute in Settings → Security.
- [ ] Wait idle; confirm the app locks to the login screen and asks for the password again.
- [ ] Sign back in.
- [ ] Confirm Audit entries cannot be edited or deleted from the UI.

## 4. Units, buildings and floors

- [ ] Units → Table view shows unit, floor, size, tenant, rent and status.
- [ ] Switch to Floor grid; confirm one block per floor and coloured unit tiles.
- [ ] Filter by search, building, floor and status; clear filters.
- [ ] Include archived units; confirm the option works.
- [ ] Buildings & floors → create a building and two floors.
- [ ] Try deleting a building/floor that has units; confirm it is blocked.
- [ ] Create a unit; confirm it appears as Vacant.
- [ ] Edit a unit, change rent/size/notes; confirm changes.
- [ ] Archive an unleased unit; confirm it disappears by default and can be restored.
- [ ] Try archiving an occupied unit; confirm it is blocked.

## 5. Tenants, contacts, documents and leases

- [ ] Create a tenant with business name, trade, KRA/ID, permit, VAT and withholding flags, primary unit and notes.
- [ ] Open the tenant profile; check every tab: Overview, Lease, Statement, Payments, Documents, Notes.
- [ ] Add two contacts; mark one primary; confirm only one is primary.
- [ ] Upload a permit/ID/lease document; open it; delete it.
- [ ] Edit the tenant and archive/restore the tenant (blocked while an active lease exists).
- [ ] Create a lease with dates, rent, deposit and no escalation.
- [ ] Confirm the lease automatically shows a flat monthly KES 500 service charge covering water, electricity, security and toilet.
- [ ] Confirm the unit becomes Occupied and the tenant primary unit is set.
- [ ] Create a second active lease on the same unit with overlapping dates; confirm it is rejected.
- [ ] Edit the lease rent; confirm a manual rent-history entry is created.
- [ ] Create a lease with percentage escalation but leave interval/date blank; confirm it defaults to 24 months and saves.
- [ ] Terminate a lease; confirm the unit becomes Vacant, the lease shows Terminated and the reason is kept.
- [ ] Confirm the lease Status history shows audit entries.

## 6. Excel import

- [ ] Open Import data; download the template.
- [ ] Confirm the template has ReadMe, Buildings, Floors, Units, Tenants and Leases sheets.
- [ ] Import the generated `backups/sample-40.xlsx` if available, or fill a small workbook.
- [ ] Confirm counts on the Import complete summary.
- [ ] Confirm imported units exist and active leases show Occupied.
- [ ] Upload a workbook with a duplicate unit code; confirm row errors are shown and nothing is imported.
- [ ] Upload a corrupt/non-xlsx file; confirm a plain error and no data change.
- [ ] Confirm opening balances are not part of this import (later phase limitation).

## 7. Billing

- [ ] Create a charge type, e.g. Garbage, with VAT applicable on/off.
- [ ] Create a utility type, e.g. Water, rate 50 per m3.
- [ ] Add a meter reading, then a second reading; confirm previous value and consumption calculate.
- [ ] Try a lower second reading; confirm it is rejected.
- [ ] Open Billing; choose the current month and due date; preview.
- [ ] Confirm one row per eligible active lease, rent, other, total and skipped count.
- [ ] Confirm a due escalation shows a rent-increase note.
- [ ] Generate selected invoices; confirm invoice numbers like `INV-A01-0001`.
- [ ] Generate the same period again; confirm no duplicates and skipped count increases.
- [ ] Open Invoices; filter by period/tenant/status; open an invoice.
- [ ] Print an invoice PDF; check logo/letterhead/lines/VAT/totals.
- [ ] Print all invoices for the period as one PDF.
- [ ] Confirm new leases already have the flat KES 500 service charge; water/electricity are not metered.
- [ ] With VAT off (default), confirm invoices show no VAT amounts/lines.
- [ ] Confirm existing invoices are unchanged when settings change.
- [ ] Add a monthly lease charge; generate; confirm prorated line.
- [ ] Add a quarterly and a once charge; confirm they bill only when due.
- [ ] Add unbilled meter readings; generate; confirm utility lines and readings become billed/locked.
- [ ] Confirm editing a billed meter reading is blocked.
- [ ] Run `python manage.py generate_invoices --period YYYY-MM --dry-run`; confirm counts without writing.
- [ ] Run it without `--dry-run`; confirm idempotent behaviour.

## 8. Payments, receipts and credit

- [ ] Record payment from the top bar, dashboard, tenant and invoice screens.
- [ ] Confirm the tenant/amount prefill where applicable.
- [ ] Select tenant, amount/date/reference; confirm the method is Bank deposit only and the allocation preview pays oldest invoice first.
- [ ] Confirm M-Pesa, Cash and Cheque are not offered when recording a payment.
- [ ] Edit an allocation manually; save; confirm the override is used.
- [ ] Save an exact payment; confirm the invoice is Paid and the receipt number is per unit.
- [ ] Record a partial payment; confirm Partial/Overdue status and reduced balance.
- [ ] Record a payment with no open invoices; confirm it becomes tenant credit.
- [ ] Record an overpayment; confirm credit appears and is applied automatically to the next generated invoice.
- [ ] Record a multi-invoice payment; confirm oldest-first allocation.
- [ ] Test cash + withholding; confirm the invoice settles and the receipt shows both amounts.
- [ ] Open the receipt A4 PDF and thermal receipt download.
- [ ] Record a cheque; mark it banked; then bounced; confirm the payment is Void and invoice balances restore.
- [ ] Void a cash payment; confirm balances restore and Activity log records the void.
- [ ] Tenant Statement and Payments tabs show the receipts and running balance.
- [ ] Invoice detail shows paid, balance, payment status and allocation history.

## 9. Statement import

- [ ] Payments → Import statement; upload an M-Pesa CSV, e.g.:
  ```
  Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
  QK81ABC,2026-11-03 10:00:00,INV-A01-0001 MAMA MBOGA 254700000001,Completed,1000.00,,5000.00
  QK82DEF,2026-11-04 11:00:00,UNKNOWN PAYER,Completed,500.00,,4500.00
  ```
- [ ] Confirm rows are imported but no payment is posted yet.
- [ ] Confirm the first row suggests a tenant/invoice.
- [ ] Click Confirm; confirm a payment appears and the row is Confirmed.
- [ ] Try Confirm on the unmatched row without picking a tenant; confirm it is blocked.
- [ ] Pick a tenant and confirm the unmatched row.
- [ ] Ignore a row; confirm it is Ignored and never posted.
- [ ] Confirm the import becomes Completed when all rows are resolved.
- [ ] Upload a bank CSV with Date, Description, Amount, Reference; confirm matching/confirmation.

## 10. Deposits and move-out

- [ ] Lease → Deposits; record the deposit actually received.
- [ ] Lease → Move out; choose dates; enter final meter readings if utilities exist; plan it.
- [ ] Confirm the checklist has Door, Shutter, Lights, Floor and Meter.
- [ ] Mark an item damaged with a cost; save; confirm damages and refund recalculate.
- [ ] Confirm deposit held, arrears at exit (tenant total balance), damages and refund due.
- [ ] Try planning a second move-out for the same lease; confirm it is blocked.
- [ ] Print the settlement PDF.
- [ ] Confirm refund; confirm the deposit status updates, lease terminates and unit becomes Vacant.
- [ ] Reopen the move-out; confirm the settlement snapshot did not change.

## 11. Prospects, maintenance and expenses

- [ ] Prospects page shows vacant units.
- [ ] Create a prospect with follow-up date and interested unit; overdue follow-up is highlighted.
- [ ] Convert the prospect to a lease; confirm tenant/contact/lease are created and the unit becomes Occupied.
- [ ] Create a maintenance request with priority/status/cost.
- [ ] From maintenance, Create expense; save; confirm the expense links back and the request becomes Done.
- [ ] Create an expense category; create an expense with payee, method and reference.
- [ ] Upload a receipt to the expense; open and delete it.
- [ ] Disable an expense category; confirm it is disabled rather than deleted.

## 12. Dashboard and reports

- [ ] Dashboard Rent due matches issued invoices for the current month.
- [ ] Collected matches posted payments received this month (cash + withholding).
- [ ] Arrears matches overdue invoice balances only.
- [ ] Occupied matches active occupied units over all active units.
- [ ] Income vs expenses chart uses collected payments and expenses for six months.
- [ ] Arrears by age buckets match overdue invoice ages.
- [ ] Needs-attention counts and View list links work.
- [ ] Reports → Arrears: set as-of date, check buckets, export Excel and PDF.
- [ ] Reports → Income and expenses: filter dates, export Excel and PDF.
- [ ] Reports → Occupancy: filter building, export both formats.
- [ ] Reports → Tenant statement: choose tenant/date range, compare closing balance with tenant profile, export.
- [ ] Reports → Tax summary: check rent billed, VAT charged, withholding deducted; export.
- [ ] Overdue reminders: counts/balances, WhatsApp opens prefilled message from Settings, Call uses `tel:`.
- [ ] Change reminder template in Settings and reload reminders; confirm the new message.
- [ ] Confirm report PDFs open and are readable.

## 13. Backup, restore and help

- [ ] Dashboard shows a backup warning when no backup exists or the folder is missing/stale.
- [ ] Backup & restore → Back up now; confirm OK row and file in the folder.
- [ ] Configure a missing USB folder; confirm warning and failed backup logging.
- [ ] Help & Support shows version, folder, last backup and recovery status.
- [ ] Open data folder button opens `%LOCALAPPDATA%\RentalsManager` (or configured folder).
- [ ] Export support bundle; confirm zip contains version/log only, no database or business data.
- [ ] Restore drill with the app closed:
  ```powershell
  python manage.py restore_backup "<latest backup.sqlite3>" --yes
  ```
  Expected: safety backup, restored data, restore audit entry.
- [ ] Change owner password and sign in again.
- [ ] Run `python manage.py reset_password`, use the recovery code, set a new password, and sign in.

## 14. Installer and window

- [ ] Build/obtain `dist\RentalsManager-Setup-1.1.0.exe`.
- [ ] Install on a clean Windows machine with no Python.
- [ ] Confirm desktop and Start menu shortcuts exist.
- [ ] Launch; complete first-run setup.
- [ ] Confirm data is written to `%LOCALAPPDATA%\RentalsManager`, not the install folder.
- [ ] Close/relaunch; owner and data remain.
- [ ] Uninstall; confirm app files are removed and business data remains.
- [ ] Reinstall; confirm the existing data is still there.
- [ ] Confirm the app works fully offline (network cable disabled).

## 15. Automated checks

- [ ] `pytest` passes (222 tests).
- [ ] `python manage.py check` reports no issues.
- [ ] `python manage.py makemigrations --check --dry-run` reports no changes.
- [ ] `python manage.py check_theme_contrast` passes all 120 pairs.
- [ ] Coverage command runs and reports about 92%.
- [ ] `node --check static/js/app.js`, `theme.js`, `payments.js`, `dashboard.js` pass.

## Known limitations (expected, not failures)

- Invoice voiding/recalculation UI is not implemented.
- Thermal receipts are raw ESC/POS downloads; no printer selection inside the app.
- Opening balances are not imported.
- Arrears as-of uses current balances, not a historical replay.
- Occupancy and dashboard are current snapshots.
- Planned move-outs cannot be cancelled; they can be edited or settled.
- Deposit refunds do not create a separate cash-refund ledger entry.
- Support bundles include logs; they contain no database/business records.

## Notes

Record any failure with:
- screen/page,
- what you clicked,
- expected result,
- actual result,
- screenshot or support bundle if available.

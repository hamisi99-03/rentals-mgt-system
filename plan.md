You are a senior Django engineer. Build an offline desktop application for managing a commercial building of 20 to 100 shop units rented to business tenants. Work in strict phases. After each phase: run all tests, fix failures, commit with a clear message, summarize what was built, list any deviations from the docs/ files, give me a short manual test script for the UI, then STOP and wait for me to say "continue".

## Design sources (follow these, do not improvise)
- The database must follow docs/SCHEMA.md: same tables, field names, statuses and constraints. If you think a change is needed, propose it and wait for my approval.
- Every screen must follow docs/WIREFRAMES.md for layout and content. Screens not sketched there reuse the same shell, tables, dialogs and components.
- Theming must follow docs/THEMES.md.
- At the start of each phase, state which parts of these three files that phase implements.

## Context
- Users: building owner and property manager. Both roles have IDENTICAL access. Password login.
- Runs on ONE Windows PC, fully offline. No cloud services.
- Landlord side: I rent shop units to business tenants. Kenya (currency KES, M-Pesa, KRA).
- Dashboard-first UI. No fixed deadline, so prioritize correctness over speed.

## Tech stack
- Python 3.12, Django, SQLite, pywebview desktop shell, PyInstaller installer.
- Chart.js (charts), WeasyPrint or ReportLab (PDF), openpyxl (Excel), python-escpos (thermal receipts).
- pytest + pytest-django. Virtual environment and requirements file.

## Non-negotiable rules
1. All money is Decimal (DecimalField, 2 places). Never float.
2. Balances are DERIVED from invoices, payments and allocations (a ledger). Never editable by hand.
3. Tax rates, thresholds, numbering formats and message templates live in a Settings model, never in code.
4. 4. Every create, update and delete of business data writes an AuditLog entry (time, model, object, before/after). The log is visible to the owner and cannot be edited or deleted from the UI.
5. Deposits are a liability held for the tenant, not income.
6. Destructive actions need confirmation. Records with history are archived or voided, never hard-deleted.
7. Every phase ships with tests. Billing and payment allocation need especially thorough tests (write them first).
8. No hardcoded colours in templates or CSS outside the theme stylesheet. Use theme variables only.

## Settled decisions (these override anything else)
- VAT: do NOT assume the landlord is VAT-registered. Settings has a master "VAT enabled" switch (default OFF) and a VAT rate (default 16%). A per-tenant "VAT applicable" flag only takes effect when the master switch is ON. When OFF, invoices show no VAT lines. Changing the switch affects only invoices generated afterwards; existing invoices are never recalculated.
- Escalation: no global default. Each lease has an optional rule: type (none / percentage / fixed amount), value, interval in months, next escalation date. A lease with no rule never escalates. When an invoice period starts on or after the next escalation date, apply the new rent and record the change in the lease history.
- Numbering: invoices and receipts use {PREFIX}-{UNITCODE}-{SEQ:04d}, e.g. INV-A12-0001 and RCT-A12-0001. The sequence is per unit and per document type, never reused (voided numbers stay in the log). Prefix, separator and padding are editable in Settings. If a document spans several units, use the tenant's primary unit.
- Permissions: Owner and Manager have identical access to every screen and action. Keep the role field and one central permission-check function so access can be restricted later.
- Withholding tax: per-tenant flag and a rate in Settings (suggested starting value 10%, to be confirmed with my accountant). Applied only when the flag is set. Recorded on payments with an optional certificate number.
- Tenants are NOT notified by the app (no SMS or email in v1). Overdue follow-up is a manual list with click-to-chat (WhatsApp link) and call buttons.
- Themes: mode (light/dark/match Windows), five palettes (Ocean default, Forest, Sunset, Slate, Plum), density, text size, optional company brand colour, saved per user. PDFs always use a fixed print-safe light style. Details in docs/THEMES.md.

## PHASE 1: Foundation
1. Create the Django project and apps (core, property, billing, payments, operations, reports) with a clean structure.
2. Custom user with roles Owner and Manager (identical permissions via one central check) and the theme fields from docs/SCHEMA.md; login/logout.
3. Settings model and screen: company name, logo, letterhead text, VAT switch and rate, withholding rate, numbering formats, backup folder, reminder message template, default palette, brand colour.
4. AuditLog via mixin or signals.
5. Backup: management command copying the SQLite database and uploaded files to the configured USB/external folder with a timestamp, run on app exit and daily; plus a restore command.
6. Theme system from docs/THEMES.md: theme stylesheet with CSS variables, mode/palette/density/text-size switching without reload, brand colour override, contrast-check script, and the Appearance screen with live preview.
7. Base layout from docs/WIREFRAMES.md: left sidebar (Dashboard, Units, Tenants, Billing, Payments, Maintenance, Expenses, Reports, Settings), top bar with search and user menu, reusable table, form, dialog, metric-card and empty-state components, all using theme variables only.
8. pywebview launcher that starts Django locally and opens the window.
Acceptance: log in as each role, change a setting, switch every palette in light and dark, see an audit entry, run a backup and a restore.

## PHASE 2: Property core
1. CRUD for Building, Floor, Unit with filters and search; Units screen with table and floor-grid views as in the wireframe.
2. Tenant CRUD with multiple contacts and document upload (lease, ID copies, permit); tenant profile with tabs as in the wireframe.
3. Lease CRUD with dates, rent, deposit, escalation rule, renewal alert date, status history. Prevent overlapping active leases on one unit.
4. Excel import for existing tenants, units, leases and opening balances: template download, row-level validation, error report before anything is committed.
Acceptance: import 40 sample units and tenants, create leases, unit status updates automatically.

## PHASE 3: Billing engine (most critical)
1. ChargeType and LeaseCharge as in docs/SCHEMA.md.
2. Monthly invoice generation (command + the billing run screen from the wireframe): one invoice per active lease, lines per charge, idempotent (running twice never duplicates), correct proration for mid-month lease start/end.
3. Escalation applied per the settled rule.
4. VAT per the settled rule; withholding flag recorded on tenant for use at payment time.
5. Document numbering per the settled format using NumberSequence (atomic, no gaps or reuse).
6. Invoice PDF with logo and letterhead in the fixed print-safe style.
7. Meter readings per unit; utility lines computed as (current minus previous) times rate.
Acceptance: tests for escalation dates, proration, VAT on and off, numbering uniqueness, idempotency.

## PHASE 4: Payments
1. Record payment dialog exactly as in the wireframe, reachable from anywhere, with the allocation preview.
2. Auto-allocate oldest invoice first; allow manual override; overpayment goes to credit (CreditEntry) and is applied to the next invoice automatically.
3. Cheque lifecycle: received, banked, bounced (a bounce reverses allocations and is audited).
4. Withholding tax recorded on the payment with optional certificate number.
5. Receipts: A4 PDF and thermal (ESC/POS) with logo, using the settled numbering.
6. Statement import screen as in the wireframe: upload M-Pesa or bank CSV, suggest matches, require my confirmation, never auto-post unmatched rows.
Acceptance: tests for partial, advance, exact and multi-invoice payments, bounced cheque reversal, import matching.

## PHASE 5: Operations
1. Deposits held as liability; move-out screen as in the wireframe (checklist, final meter readings, refund calculation, printable settlement).
2. Vacancies and prospects: vacant list, prospect records, follow-up dates, convert a prospect to a lease.
3. Maintenance requests per unit (status, cost, notes) that can create an Expense.
4. Expenses by category with receipt attachment.
Acceptance: complete a full lifecycle: prospect, lease, invoices, payments, move-out, refund.

## PHASE 6: Reports and dashboard
1. Dashboard exactly as in the wireframe: metric cards, income vs expense chart, arrears by age, needs-attention panel; charts follow the active theme.
2. Reports: arrears, monthly income and expense, occupancy and vacancy, tenant statement, tax summary (rent billed, VAT charged, withholding deducted). Filter by date; export to Excel and PDF.
3. Overdue reminder list with click-to-chat and call buttons, using the message template from Settings.
Acceptance: dashboard numbers reconcile exactly with the ledger.

## PHASE 7: Hardening and delivery
1. Seed script: 40 units, tenants, 12 months of invoices and payments.
2. Full test suite with coverage report; close gaps in billing and allocation. Re-run the theme contrast check for all palettes.
3. Performance check on 12 months of data; add indexes from docs/SCHEMA.md where needed.
4. PyInstaller Windows installer and a first-run wizard (company details, backup folder, create the first user, choose palette).
5. User guide (screens, month-end routine, backup and restore, changing themes) and developer README.
6. Final checklist: restore-from-backup drill, month-end reconciliation steps, list of every deviation from docs/ files, known limitations.

## Working protocol
- Before each phase, list what you will build and any assumption you are making. Ask me before deciding anything that affects money calculations.
- Tests first for billing and allocation logic.
- Small functions, clear names, no duplicated logic.
- Never invent tax rates; read them from Settings and use clearly labeled placeholder values in seed data.

Start with PHASE 1 now.
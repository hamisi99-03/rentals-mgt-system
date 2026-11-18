# Rentals Manager - Owner Guide

Rentals Manager keeps the rent, payments, tenants and building records on this PC. It is fully offline. There is one owner account, and the data stays in your Windows user folder.

## First start

1. Install Rentals Manager and open it from the desktop shortcut or Start menu.
2. The first-time setup asks for the company name, contact details, logo, backup drive and owner password. It also chooses a theme.
3. The setup shows a **recovery code once**. Write it down and keep it with the company records. It is the only way to reset the owner password without technical help.
4. Sign in with the owner username and password.

## The dashboard

The dashboard shows:

- **Rent due** - what was billed for the current month.
- **Collected** - payments received this month, including tax withheld.
- **Arrears** - overdue balances only.
- **Occupied** - units with an active lease.
- The income and expense chart for the last six months.
- Arrears by age and the **Needs attention** list.

If the backup folder is missing or the last backup is over seven days old, a warning appears on the dashboard.

## Building, units, tenants and leases

- **Units** - add buildings and floors, then units. Use the table or floor grid. Unit status follows the active lease; use Reserved for a unit held for a prospect.
- **Tenants** - add the business, contacts and documents. The profile tabs show contacts, leases, statements, payments, documents and notes.
- **Leases** - a lease has a unit, tenant, dates, rent, deposit and optional escalation. Only one active lease may overlap a unit.
- **Prospects** - keep follow-up dates for interested businesses. Convert a prospect to a lease in one step.

## Billing

1. Open **Billing** and choose the month and due date.
2. Preview the invoices. The oldest invoice is not relevant here; the preview is one row per active lease.
3. Check any rent-increase notes and the skipped count, then generate.
4. Running the same month again never duplicates an invoice.
5. Open **Invoices** to view, print or print all invoices for a period.

VAT is off by default. Turn it on in Settings only when the owner is VAT-registered. Existing invoices never change when settings change.

## Payments and receipts

- Use **Record payment** from the top bar or a tenant/invoice screen.
- The allocation preview pays the oldest invoice first. You can edit the amounts.
- Cash plus tax withheld settle the invoice. Any extra becomes tenant credit and is used automatically on the next invoice.
- Cheques can be marked banked or bounced. A bounce reverses the payment and restores the invoice balances.
- Each payment has an A4 receipt and a thermal ESC/POS receipt.

## Deposits and move-outs

- Record deposits actually received on the lease page.
- Plan a move-out from the lease or tenant page, complete the checklist, enter final meter readings, review the refund and print the settlement.
- Confirming the refund settles the deposit, ends the lease and frees the unit. If arrears and damages exceed the deposit, the remaining tenant balance stays outstanding.

## Maintenance and expenses

- **Maintenance** tracks requests per unit. A request can create an expense and mark itself done.
- **Expenses** records spending by category. Attach a receipt photo or PDF to each expense.

## Reports

Reports include arrears, monthly income and expenses, occupancy, tenant statements and a tax summary. Every report can be exported to Excel or PDF.

**Overdue reminders** shows one row per tenant with an overdue balance. Use the WhatsApp or Call button when the contact has a phone number. The WhatsApp message uses the template in Settings.

## Month-end routine

1. Record every payment and import the M-Pesa or bank statement. Confirm each suggested row; never post an unmatched row by accident.
2. Enter the meter readings.
3. Run Billing for the month. Check the preview and skipped count.
4. Print or save the invoices and receipts you need.
5. Review the Dashboard and Reports.
6. Run a backup and confirm it appears in Backup history.

## Backups and restore

- The app backs up automatically on exit and daily.
- **Settings > Backup > Back up now** runs an immediate backup. Copy the backup folder to a USB drive or keep the configured external folder connected.
- To restore, ask your technical contact to run the restore command with the app closed. The restore takes a safety backup first.

## Themes and appearance

Open **Appearance** from the user menu or Settings. Choose light, dark or Match Windows; choose a palette, density and text size. The company brand colour is set in Settings. PDF reports always print in a clean light style.

## Help and support

**Help & Support** shows the app version, last backup, data folder and a month-end routine. It can open the data folder and export a support bundle containing the app version and log file. The support bundle never includes tenants, invoices or payments.

If the app will not start, keep the data folder and latest backup safe, then export a support bundle for your technical contact. Full technical details are written to the log file in the data folder; the app only shows plain-language messages.

## Data location

In the installed app the data lives in:

`%LOCALAPPDATA%\RentalsManager`

It contains the database, uploaded documents, backups and logs. Reinstalling or updating the app does not touch this folder.

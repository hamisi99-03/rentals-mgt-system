About 35 tables in SQLite through the Django ORM. Conventions: every table has id, created_at, updated_at and created_by (User). Money is DECIMAL(12,2). Status fields are fixed lists, shown in brackets. Balances, amounts paid and arrears are never stored; they are computed from invoices, allocations and credit entries.
Core and settings
• User: username (unique), password_hash, full_name, phone, auto_lock_minutes (default 15), last_login, theme_mode [light, dark, system], theme_palette [ocean, forest, sunset, slate, plum], theme_density [comfortable, compact], theme_text_size [small, medium, large].
• Settings (one row): company_name, address, phone, email, kra_pin, logo, letterhead_text, currency (KES), service_charge_amount (default 500.00), vat_enabled (default false), vat_rate (default 16.00), withholding_rate, invoice_prefix (INV), receipt_prefix (RCT), number_separator, number_padding (4), invoice_due_day, renewal_alert_days (60), backup_folder, reminder_template, default_palette, brand_color (optional hex).
• NumberSequence: doc_type [invoice, receipt], unit (FK), last_value. Unique on (doc_type, unit). Incremented inside a database transaction so numbers are never reused.
• AuditLog (append-only): timestamp, user, action [create, update, delete, void, login, backup, restore], model, object_id, object_repr, changes (JSON before/after).
• BackupLog: timestamp, destination_path, size_bytes, result [ok, failed], message.
Property
• Building: name, address, notes.
• Floor: building (FK), name, sort_order.
• Unit: building (FK), floor (FK), code (unique, e.g. A12), size_sqm, base_rent, status [vacant, occupied, reserved], notes, is_active.
• UtilityType: name (water, electricity, garbage), measure (m3, kWh), rate_per_unit, is_active.
• MeterReading: unit (FK), utility_type (FK), reading_date, reading_value, previous_value, consumption (computed on save), invoice_line (nullable FK, set when billed). Unique on (unit, utility_type, reading_date).
Tenants and documents
• Tenant: business_name, trade, id_or_kra_pin, permit_number, vat_applicable, withholding_applicable, primary_unit (nullable FK), status [active, former], notes.
• TenantContact: tenant (FK), name, role_title, phone, email, is_primary.
• Document: owner_type and owner_id (generic link to Tenant, Lease, Expense, MaintenanceRequest or MoveOut), doc_type [lease, id_copy, permit, receipt, photo, other], file, uploaded_by, uploaded_at.
Leases and charges
• Lease: tenant (FK), unit (FK), agreement_type [lease, monthly], start_date, end_date (blank for an open-ended monthly rental), monthly_rent, deposit_amount, escalation_type [none, percent, fixed], escalation_value, escalation_interval_months (defaults to 24 when a rule is enabled), next_escalation_date, status [draft, active, expired, terminated], terminated_on, termination_reason, notes.
• LeaseRentHistory: lease (FK), effective_date, old_rent, new_rent, reason [initial, escalation, manual], changed_by.
• ChargeType: name, kind [service, utility, other], vat_applicable, is_active. Rent comes from the lease itself. A default "Service charge (water, electricity, security, toilet)" type is attached to every new lease at the Settings amount (500.00 by default), as a flat monthly charge regardless of use.
• LeaseCharge: lease (FK), charge_type (FK), amount, frequency [monthly, quarterly, once], start_date, end_date, is_active.
Billing
• Invoice: invoice_number (unique), tenant (FK), lease (FK), unit (FK), period_start, period_end, issue_date, due_date, subtotal, vat_amount, total, vat_enabled_snapshot, vat_rate_snapshot, status [issued, void], void_reason, voided_by, voided_at. Unique on (lease, period_start), which makes generation idempotent.
• InvoiceLine: invoice (FK), kind [rent, service, utility, other], charge_type (nullable FK), description, quantity, unit_price, amount, vat_amount.
Payments and credit
• Payment: receipt_number (unique), tenant (FK), date_received, method [mpesa, bank, cash, cheque] (new payments are bank deposit only; older values remain readable), amount, reference, cheque_number, cheque_bank, cheque_status [received, banked, bounced], withholding_amount, withholding_cert_no, status [posted, void], notes, statement_row (nullable FK), recorded_by.
• PaymentAllocation: payment (FK), invoice (FK), amount, allocated_at, is_auto.
• CreditEntry: tenant (FK), entry_date, amount (positive adds credit, negative uses it), source [overpayment, applied_to_invoice, refund], payment (nullable FK), invoice (nullable FK).
• StatementImport: source [mpesa, bank] (the import screen accepts bank statements only), file, uploaded_at, uploaded_by, status [pending, completed].
• StatementRow: import (FK), tx_date, amount, reference, payer_name, phone, suggested_tenant (nullable FK), suggested_invoice (nullable FK), match_status [unmatched, suggested, confirmed, ignored], payment (nullable FK).
Deposits and move-out
• Deposit: lease (FK), amount_received, received_date, payment (nullable FK), status [held, partly_refunded, refunded, forfeited].
• MoveOut: lease (FK), notice_date, move_out_date, arrears_at_exit, damages_amount, deposit_held, refund_amount, status [planned, settled], settlement_notes.
• MoveOutItem: move_out (FK), item (door, shutter, lights, floor, meter), condition, damage_cost, notes.
Operations
• Prospect: name, business, phone, email, interested_unit (nullable FK), status [new, viewing, negotiating, converted, lost], follow_up_date, notes, converted_lease (nullable FK).
• MaintenanceRequest: unit (FK), tenant (nullable FK), title, description, priority [low, normal, urgent], status [open, in_progress, done], reported_date, completed_date, cost, expense (nullable FK).
• ExpenseCategory: name, is_active.
• Expense: category (FK), expense_date, amount, payee, description, payment_method, reference, maintenance_request (nullable FK).
Computed, never stored
• Invoice amount paid and balance = sum of its allocations.
• Invoice payment status [unpaid, partial, paid, overdue] from balance and due date.
• Tenant balance = invoices minus allocations, with credit balance = sum of CreditEntry.
• Arrears ageing buckets 0-30, 31-60, 61-90, 90+ days from due date.
• Unit status follows the active lease (occupied) or its absence (vacant).
Rules and indexes
• No two leases on one unit may overlap in dates while active (checked in the service layer and a test).
• Voiding an invoice or payment reverses its allocations and writes an audit entry; nothing financial is hard-deleted.
• A bounced cheque sets the payment to void for allocation purposes and restores the invoice balances.
• Indexes: Invoice (tenant, due_date), Invoice (status), Payment (tenant, date_received), PaymentAllocation (invoice), Lease (unit, status), Lease (end_date), AuditLog (timestamp), StatementRow (match_status).
The app is built for the owner as its only user. This replaces the earlier owner-and-manager decision wherever the two disagree.
Removed
• The manager role, the role field and every role-based permission check.
• Any screen, setting or report that exists only to supervise another person.
• Multi-user account management (no user list, no invites, no per-user permissions).
Kept, now owner-first
• Login: one password-protected owner account, to keep rent and tenant data private on the PC. It locks automatically after a period of inactivity (default 15 minutes, set in Settings) and asks for the password again.
• Activity log: stays as a history of what changed and when, useful for tracing mistakes and for the accountant. It is append-only.
• Themes: stored on the single owner account, with the same options as section 13.
• Everything else in sections 3 to 12 is unchanged. Every screen is designed around the owner's questions: what is due, what has been paid, who is late, what do I owe in tax, and what is vacant.
Updated rules for the build
1.  One user row. The first-run wizard creates the owner account and there is no sign-up screen afterwards.
2.  Password reset is done by a local recovery step (a recovery code shown once at setup), because there is no admin to reset it.
3.  Audit entries do not need a user column beyond the single owner, but keep the field so a second user could be added later without a data migration.
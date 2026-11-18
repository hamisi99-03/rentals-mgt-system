Text wireframes with sample figures. They show layout and content, not final styling. Every screen sits inside the same shell: left sidebar, top bar with search and user menu, and a content area.
12.1 Dashboard
+------------------------------------------------------------------------+
| [Logo] Rental Manager       [ Search tenants, units, invoices... ] [User v]|
+---------------+--------------------------------------------------------+
| > Dashboard   |  November 2026                         [+ Record payment]|
|   Units       |                                                        |
|   Tenants     |  +-----------+ +-----------+ +-----------+ +---------+ |
|   Billing     |  | Rent due  | | Collected | | Arrears   | | Occupied| |
|   Payments    |  | 842,000   | | 610,500   | | 231,500   | | 36 / 40 | |
|   Maintenance |  +-----------+ +-----------+ +-----------+ +---------+ |
|   Expenses    |                                                        |
|   Reports     |  Income vs expenses (6 months)   Arrears by age        |
|   Settings    |  [ bar chart ]                   [ 0-30 31-60 61-90 90+]|
|               |                                                        |
|               |  Needs attention                                       |
|               |  - Overdue tenants (7)                    [View list]  |
|               |  - Leases ending in 60 days (3)           [View list]  |
|               |  - Rent increases due this month (2)      [View list]  |
|               |  - Open maintenance requests (4)          [View list]  |
+---------------+--------------------------------------------------------+
12.2 Units
 Units                                         [Table | Floor grid] [+ Unit]
 [ Search ]  Floor [All v]  Status [All v]
 +------+-------+-------+----------------+----------+------------+
 | Unit | Floor | Size  | Tenant         | Rent     | Status     |
 +------+-------+-------+----------------+----------+------------+
 | A01  | Gnd   | 24 m2 | Mama Mboga Ltd | 25,000   | Occupied   |
 | A02  | Gnd   | 18 m2 | -              | 20,000   | Vacant     |
 | B07  | 1st   | 30 m2 | Salon Bella    | 32,000   | Occupied   |
 +------+-------+-------+----------------+----------+------------+
 Floor grid view: one row per floor, a coloured box per unit
 (green occupied, grey vacant, amber reserved), click opens the unit.
12.3 Tenant profile
 < Tenants     Salon Bella                       [Edit] [Record payment]
 Unit B07 - Lease 01 Mar 2026 to 28 Feb 2027 - Rent 32,000 - Active
 +--------------------------------------------------------------------+
 | Balance due 32,000 | Credit 0 | Deposit held 64,000 | Next rent +5% |
 +--------------------------------------------------------------------+
 [Overview] [Lease] [Statement] [Payments] [Documents] [Notes]

 Statement
 +----------+--------------+-----------+----------+-----------+
 | Date     | Description  | Charged   | Paid     | Balance   |
 +----------+--------------+-----------+----------+-----------+
 | 01 Nov   | INV-B07-0009 | 32,000    |          | 32,000    |
 | 05 Oct   | RCT-B07-0008 |           | 32,000   | 0         |
 +----------+--------------+-----------+----------+-----------+
                                [Print statement] [Export PDF/Excel]
12.4 Record payment dialog
 +--------------- Record payment ---------------+
 | Tenant   [ Salon Bella - B07 v ]            |
 | Method   ( ) M-Pesa ( ) Bank ( ) Cash ( ) Cheque |
 | Amount   [ 40,000 ]   Date [ 17 Nov 2026 ]  |
 | Reference [ QWE123XYZ ]                     |
 | (cheque) Cheque no [ ]  Bank [ ]            |
 | [ ] Tenant withheld tax   Amount [ ] Cert [ ]|
 |                                             |
 | Allocation preview                          |
 |  INV-B07-0009   32,000 -> paid              |
 |  Credit carried forward   8,000             |
 |                                             |
 |            [Cancel]  [Save and print receipt]|
 +---------------------------------------------+
12.5 Monthly billing run
 Billing  >  Generate invoices
 Period [ December 2026 v ]   Due date [ 05 Dec 2026 ]
 +---+------+----------------+---------+--------+----------+
 | x | Unit | Tenant         | Rent    | Other  | Total    |
 +---+------+----------------+---------+--------+----------+
 | x | A01  | Mama Mboga Ltd | 25,000  | 1,500  | 26,500   |
 | x | B07  | Salon Bella    | 33,600* | 0      | 33,600   |
 +---+------+----------------+---------+--------+----------+
 * rent increase applied (5%)    Skipped: 0 already invoiced
                    [Cancel]  [Generate 36 invoices]  [Print all PDF]
12.6 Statement import and matching
 Payments > Import statement          File: mpesa_nov.csv   [Upload]
 +----------+--------+------------+--------------------+-----------+
 | Date     | Amount | Reference  | Suggested match    | Action    |
 +----------+--------+------------+--------------------+-----------+
 | 03 Nov   | 25,000 | QK81ABC    | A01 Mama Mboga     | [Confirm] |
 | 04 Nov   | 12,500 | QK82DEF    | (no match)         | [Pick...] |
 | 04 Nov   | 500    | QK82GHI    | Not rent           | [Ignore]  |
 +----------+--------+------------+--------------------+-----------+
 Unmatched rows are never posted without your confirmation.
12.7 Move-out and deposit settlement
 Move-out: Salon Bella (B07)       Move-out date [ 28 Feb 2027 ]
 Checklist  Door [OK v]  Shutter [Damaged v 3,000]  Lights [OK v]
            Final meter readings: water [ ]  electricity [ ]
 +------------------------------------------+
 | Deposit held                    64,000   |
 | Less arrears                         0   |
 | Less damages                     3,000   |
 | Refund due                      61,000   |
 +------------------------------------------+
                        [Print settlement]  [Confirm refund]
12.8 Remaining screens
Same shell and table patterns: Lease form, Tenant form, Unit form, Invoice detail, Receipt list, Meter readings, Prospects, Maintenance, Expenses, Reports hub with filters and export buttons, Overdue reminder list (call and WhatsApp buttons), Settings (company, tax, numbering, backup, templates), Activity log, Backup and restore.
"""Tatmaq Books - database schema, industry profiles and demo seeder."""
import os
import random
import secrets
import sqlite3
from datetime import date, timedelta

DB_PATH = os.environ.get("TATMAQ_DB", os.path.join(os.path.dirname(__file__), "tatmaq.db"))
TODAY = date.today()

# ----------------------------------------------------------------------------- schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies(
 id INTEGER PRIMARY KEY, name TEXT, industry TEXT, currency TEXT DEFAULT 'USD', symbol TEXT DEFAULT '$',
 tax_name TEXT DEFAULT 'VAT', tax_rate REAL DEFAULT 15, address TEXT, email TEXT, phone TEXT,
 fiscal_start TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS accounts(
 id INTEGER PRIMARY KEY, company_id INT, code TEXT, name TEXT, type TEXT, subtype TEXT,
 is_active INT DEFAULT 1);

CREATE TABLE IF NOT EXISTS contacts(
 id INTEGER PRIMARY KEY, company_id INT, type TEXT, name TEXT, company TEXT, email TEXT, phone TEXT,
 address TEXT, tax_no TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS items(
 id INTEGER PRIMARY KEY, company_id INT, name TEXT, sku TEXT, kind TEXT, unit TEXT,
 price REAL, cost REAL, tax_rate REAL, qty REAL DEFAULT 0, reorder REAL DEFAULT 0,
 tracked INT DEFAULT 1, account_id INT);

CREATE TABLE IF NOT EXISTS quotes(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, contact_id INT, date TEXT, expiry TEXT,
 status TEXT, subtotal REAL, tax REAL, total REAL, notes TEXT, invoice_id INT);

CREATE TABLE IF NOT EXISTS quote_lines(
 id INTEGER PRIMARY KEY, quote_id INT, item_id INT, description TEXT, qty REAL, unit_price REAL,
 tax_rate REAL, amount REAL);

CREATE TABLE IF NOT EXISTS invoices(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, contact_id INT, quote_id INT,
 date TEXT, due_date TEXT, status TEXT, subtotal REAL, tax REAL, total REAL,
 amount_paid REAL DEFAULT 0, notes TEXT, currency TEXT);

CREATE TABLE IF NOT EXISTS invoice_lines(
 id INTEGER PRIMARY KEY, invoice_id INT, item_id INT, description TEXT, qty REAL,
 unit_price REAL, tax_rate REAL, amount REAL, unit_cost REAL);

CREATE TABLE IF NOT EXISTS bills(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, vendor_id INT, date TEXT, due_date TEXT,
 status TEXT, subtotal REAL, tax REAL, total REAL, amount_paid REAL DEFAULT 0, notes TEXT);

CREATE TABLE IF NOT EXISTS bill_lines(
 id INTEGER PRIMARY KEY, bill_id INT, item_id INT, account_id INT, description TEXT,
 qty REAL, unit_cost REAL, tax_rate REAL, amount REAL);

CREATE TABLE IF NOT EXISTS payments(
 id INTEGER PRIMARY KEY, company_id INT, kind TEXT, contact_id INT, invoice_id INT, bill_id INT,
 date TEXT, amount REAL, method TEXT, bank_account_id INT, reference TEXT);

CREATE TABLE IF NOT EXISTS bank_accounts(
 id INTEGER PRIMARY KEY, company_id INT, name TEXT, account_id INT, number TEXT,
 opening_balance REAL, currency TEXT);

CREATE TABLE IF NOT EXISTS bank_txns(
 id INTEGER PRIMARY KEY, company_id INT, bank_account_id INT, date TEXT, description TEXT,
 reference TEXT, amount REAL, direction TEXT, status TEXT, source TEXT);

CREATE TABLE IF NOT EXISTS journal_entries(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, date TEXT, memo TEXT, source TEXT,
 reference TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS journal_lines(
 id INTEGER PRIMARY KEY, entry_id INT, account_id INT, description TEXT, debit REAL, credit REAL);

CREATE TABLE IF NOT EXISTS employees(
 id INTEGER PRIMARY KEY, company_id INT, name TEXT, position TEXT, department TEXT,
 gross REAL, start_date TEXT, paye_no TEXT, status TEXT);

CREATE TABLE IF NOT EXISTS payroll_runs(
 id INTEGER PRIMARY KEY, company_id INT, period TEXT, date TEXT, gross REAL, paye REAL,
 nssa REAL, net REAL, status TEXT);

CREATE TABLE IF NOT EXISTS payslips(
 id INTEGER PRIMARY KEY, run_id INT, employee_id INT, gross REAL, paye REAL, aids REAL,
 nssa REAL, net REAL);

CREATE TABLE IF NOT EXISTS fixed_assets(
 id INTEGER PRIMARY KEY, company_id INT, name TEXT, category TEXT, purchase_date TEXT,
 cost REAL, salvage REAL, life REAL, accum_dep REAL DEFAULT 0, last_dep TEXT,
 exp_account_id INT, accum_account_id INT, status TEXT, location TEXT);

CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, company_id INT, name TEXT, email TEXT, role TEXT, status TEXT,
 password_hash TEXT, last_login TEXT, created_at TEXT);

CREATE TABLE IF NOT EXISTS sessions_tbl(
 id INTEGER PRIMARY KEY, token TEXT, company_id INT, user_id INT, kind TEXT,
 created_at TEXT, expires_at TEXT, label TEXT);

CREATE TABLE IF NOT EXISTS credit_notes(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, contact_id INT, invoice_id INT,
 date TEXT, reason TEXT, subtotal REAL, tax REAL, total REAL, applied REAL DEFAULT 0,
 refunded REAL DEFAULT 0, status TEXT, notes TEXT);

CREATE TABLE IF NOT EXISTS credit_note_lines(
 id INTEGER PRIMARY KEY, credit_note_id INT, item_id INT, description TEXT, qty REAL,
 unit_price REAL, tax_rate REAL, amount REAL, unit_cost REAL, restock INT DEFAULT 0);

CREATE TABLE IF NOT EXISTS vendor_credits(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, vendor_id INT, bill_id INT,
 date TEXT, reason TEXT, subtotal REAL, tax REAL, total REAL, applied REAL DEFAULT 0,
 status TEXT, notes TEXT);

CREATE TABLE IF NOT EXISTS vendor_credit_lines(
 id INTEGER PRIMARY KEY, vendor_credit_id INT, item_id INT, account_id INT, description TEXT,
 qty REAL, unit_cost REAL, tax_rate REAL, amount REAL, restock INT DEFAULT 0);

CREATE TABLE IF NOT EXISTS purchase_orders(
 id INTEGER PRIMARY KEY, company_id INT, number TEXT, vendor_id INT, date TEXT, delivery_date TEXT,
 status TEXT, subtotal REAL, tax REAL, total REAL, notes TEXT, bill_id INT, received_at TEXT);

CREATE TABLE IF NOT EXISTS purchase_order_lines(
 id INTEGER PRIMARY KEY, purchase_order_id INT, item_id INT, account_id INT, description TEXT,
 qty REAL, unit_cost REAL, tax_rate REAL, amount REAL, qty_received REAL DEFAULT 0);

CREATE TABLE IF NOT EXISTS currencies(
 code TEXT PRIMARY KEY, name TEXT, symbol TEXT, rate REAL);

CREATE INDEX IF NOT EXISTS ix_jl_entry ON journal_lines(entry_id);
CREATE INDEX IF NOT EXISTS ix_inv_contact ON invoices(contact_id);
CREATE INDEX IF NOT EXISTS ix_je_date ON journal_entries(date);
"""

# ----------------------------------------------------------------------------- base chart of accounts
BASE_COA = [
    ("1000", "Cash on Hand", "asset", "cash"),
    ("1010", "Bank - USD Operating", "asset", "bank"),
    ("1020", "Bank - ZiG Operating", "asset", "bank"),
    ("1100", "Accounts Receivable", "asset", "ar"),
    ("1150", "Customer Credits Available", "asset", "ar"),
    ("1200", "Inventory", "asset", "inventory"),
    ("1300", "Prepaid Expenses", "asset", "current_asset"),
    ("1400", "Input VAT Recoverable", "asset", "tax_receivable"),
    ("1500", "Property, Plant & Equipment", "asset", "fixed_asset"),
    ("1510", "Accumulated Depreciation", "asset", "accum_dep"),
    ("2000", "Accounts Payable", "liability", "ap"),
    ("2050", "Supplier Credits Available", "liability", "ap"),
    ("2060", "Goods Received Not Invoiced", "liability", "current_liability"),
    ("2100", "VAT Payable", "liability", "tax_payable"),
    ("2200", "PAYE Payable", "liability", "tax_payable"),
    ("2210", "NSSA Payable", "liability", "tax_payable"),
    ("2220", "AIDS Levy Payable", "liability", "tax_payable"),
    ("2300", "Accrued Expenses", "liability", "current_liability"),
    ("2400", "Bank Loans", "liability", "long_term_liability"),
    ("2500", "Director's Loan", "liability", "long_term_liability"),
    ("3000", "Share Capital", "equity", "equity"),
    ("3100", "Retained Earnings", "equity", "equity"),
    ("3200", "Owner's Drawings", "equity", "drawings"),
    ("4000", "Goods Sales", "income", "revenue"),
    ("4100", "Services Revenue", "income", "revenue"),
    ("4200", "Other Income", "income", "other_income"),
    ("4900", "Sales Discounts", "income", "revenue"),
    ("5000", "Cost of Goods Sold", "expense", "cogs"),
    ("5010", "Freight & Delivery", "expense", "cogs"),
    ("5100", "Salaries & Wages", "expense", "payroll"),
    ("5110", "Employer NSSA Contributions", "expense", "payroll"),
    ("5200", "Rent", "expense", "expense"),
    ("5210", "Utilities (ZESA & Water)", "expense", "expense"),
    ("5220", "Fuel & Lubricants", "expense", "expense"),
    ("5230", "Repairs & Maintenance", "expense", "expense"),
    ("5240", "Depreciation", "expense", "depreciation"),
    ("5250", "Bank Charges", "expense", "expense"),
    ("5260", "Professional Fees", "expense", "expense"),
    ("5270", "Travel & Accommodation", "expense", "expense"),
    ("5280", "Marketing & Advertising", "expense", "expense"),
    ("5290", "Insurance", "expense", "expense"),
    ("5300", "Telephone & Internet", "expense", "expense"),
    ("5400", "Office Supplies", "expense", "expense"),
    ("5500", "Licences & Fees", "expense", "expense"),
    ("5600", "Bad Debts", "expense", "expense"),
    ("5700", "Interest Expense", "expense", "expense"),
]

NAMES = ["Tatenda Moyo", "Rudo Chikafu", "Farai Ncube", "Nyasha Dube", "Kudzai Sibanda",
         "Chipo Marufu", "Tapiwa Nyandoro", "Blessing Mutasa", "Rutendo Chari", "Simba Gumbo",
         "Anesu Mudimu", "Panashe Zhou"]

# ----------------------------------------------------------------------------- industry profiles
PROFILES = {
    "mining": {
        "label": "Mining & Resources", "icon": "pickaxe",
        "tagline": "Production, royalties, heavy equipment & rehabilitation",
        "accounts": [
            ("1210", "Ore Stockpiles", "asset", "inventory"),
            ("1220", "Spare Parts & Consumables", "asset", "inventory"),
            ("2600", "Mine Rehabilitation Provision", "liability", "long_term_liability"),
            ("4020", "Concentrate & Ore Sales", "income", "revenue"),
            ("4030", "Equipment Hire Income", "income", "revenue"),
            ("5232", "Royalties & Mineral Fees", "expense", "expense"),
            ("5233", "Explosives & Blasting", "expense", "expense"),
            ("5234", "Contract Haulage", "expense", "cogs"),
        ],
        "customers": ["Mvurwi Gold Syndicate", "Great Dyke Minerals", "Karo Platinum",
                      "Shamva Stone Works", "Mazowe Chrome Co", "Bindura Ore Traders"],
        "vendors": ["ZESA Holdings", "Mashonaland Diesel Supply", "Rock-Tech Explosives",
                    "Paramount Tyres", "Harare Assay Labs", "ZimConnect Internet", "ZINARA"],
        "items": [("Gold ore - milled (tonne)", "tonne", 185, 96, 1, "4020"),
                  ("PGM concentrate (tonne)", "tonne", 410, 240, 1, "4020"),
                  ("Crushed aggregate 19mm (tonne)", "tonne", 42, 21, 1, "4000"),
                  ("Grade control assay", "sample", 85, 18, 0, "4100"),
                  ("Equipment hire - ADT", "day", 640, 180, 0, "4030")],
        "bill_codes": ["5220", "5230", "5210", "5232", "5233", "5400", "5500", "5260", "5300", "5270", "5234"],
        "stock_codes": [("1210", "Ore Stockpiles")],
        "metric": "Tonnes sold", "base_revenue": 96000,
        "roles": [("Mine Manager", 1850), ("Geologist", 1500), ("Blasting Officer", 1150),
                  ("Plant Operator", 760), ("Diesel Mechanic", 700), ("Accounts Clerk", 550),
                  ("Security Supervisor", 480), ("Haul Truck Driver", 430)],
        "assets": [("CAT 777 Haul Truck", "Mobile plant", 145000, 10, 26),
                   ("Atlas Copco Drill Rig", "Mining equipment", 92000, 8, 20),
                   ("Jaw Crusher Plant", "Processing", 68000, 12, 34),
                   ("Workshop Tooling", "Workshop", 14500, 6, 15)],
    },
    "education": {
        "label": "Education & Training", "icon": "cap",
        "tagline": "Tuition billing, sponsors, boarding & term-based income",
        "accounts": [
            ("1110", "Tuition Fees Receivable", "asset", "ar"),
            ("2410", "Deferred Tuition Income", "liability", "current_liability"),
            ("4010", "Tuition Fees", "income", "revenue"),
            ("4020", "Boarding & Catering Income", "income", "revenue"),
            ("5232", "Teaching & Learning Materials", "expense", "expense"),
            ("5233", "Scholarships & Bursaries", "expense", "expense"),
            ("5234", "Catering & Boarding Costs", "expense", "expense"),
        ],
        "customers": ["Tsime Education Trust", "Mufaro Scholarship Fund", "Highlands Parents Association",
                      "Chiedza Corporate Sponsors", "Ruvimbo Primary Association", "Econet Bridge Academy"],
        "vendors": ["Zimtext Books", "EduSupplies Zimbabwe", "Greenfield Catering",
                    "BusLink Transport", "Telecoms Zimbabwe", "Harare Printworks"],
        "items": [("Term fees - day scholar", "term", 480, 0, 0, "4010"),
                  ("Term fees - boarder", "term", 1250, 0, 0, "4010"),
                  ("Boarding & meals package", "term", 650, 320, 0, "4020"),
                  ("School bus service", "term", 120, 55, 0, "4100"),
                  ("Aftercare programme", "month", 90, 30, 0, "4100")],
        "bill_codes": ["5232", "5234", "5210", "5230", "5400", "5260", "5300", "5290", "5270"],
        "stock_codes": [("1200", "Inventory")],
        "metric": "Students billed", "base_revenue": 42000,
        "roles": [("Head Teacher", 1600), ("Deputy Head", 1200), ("Senior Teacher", 950),
                  ("Teacher", 660), ("Bursar", 720), ("Admin Clerk", 450),
                  ("Groundskeeper", 340), ("Bus Driver", 420)],
        "assets": [("School Bus - 64 seater", "Vehicles", 68000, 10, 28),
                   ("Science Lab Equipment", "Lab", 24000, 8, 40),
                   ("Computer Lab (30 units)", "ICT", 32000, 5, 18),
                   ("Boarding Furniture", "Furniture", 18000, 8, 52)],
    },
    "transport": {
        "label": "Transport & Logistics", "icon": "truck",
        "tagline": "Trip revenue, fuel, tyres, tolls & fleet maintenance",
        "accounts": [
            ("1220", "Tyres & Spares Inventory", "asset", "inventory"),
            ("4030", "Freight Revenue", "income", "revenue"),
            ("4040", "Passenger Revenue", "income", "revenue"),
            ("5232", "Tolls & Permits", "expense", "expense"),
            ("5233", "Driver Allowances", "expense", "payroll"),
            ("5234", "Vehicle Insurance", "expense", "expense"),
        ],
        "customers": ["Kwekwe Steel & Wire", "Nyamandlovu Cement Co", "Chengetai Beverages",
                      "Mhunga Grain Mills", "Zambezi Cotton Ginners", "Sakunda Agro Logistics"],
        "vendors": ["Harare Fuel Depot", "Bandag Tyres ZW", "ZINARA", "Mvurwi Mechanical Works",
                    "Swift Cargo Insurance", "ZESA Holdings"],
        "items": [("Harare-Bulawayo freight run", "trip", 1250, 640, 0, "4030"),
                  ("Cross-border haulage - Beitbridge", "trip", 3800, 1950, 0, "4030"),
                  ("Bulk fuel haulage", "trip", 2100, 1100, 0, "4030"),
                  ("Bus charter - full day", "day", 850, 380, 0, "4040"),
                  ("Rigid truck hire", "day", 420, 190, 0, "4030")],
        "bill_codes": ["5220", "5230", "5232", "5234", "5210", "5500", "5260", "5400", "5300"],
        "stock_codes": [("1220", "Tyres & Spares Inventory")],
        "metric": "Trips completed", "base_revenue": 74000,
        "roles": [("Operations Manager", 1500), ("Fleet Controller", 900), ("Senior Driver", 580),
                  ("Driver", 470), ("Mechanic", 700), ("Warehouse Clerk", 500),
                  ("Accounts Clerk", 550), ("Dispatch Clerk", 450)],
        "assets": [("Horse & 30t trailer", "Fleet", 118000, 8, 30),
                   ("Isuzu FVR 8t truck", "Fleet", 56000, 7, 22),
                   ("Workshop Equipment", "Workshop", 22000, 8, 44),
                   ("Warehouse Racking", "Warehouse", 16500, 10, 16)],
    },
    "agriculture": {
        "label": "Agriculture & Agro-processing", "icon": "leaf",
        "tagline": "Biological assets, crop inputs, harvests & seasonal labour",
        "accounts": [
            ("1230", "Livestock & Biological Assets", "asset", "inventory"),
            ("4030", "Produce Sales", "income", "revenue"),
            ("4040", "Livestock Sales", "income", "revenue"),
            ("5232", "Crop Inputs & Seed", "expense", "cogs"),
            ("5233", "Irrigation & Borehole Costs", "expense", "expense"),
            ("5234", "Seasonal Labour", "expense", "payroll"),
        ],
        "customers": ["Mhondoro Grain Traders", "Chinhoyi Soya Processors", "Tobacco Auction Floors",
                      "Fresh Produce Market Harare", "Zvimba Dairy Collective", "Ngezi Beef Abattoir"],
        "vendors": ["Windmill Seed Supplies", "AgriChem Zimbabwe", "Irrigation Systems Harare",
                    "ZESA Holdings", "Trekkers Farm Equipment", "Grain Bag Suppliers"],
        "items": [("Maize - grade A (tonne)", "tonne", 310, 175, 1, "4030"),
                  ("Soya beans (tonne)", "tonne", 480, 290, 1, "4030"),
                  ("Flue-cured tobacco (bale)", "bale", 260, 140, 1, "4030"),
                  ("Horticulture export crate", "crate", 34, 18, 1, "4030"),
                  ("Cattle - feedlot (head)", "head", 850, 520, 1, "4040")],
        "bill_codes": ["5232", "5233", "5220", "5230", "5210", "5234", "5400", "5260", "5290"],
        "stock_codes": [("1200", "Inventory"), ("1230", "Livestock & Biological Assets")],
        "metric": "Tonnes harvested", "base_revenue": 58000,
        "roles": [("Farm Manager", 1300), ("Agronomist", 1100), ("Irrigation Technician", 650),
                  ("Tractor Operator", 480), ("Field Supervisor", 520), ("General Worker", 330),
                  ("Store Clerk", 420), ("Accounts Clerk", 540)],
        "assets": [("John Deere 6120 Tractor", "Machinery", 88000, 10, 32),
                   ("Centre Pivot Irrigation", "Irrigation", 64000, 12, 48),
                   ("Grain Silo - 500t", "Storage", 42000, 20, 60),
                   ("Bakkie - Isuzu D-Max", "Vehicles", 38000, 6, 12)],
    },
    "manufacturing": {
        "label": "Manufacturing", "icon": "factory",
        "tagline": "Raw materials, WIP, finished goods & factory overheads",
        "accounts": [
            ("1240", "Work in Progress", "asset", "inventory"),
            ("1250", "Finished Goods", "asset", "inventory"),
            ("4040", "Manufacturing Sales", "income", "revenue"),
            ("5232", "Factory Overheads", "expense", "cogs"),
            ("5233", "Machine Maintenance", "expense", "expense"),
            ("5234", "Packaging Materials", "expense", "cogs"),
        ],
        "customers": ["Sunrise Wholesalers", "Chikwanha Retail Group", "Nyanga Hotels Supply",
                      "Midlands Distributors", "Gweru Hardware Mart", "Masvingo Trade Centre"],
        "vendors": ["Zimbabwe Packaging Co", "Steel & Wire Supplies", "ZESA Holdings",
                    "Bulawayo Machine Works", "Chemicals Africa", "ZimConnect Internet"],
        "items": [("Bottled water 500ml (case)", "case", 9.5, 5.2, 1, "4040"),
                  ("Maize meal 10kg (bag)", "bag", 11.8, 6.4, 1, "4040"),
                  ("Steel door frame (unit)", "unit", 78, 44, 1, "4040"),
                  ("Contract packing (hour)", "hour", 55, 22, 0, "4100")],
        "bill_codes": ["5232", "5233", "5234", "5210", "5220", "5230", "5400", "5260", "5500"],
        "stock_codes": [("1200", "Inventory"), ("1250", "Finished Goods")],
        "metric": "Units produced", "base_revenue": 124000,
        "roles": [("Plant Manager", 1900), ("Production Supervisor", 1100), ("Machine Operator", 620),
                  ("Quality Controller", 750), ("Storekeeper", 500), ("Maintenance Fitter", 780),
                  ("Accounts Clerk", 560), ("Dispatch Clerk", 460)],
        "assets": [("Bottling Line", "Plant", 165000, 12, 36),
                   ("Forklift - 3t", "Mobile plant", 34000, 8, 20),
                   ("Factory Roof & Fit-out", "Buildings", 78000, 20, 55),
                   ("Quality Lab Equipment", "Lab", 26500, 7, 14)],
    },
    "banking": {
        "label": "Banking & Microfinance", "icon": "bank",
        "tagline": "Loans, deposits, interest margin & provisioning",
        "accounts": [
            ("1050", "Placements with Other Banks", "asset", "current_asset"),
            ("1310", "Loans & Advances to Customers", "asset", "current_asset"),
            ("2700", "Customer Deposits", "liability", "current_liability"),
            ("4050", "Interest Income - Loans", "income", "revenue"),
            ("4060", "Fees & Commission Income", "income", "revenue"),
            ("5710", "Interest Expense - Deposits", "expense", "expense"),
            ("5720", "Loan Loss Provision", "expense", "expense"),
        ],
        "customers": ["Kazembe Holdings (term loan)", "Mufaro Agro (trade finance)",
                      "Sibanda Transport (asset finance)", "Chiedza Retail (working capital)",
                      "Gumbo Family (mortgage)", "Zhou Logistics (invoice discounting)"],
        "vendors": ["Zimbabwe Interbank Desk", "Harare Legal Chambers", "Core Banking Systems Ltd",
                    "G4S Cash Services", "Telecoms Zimbabwe", "ZESA Holdings"],
        "items": [("Commercial loan facility - monthly", "facility", 1450, 0, 0, "4050"),
                  ("Mortgage facility - monthly", "facility", 890, 0, 0, "4050"),
                  ("Trade finance line - monthly", "facility", 2100, 0, 0, "4050"),
                  ("Account maintenance fee", "account", 6, 0, 0, "4060"),
                  ("Loan application fee", "application", 120, 0, 0, "4060")],
        "bill_codes": ["5710", "5720", "5210", "5230", "5400", "5260", "5300", "5290", "5500"],
        "stock_codes": [],
        "metric": "Facilities billed", "base_revenue": 180000,
        "roles": [("Branch Manager", 2200), ("Credit Analyst", 1400), ("Relationship Manager", 1300),
                  ("Teller", 700), ("Compliance Officer", 1200), ("IT Officer", 950),
                  ("Finance Officer", 900), ("Loans Clerk", 620)],
        "assets": [("Branch Fit-out", "Premises", 94000, 10, 40),
                   ("Core Banking System", "Systems", 120000, 6, 24),
                   ("Cash Vault & Counters", "Security", 46000, 12, 50),
                   ("ATM Terminals (4)", "Systems", 58000, 8, 18)],
    },
    "insurance": {
        "label": "Insurance", "icon": "shield",
        "tagline": "Premiums, unearned premium reserves, claims & reinsurance",
        "accounts": [
            ("1120", "Premiums Receivable", "asset", "ar"),
            ("2420", "Unearned Premium Reserve", "liability", "current_liability"),
            ("2430", "Claims Payable", "liability", "current_liability"),
            ("4050", "Gross Premiums Written", "income", "revenue"),
            ("4060", "Reinsurance Commission", "income", "other_income"),
            ("5710", "Claims Incurred", "expense", "expense"),
            ("5720", "Reinsurance Premiums Ceded", "expense", "cogs"),
            ("5730", "Policy Acquisition Costs", "expense", "expense"),
        ],
        "customers": ["Kwekwe Steel (fleet policy)", "Swift Haulage (goods in transit)",
                      "Harare Teachers Union (group life)", "Chinhoyi Hotels (property)",
                      "Mufaro Farms (crop cover)", "Gomo Mining (equipment all-risk)"],
        "vendors": ["Munich Re Africa (treaty)", "Loss Adjusters Zimbabwe", "Harare Legal Chambers",
                    "Actuarial Services Ltd", "Telecoms Zimbabwe", "ZESA Holdings"],
        "items": [("Motor policy - commercial fleet", "policy", 1450, 0, 0, "4050"),
                  ("Property policy - commercial", "policy", 2200, 0, 0, "4050"),
                  ("Group life policy - per 50 lives", "policy", 980, 0, 0, "4050"),
                  ("Crop weather-index cover", "policy", 1750, 0, 0, "4050"),
                  ("Policy administration fee", "policy", 85, 0, 0, "4060")],
        "bill_codes": ["5710", "5720", "5730", "5210", "5230", "5400", "5260", "5300", "5500"],
        "stock_codes": [],
        "metric": "Policies written", "base_revenue": 92000,
        "roles": [("Underwriting Manager", 1800), ("Claims Assessor", 1200), ("Broker Relations", 1000),
                  ("Policy Admin Clerk", 620), ("Actuarial Analyst", 1500), ("Finance Officer", 900),
                  ("Accounts Clerk", 560), ("Claims Clerk", 520)],
        "assets": [("Office Refurbishment", "Premises", 52000, 10, 42),
                   ("Policy Admin System", "Systems", 76000, 6, 26),
                   ("Motor Fleet (claims assessors)", "Vehicles", 64000, 6, 16),
                   ("Boardroom Fit-out", "Furniture", 19000, 8, 55)],
    },
    "hospitals": {
        "label": "Hospitals & Healthcare", "icon": "heart",
        "tagline": "Patient billing, medical aid claims, pharmacy & theatres",
        "accounts": [
            ("1130", "Patient & Medical Aid Receivable", "asset", "ar"),
            ("4070", "Patient Service Revenue", "income", "revenue"),
            ("4080", "Pharmacy Revenue", "income", "revenue"),
            ("5232", "Medical Supplies & Drugs", "expense", "cogs"),
            ("5233", "Locum & Agency Staff", "expense", "payroll"),
            ("5234", "Medical Equipment Maintenance", "expense", "expense"),
        ],
        "customers": ["HealthGuard Medical Aid", "MedSure Zimbabwe", "Premier Health Fund",
                      "Corporate Scheme - Kwekwe Steel", "Self-pay - Ward Patients", "Ministry of Health (BEAM)"],
        "vendors": ["Pharma Distributors ZW", "MedEquip Zimbabwe", "Oxygen Solutions",
                    "ZESA Holdings", "Clinical Waste Services", "Harare Labs"],
        "items": [("Consultation - specialist", "visit", 65, 12, 0, "4070"),
                  ("Inpatient day - private ward", "day", 320, 140, 0, "4070"),
                  ("Theatre procedure - major", "procedure", 1850, 620, 0, "4070"),
                  ("Pharmacy dispense", "script", 48, 29, 1, "4080"),
                  ("Laboratory test panel", "panel", 95, 38, 0, "4070")],
        "bill_codes": ["5232", "5233", "5234", "5210", "5230", "5400", "5260", "5290", "5300"],
        "stock_codes": [("1200", "Inventory")],
        "metric": "Patient visits", "base_revenue": 112000,
        "roles": [("Medical Superintendent", 2600), ("Physician", 2100), ("Theatre Nurse", 950),
                  ("Registered Nurse", 700), ("Pharmacist", 1100), ("Radiographer", 900),
                  ("Accounts Clerk", 560), ("Records Clerk", 460)],
        "assets": [("Theatre Equipment", "Medical", 148000, 10, 34),
                   ("Ambulance - Toyota", "Vehicles", 72000, 7, 20),
                   ("Digital X-Ray", "Imaging", 96000, 8, 12),
                   ("Ward Furniture & Beds", "Furniture", 39000, 10, 58)],
    },
}

# ----------------------------------------------------------------------------- helpers
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def money(v):
    return f"{v:,.2f}"


# ----------------------------------------------------------------------------- PAYE (Zimbabwe USD 2025/26 bands)
def paye_zim(gross):
    bands = [(100, 0.0), (300, 0.20), (1000, 0.25), (2000, 0.30), (3000, 0.35), (float("inf"), 0.40)]
    tax, lower = 0.0, 0.0
    for upper, rate in bands:
        if gross > lower:
            taxable = min(gross, upper) - lower
            tax += taxable * rate
        lower = upper
    tax = max(tax, 0.0)
    aids = round(tax * 0.03, 2)
    nssa = round(min(gross, 700) * 0.045, 2)
    return round(tax, 2), aids, nssa


def add_je(cur, company_id, when, memo, source, ref, lines, counter):
    """lines: [(account_code, debit, credit, description)] - must balance."""
    d = sum(l[1] for l in lines)
    c = sum(l[2] for l in lines)
    if abs(d - c) > 0.02:
        raise ValueError(f"Unbalanced JE {memo}: Dr {d} Cr {c}")
    counter["je"] += 1
    num = f"JE-{counter['je']:04d}"
    cur.execute("INSERT INTO journal_entries(company_id,number,date,memo,source,reference,created_at) VALUES(?,?,?,?,?,?,?)",
                (company_id, num, when, memo, source, ref, str(TODAY)))
    eid = cur.lastrowid
    for code, dr, cr, desc in lines:
        if abs(dr) < 0.001 and abs(cr) < 0.001:
            continue
        aid = counter["acct"][code]
        cur.execute("INSERT INTO journal_lines(entry_id,account_id,description,debit,credit) VALUES(?,?,?,?,?)",
                    (eid, aid, desc, round(dr, 2), round(cr, 2)))
    return eid


# ----------------------------------------------------------------------------- seed
TENANT_TABLES = [
    ("companies", "id"), ("accounts", "company_id"), ("contacts", "company_id"),
    ("items", "company_id"), ("quotes", "company_id"), ("quote_lines", "quote_id:q"),
    ("invoices", "company_id"), ("invoice_lines", "invoice_id:i"),
    ("credit_notes", "company_id"), ("credit_note_lines", "credit_note_id:c"),
    ("bills", "company_id"), ("bill_lines", "bill_id:b"),
    ("vendor_credits", "company_id"), ("vendor_credit_lines", "vendor_credit_id:v"),
    ("purchase_orders", "company_id"), ("purchase_order_lines", "purchase_order_id:p"),
    ("payments", "company_id"), ("bank_accounts", "company_id"), ("bank_txns", "company_id"),
    ("journal_lines", "entry_id:j"), ("journal_entries", "company_id"),
    ("employees", "company_id"), ("payroll_runs", "company_id"), ("payslips", "run_id:r"),
    ("fixed_assets", "company_id"), ("users", "company_id"), ("sessions_tbl", "company_id"),
]


def delete_tenant(conn, company_id, keep_users=False):
    """Remove every record belonging to one company. Fresh users are recreated on seed."""
    cur = conn.cursor()
    sub = {"q": ("quote_lines", "quote_id", "quotes"),
           "i": ("invoice_lines", "invoice_id", "invoices"),
           "c": ("credit_note_lines", "credit_note_id", "credit_notes"),
           "b": ("bill_lines", "bill_id", "bills"),
           "v": ("vendor_credit_lines", "vendor_credit_id", "vendor_credits"),
           "p": ("purchase_order_lines", "purchase_order_id", "purchase_orders"),
           "j": ("journal_lines", "entry_id", "journal_entries"),
           "r": ("payslips", "run_id", "payroll_runs")}
    for table, spec in TENANT_TABLES:
        if table == "users" and keep_users:
            continue
        if ":" in spec:
            child, col, parent = sub[spec.split(":")[1]]
            cur.execute(f"DELETE FROM {child} WHERE {col} IN (SELECT id FROM {parent} WHERE company_id=?)",
                        (company_id,))
        elif table == "companies":
            cur.execute("DELETE FROM companies WHERE id=?", (company_id,))
        else:
            cur.execute(f"DELETE FROM {table} WHERE {spec}=?", (company_id,))
    conn.commit()


def rebuild_tenant(conn, company_id, profile_key="mining", demo=True):
    delete_tenant(conn, company_id)
    return seed_company(conn, profile_key, demo)


def reset_and_seed(profile_key="mining", demo=True):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    seed_company(conn, profile_key, demo, user_mode="standard")
    conn.close()


def seed_company(conn, profile_key, demo=True, user_mode="tenant"):
    prof = PROFILES[profile_key]
    random.seed(11)
    cur = conn.cursor()
    n_companies = conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"]
    if user_mode == "tenant":
        company_name = f"Demo · {prof['label']} workspace {n_companies + 1}"
    else:
        company_name = f"Tatmaq {prof['label'].split(' & ')[0]} (Pvt) Ltd"
    cur.execute("""INSERT INTO companies(name,industry,currency,symbol,tax_name,tax_rate,address,email,phone,fiscal_start,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (company_name, profile_key, "USD", "$", "VAT", 15,
                 "12 Baines Avenue, Harare, Zimbabwe", f"finance@tatmaq-{profile_key}.co.zw", "+263 242 700 118",
                 "2026-01-01", str(TODAY)))
    cid = cur.lastrowid
    counter = {"je": 0, "acct": {}}

    # accounts
    for code, name, typ, sub in BASE_COA + prof["accounts"]:
        cur.execute("INSERT INTO accounts(company_id,code,name,type,subtype) VALUES(?,?,?,?,?)",
                    (cid, code, name, typ, sub))
        counter["acct"][code] = cur.lastrowid

    # currencies / users
    for row in [("USD", "US Dollar", "$", 1.0), ("ZWG", "Zimbabwe Gold", "ZiG", 27.5)]:
        cur.execute("INSERT OR REPLACE INTO currencies(code,name,symbol,rate) VALUES(?,?,?,?)", row)

    names = random.sample(NAMES, len(prof["roles"]))
    from werkzeug.security import generate_password_hash as _hpw
    if user_mode == "standard":
        # the primary seeded workspace: documented demo logins, password demo1234
        demo_users = [
            ("Tatenda Maq", "owner@tatmaqbooks.co.zw", "owner", "demo1234"),
            ("Rudo Chikafu", "accountant@tatmaqbooks.co.zw", "accountant", "demo1234"),
            ("Farai Ncube", "sales@tatmaqbooks.co.zw", "sales", "demo1234"),
            ("Tarisai Mhaka", "auditor@tatmaqbooks.co.zw", "auditor", "demo1234"),
        ]
        for uname, email, role, pw in demo_users:
            cur.execute("""INSERT INTO users(company_id,name,email,role,status,password_hash,created_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (cid, uname, email, role, "Active", _hpw(pw), str(date.today())))
    elif user_mode == "tenant":
        # throwaway demo workspaces: unique emails so no login ever collides
        tag = f"demo+{cid}"
        for uname, role in [("Demo Owner", "owner"), ("Demo Accountant", "accountant"),
                            ("Demo Clerk", "sales"), ("Demo Auditor", "auditor")]:
            cur.execute("""INSERT INTO users(company_id,name,email,role,status,password_hash,created_at)
                           VALUES(?,?,?,?,?,?,?)""",
                        (cid, uname, f"{role}.{tag}@tatmaqbooks.co.zw", role, "Active",
                         _hpw(secrets.token_urlsafe(18)), str(date.today())))
    # user_mode == "none": a real tenant — the registering owner is added by the caller

    # bank accounts linked to 1010 / 1020
    cur.execute("INSERT INTO bank_accounts(company_id,name,account_id,number,opening_balance,currency) VALUES(?,?,?,?,?,?)",
                (cid, "CBZ Bank - USD Operating", counter["acct"]["1010"], "0221 4567 8901", 30000, "USD"))
    cur.execute("INSERT INTO bank_accounts(company_id,name,account_id,number,opening_balance,currency) VALUES(?,?,?,?,?,?)",
                (cid, "FBC Bank - ZiG Account", counter["acct"]["1020"], "0812 3345 6789", 0, "ZWG"))

    # contacts
    customers, vendors = [], []
    for name in prof["customers"]:
        cur.execute("INSERT INTO contacts(company_id,type,name,company,email,phone,address,tax_no,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (cid, "customer", name, name, f"accounts@{name.split()[0].lower()}.co.zw",
                     "+263 77 " + str(random.randint(100, 999)) + " " + str(random.randint(1000, 9999)),
                     "Harare, Zimbabwe", "BP" + str(random.randint(1000000, 9999999)), str(TODAY)))
        customers.append(cur.lastrowid)
    for name in prof["vendors"]:
        cur.execute("INSERT INTO contacts(company_id,type,name,company,email,phone,address,tax_no,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (cid, "vendor", name, name, f"sales@{name.split()[0].lower()}.co.zw",
                     "+263 24 " + str(random.randint(200, 799)) + " " + str(random.randint(1000, 9999)),
                     "Harare, Zimbabwe", "BP" + str(random.randint(1000000, 9999999)), str(TODAY)))
        vendors.append(cur.lastrowid)

    # items
    items = []
    for i, (name, unit, price, cost, tracked, rev) in enumerate(prof["items"]):
        qty = random.randint(120, 420) if tracked else 0
        reorder = random.randint(40, 90) if tracked else 0
        cur.execute("""INSERT INTO items(company_id,name,sku,kind,unit,price,cost,tax_rate,qty,reorder,tracked,account_id)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, name, f"{profile_key[:3].upper()}-{i+1:03d}", "goods" if tracked else "service", unit,
                     price, cost, 15, qty, reorder, tracked, counter["acct"][rev]))
        items.append({"id": cur.lastrowid, "name": name, "unit": unit, "price": price, "cost": cost,
                      "tracked": tracked, "rev_code": rev, "qty": qty, "reorder": reorder})

    # employees
    emps = []
    for i, (position, gross) in enumerate(prof["roles"]):
        cur.execute("INSERT INTO employees(company_id,name,position,department,gross,start_date,paye_no,status) VALUES(?,?,?,?,?,?,?,?)",
                    (cid, names[i % len(names)], position, "Operations" if i < 4 else "Support", gross,
                     f"20{random.randint(18, 24)}-0{random.randint(1, 9)}-15", "PAYE" + str(random.randint(100000, 999999)), "Active"))
        emps.append({"id": cur.lastrowid, "gross": gross})

    # fixed assets (cost already in opening balances)
    asset_cost = 0
    for name, cat, cost, life, ago in prof["assets"]:
        purch = TODAY.replace(day=1) - timedelta(days=ago * 30)
        cur.execute("""INSERT INTO fixed_assets(company_id,name,category,purchase_date,cost,salvage,life,
                       accum_dep,last_dep,exp_account_id,accum_account_id,status,location)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, name, cat, str(purch), cost, 0, life, 0, None, counter["acct"]["5240"],
                     counter["acct"]["1510"], "In service", "Harare"))
        asset_cost += cost

    if demo:
        _seed_demo(conn, cur, cid, prof, counter, customers, vendors, items, emps, asset_cost)
    else:
        # clean start: opening balance only
        add_je(cur, cid, "2026-01-01", "Opening balances", "opening", "OPEN-1",
               [("1010", 30000, 0, "Opening bank balance"),
                ("3000", 0, 30000, "Share capital introduced")], counter)
    conn.commit()
    return cid


def _seed_demo(conn, cur, cid, prof, counter, customers, vendors, items, emps, asset_cost):
    today = TODAY
    fy_start = date(2026, 1, 1)
    # ---- opening balances (Dec 2025 start-of-history)
    opening_inventory = round(sum(it["qty"] * it["cost"] for it in items), 2)
    dr_total = 30000 + asset_cost + opening_inventory
    retained = dr_total - 50000
    add_je(cur, cid, "2025-12-01", "Opening balances brought forward", "opening", "OPEN-1", [
        ("1010", 30000, 0, "Bank opening balance"),
        ("1500", asset_cost, 0, "Property, plant & equipment at cost"),
        ("1200", opening_inventory, 0, "Opening stock at cost"),
        ("3000", 0, 50000, "Share capital"),
        ("3100", 0, retained, "Retained earnings brought forward"),
    ], counter)
    for name, cat, cost, life, ago in []:
        pass

    banks = [dict(r) for r in cur.execute("SELECT * FROM bank_accounts WHERE company_id=?", (cid,))]
    usd_bank = banks[0]

    inv_no = 0
    quote_no = 0
    bill_no = 0
    months = []
    d = today.replace(day=1)
    for k in range(11, -1, -1):
        y = d.year
        m = d.month - k
        while m <= 0:
            m += 12
            y -= 1
        months.append(date(y, m, 1))

    def last_day(dt):
        nxt = (dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt - timedelta(days=1)

    def post_invoice(cust, when, lines, paid_pct):
        nonlocal inv_no
        inv_no += 1
        number = f"INV-{inv_no:04d}"
        subtotal = round(sum(l["qty"] * l["unit_price"] for l in lines), 2)
        tax = round(sum(l["qty"] * l["unit_price"] * l["tax_rate"] / 100 for l in lines), 2)
        total = subtotal + tax
        due = when + timedelta(days=random.choice([14, 14, 30, 30, 30, 45]))
        paid = round(total * paid_pct, 2)
        status = "paid" if paid >= total - 0.01 else ("sent" if paid == 0 else "partial")
        cur.execute("""INSERT INTO invoices(company_id,number,contact_id,date,due_date,status,subtotal,tax,total,
                       amount_paid,notes,currency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (cid, number, cust, str(when), str(due), status, subtotal, tax, total, paid,
                     "Thank you for your business. Payment via ZIPIT / EcoCash.", "USD"))
        iid = cur.lastrowid
        je = [("1100", total, 0, number)]
        for l in lines:
            cur.execute("""INSERT INTO invoice_lines(invoice_id,item_id,description,qty,unit_price,tax_rate,amount,unit_cost)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (iid, l["item_id"], l["desc"], l["qty"], l["unit_price"], l["tax_rate"],
                         round(l["qty"] * l["unit_price"], 2), l["cost"]))
            je.append((l["rev_code"], 0, round(l["qty"] * l["unit_price"], 2), l["desc"]))
            if l["tracked"]:
                item = next(it for it in items if it["id"] == l["item_id"])
                cogs = round(l["qty"] * item["cost"], 2)
                je.append(("5000", cogs, 0, "Cost of sales - " + l["desc"]))
                je.append(("1200", 0, cogs, "Stock issued - " + l["desc"]))
        if tax:
            je.append(("2100", 0, tax, "VAT on " + number))
        add_je(cur, cid, str(when), f"Sales invoice {number}", "invoice", number, je, counter)

        if paid > 0:
            pay_date = min(due + timedelta(days=random.randint(-4, 9)), today)
            if pay_date < when:
                pay_date = when + timedelta(days=3)
            method = random.choice(["Bank transfer", "EcoCash", "ZIPIT", "Cheque", "Cash"])
            cur.execute("""INSERT INTO payments(company_id,kind,contact_id,invoice_id,date,amount,method,bank_account_id,reference)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (cid, "received", cust, iid, str(pay_date), paid, method, usd_bank["id"], f"RCPT-{inv_no:04d}"))
            add_je(cur, cid, str(pay_date), f"Payment received - {number}", "payment", number,
                   [("1010", paid, 0, f"{method} receipt {number}"), ("1100", 0, paid, number)], counter)
            cur.execute("""INSERT INTO bank_txns(company_id,bank_account_id,date,description,reference,amount,direction,status,source)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (cid, usd_bank["id"], str(pay_date), f"Receipt - {number}", f"RCPT-{inv_no:04d}",
                         paid, "in", "reconciled", "books"))

        # keep item quantities sensible
        for l in lines:
            if l["tracked"]:
                cur.execute("UPDATE items SET qty = qty - ? WHERE id=?", (l["qty"], l["item_id"]))

    # ---- monthly sales
    for mi, mstart in enumerate(months):
        is_current = mstart.year == today.year and mstart.month == today.month
        n_invoices = 6 if is_current else random.randint(7, 9)
        month_factor = 1.0 if mi < 10 else 0.75
        for _ in range(n_invoices):
            when = mstart + timedelta(days=random.randint(0, 26))
            if is_current:
                when = min(when, today - timedelta(days=1))
            cust = random.choice(customers)
            nlines = random.randint(1, 3)
            lines = []
            for _ in range(nlines):
                it = random.choices(items, weights=[3 if it["tracked"] else 1 for it in items])[0]
                if it["tracked"]:
                    qty = round(random.uniform(8, 34) / 2) * 2 + 2
                else:
                    qty = random.randint(1, 6)
                lines.append({"item_id": it["id"], "desc": it["name"], "qty": qty,
                              "unit_price": it["price"], "tax_rate": 15, "cost": it["cost"],
                              "tracked": it["tracked"], "rev_code": it["rev_code"]})
            age_days = (today - when).days
            if age_days > 55:
                paid_pct = random.choice([1.0, 1.0, 1.0, 1.0, 0.5, 0.5])
            elif age_days > 25:
                paid_pct = random.choice([1.0, 1.0, 1.0, 0.5, 0.0, 0.0])
            else:
                paid_pct = random.choice([0.0, 0.0, 0.0, 1.0])
            post_invoice(cust, when, lines, paid_pct)

    # ---- replenish stock so quantities stay realistic (purchases already booked above)
    for it in items:
        if it["tracked"]:
            cur.execute("UPDATE items SET qty = ? WHERE id=?", (random.randint(90, 380), it["id"]))
        else:
            cur.execute("UPDATE items SET qty = 0 WHERE id=?", (it["id"],))
    # ---- quotes
    for _ in range(4):
        quote_no += 1
        when = today - timedelta(days=random.randint(2, 20))
        cust = random.choice(customers)
        it = random.choice(items)
        qty = random.randint(4, 20) if it["tracked"] else random.randint(1, 5)
        amount = round(qty * it["price"], 2)
        tax = round(amount * 0.15, 2)
        status = random.choice(["sent", "sent", "accepted", "draft"])
        cur.execute("""INSERT INTO quotes(company_id,number,contact_id,date,expiry,status,subtotal,tax,total,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (cid, f"QT-{quote_no:04d}", cust, str(when), str(when + timedelta(days=21)), status,
                     amount, tax, amount + tax, "Validity 21 days. Prices exclude VAT."))
        qid = cur.lastrowid
        cur.execute("""INSERT INTO quote_lines(quote_id,item_id,description,qty,unit_price,tax_rate,amount)
                       VALUES(?,?,?,?,?,?,?)""",
                    (qid, it["id"], it["name"], qty, it["price"], 15, amount))

    # ---- bills
    for mi, mstart in enumerate(months):
        is_current = mstart.year == today.year and mstart.month == today.month
        n_bills = 4 if is_current else random.randint(5, 7)
        for _ in range(n_bills):
            when = mstart + timedelta(days=random.randint(0, 26))
            if is_current:
                when = min(when, today - timedelta(days=1))
            vendor = random.choice(vendors)
            bill_no += 1
            number = f"BILL-{bill_no:04d}"
            nlines = random.randint(1, 2)
            lines, subtotal, tax = [], 0, 0
            use_stock = prof["stock_codes"] and random.random() < 0.3
            for _l in range(nlines):
                if use_stock:
                    code, cname = random.choice(prof["stock_codes"])
                    it = random.choice([i for i in items if i["tracked"]] or items)
                    qty = random.randint(20, 60)
                    unit_cost = round(it["cost"] * random.uniform(0.85, 1.05), 2)
                    amount = round(qty * unit_cost, 2)
                    lines.append({"item_id": it["id"], "account_id": counter["acct"][code],
                                  "desc": f"{it['name']} - stock purchase", "qty": qty,
                                  "unit_cost": unit_cost, "tax_rate": 15, "amount": amount})
                    cur.execute("UPDATE items SET qty = qty + ? WHERE id=?", (qty, it["id"]))
                else:
                    code = random.choice(prof["bill_codes"])
                    amount = round(random.uniform(120, 1800), 2)
                    name = cur.execute("SELECT name FROM accounts WHERE code=?", (code,)).fetchone()[0]
                    lines.append({"item_id": None, "account_id": counter["acct"][code],
                                  "desc": name, "qty": 1, "unit_cost": amount, "tax_rate": 15, "amount": amount})
                subtotal += lines[-1]["amount"]
                tax += round(lines[-1]["amount"] * 0.15, 2)
            total = round(subtotal + tax, 2)
            due = when + timedelta(days=random.choice([14, 30, 30, 45]))
            age_days = (today - when).days
            paid_pct = random.choice([1.0, 1.0, 0.0]) if age_days > 45 else random.choice([0.0, 0.0, 1.0])
            paid = round(total * paid_pct, 2)
            status = "paid" if paid >= total - 0.01 else ("partial" if paid else "open")
            cur.execute("""INSERT INTO bills(company_id,number,vendor_id,date,due_date,status,subtotal,tax,total,amount_paid,notes)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (cid, number, vendor, str(when), str(due), status, round(subtotal, 2), round(tax, 2),
                         total, paid, "Supplier invoice"))
            bid = cur.lastrowid
            je = [("2000", 0, total, number), ("1400", round(tax, 2), 0, "Input VAT " + number)]
            for l in lines:
                cur.execute("""INSERT INTO bill_lines(bill_id,item_id,account_id,description,qty,unit_cost,tax_rate,amount)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (bid, l["item_id"], l["account_id"], l["desc"], l["qty"], l["unit_cost"], l["tax_rate"], l["amount"]))
                je.append(([k for k, v in counter["acct"].items() if v == l["account_id"]][0], l["amount"], 0, l["desc"]))
            add_je(cur, cid, str(when), f"Vendor bill {number}", "bill", number, je, counter)
            if paid > 0:
                pay_date = min(due + timedelta(days=random.randint(-5, 5)), today)
                if pay_date < when:
                    pay_date = when + timedelta(days=2)
                cur.execute("""INSERT INTO payments(company_id,kind,contact_id,bill_id,date,amount,method,bank_account_id,reference)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                            (cid, "made", vendor, bid, str(pay_date), paid, "Bank transfer", usd_bank["id"], f"PAY-{bill_no:04d}"))
                add_je(cur, cid, str(pay_date), f"Payment made - {number}", "payment", number,
                       [("2000", paid, 0, number), ("1010", 0, paid, f"Transfer {number}")], counter)
                cur.execute("""INSERT INTO bank_txns(company_id,bank_account_id,date,description,reference,amount,direction,status,source)
                               VALUES(?,?,?,?,?,?,?,?,?)""",
                            (cid, usd_bank["id"], str(pay_date), f"Payment - {number}", f"PAY-{bill_no:04d}",
                             paid, "out", "reconciled", "books"))

    # ---- payroll runs (monthly)
    for mstart in months:
        period = f"{mstart.year}-{mstart.month:02d}"
        pay_date = last_day(mstart)
        if pay_date > today:
            pay_date = today
        gross_total = paye_total = nssa_total = net_total = 0
        slips = []
        for e in emps:
            gross = e["gross"]
            paye, aids, nssa = paye_zim(gross)
            net = round(gross - paye - aids - nssa, 2)
            slips.append((e["id"], gross, paye, aids, nssa, net))
            gross_total += gross
            paye_total += paye
            nssa_total += nssa
            net_total += net
        employer_nssa = round(sum(min(e["gross"], 700) * 0.045 for e in emps), 2)
        cur.execute("""INSERT INTO payroll_runs(company_id,period,date,gross,paye,nssa,net,status)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (cid, period, str(pay_date), round(gross_total, 2), round(paye_total, 2),
                     round(nssa_total + employer_nssa, 2), round(net_total, 2), "paid"))
        rid = cur.lastrowid
        for s in slips:
            cur.execute("""INSERT INTO payslips(run_id,employee_id,gross,paye,aids,nssa,net) VALUES(?,?,?,?,?,?,?)""", (rid,) + s)
        add_je(cur, cid, str(pay_date), f"Payroll {period}", "payroll", period, [
            ("5100", gross_total, 0, "Gross salaries"),
            ("5110", employer_nssa, 0, "Employer NSSA"),
            ("2200", 0, round(paye_total, 2), "PAYE payable"),
            ("2220", 0, round(sum(s[3] for s in slips), 2), "AIDS levy"),
            ("2210", 0, round(nssa_total + employer_nssa, 2), "NSSA payable"),
            ("2300", 0, round(net_total, 2), "Net wages accrued"),
        ], counter)
        add_je(cur, cid, str(pay_date), f"Net pay transfer {period}", "payroll", period, [
            ("2300", net_total, 0, "Net wages paid"),
            ("1010", 0, net_total, "Salaries bank transfer"),
        ], counter)
        cur.execute("""INSERT INTO bank_txns(company_id,bank_account_id,date,description,reference,amount,direction,status,source)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (cid, usd_bank["id"], str(pay_date), f"Payroll {period}", f"PAYROLL-{period}",
                     net_total, "out", "reconciled", "books"))

    # ---- depreciation (monthly, in service)
    for mstart in months:
        dep_total = 0
        for name, cat, cost, life, ago in prof["assets"]:
            monthly = cost / life / 12
            dep_total += monthly
        if dep_total <= 0:
            continue
        add_je(cur, cid, str(last_day(mstart)), f"Depreciation {mstart.year}-{mstart.month:02d}",
               "depreciation", "DEP", [
                   ("5240", round(dep_total, 2), 0, "Monthly depreciation charge"),
                   ("1510", 0, round(dep_total, 2), "Accumulated depreciation"),
               ], counter)
    cur.execute("UPDATE fixed_assets SET accum_dep = cost/life/12 * 12, last_dep=? WHERE company_id=?",
                (str(today), cid))

    # ---- a few unreconciled bank feed items
    for desc, amt, direction, days in [("Bank charges - monthly ledger fee", 28.5, "out", 6),
                                       ("EcoCash merchant settlement", 745.0, "in", 3),
                                       ("Airtime & data bundle", 45.0, "out", 2),
                                       ("Cheque deposit - Mvurwi", 1250.0, "in", 9)]:
        cur.execute("""INSERT INTO bank_txns(company_id,bank_account_id,date,description,reference,amount,direction,status,source)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (cid, usd_bank["id"], str(today - timedelta(days=days)), desc, "BANKFEED",
                     amt, direction, "unreconciled", "statement"))

    conn.commit()


def ensure_db():
    conn = connect()
    conn.executescript(SCHEMA)
    # lightweight migrations for databases created before auth existed
    ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "password_hash" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "last_login" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
    if "created_at" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
    n = conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"]
    conn.commit()
    conn.close()
    if n == 0:
        reset_and_seed("mining", demo=True)


if __name__ == "__main__":
    reset_and_seed("mining", demo=True)
    print("seeded", DB_PATH)

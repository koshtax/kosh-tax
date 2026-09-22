
import os
import io
import json
import shutil
import sqlite3
import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
import streamlit as st

try:
    from jinja2 import Template
    from weasyprint import HTML
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

from pypdf import PdfReader

# ============================================================
# KOSH-TAX — ENTERPRISE SALARY / ARREAR / TDS / FORM-16 PORTAL
# ============================================================

st.set_page_config(
    page_title="Kosh-Tax | Salary, TDS & Form-16",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_NAME = os.environ.get("KOSHTAX_DB", "tds_enterprise_master.sqlite")
APP_VERSION = "2.1.0-granular-audit-public-integrated"

logging.basicConfig(
    filename="kosh_tax.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

MONTHS = [
    "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST",
    "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
    "JANUARY", "FEBRUARY",
]

AY_OPTIONS = [
    "AY 2025-26 (FY 2024-25)",
    "AY 2026-27 (FY 2025-26)",
]

CPC_7TH_MATRIX = {
    "LEVEL 1 (GP 1800)": [18000,18500,19100,19700,20300,20900,21500,22100,22800,23500,24200,24900,25600,26400,27200],
    "LEVEL 2 (GP 1900)": [19900,20500,21100,21700,22400,23100,23800,24500,25200,26000,26800,27600,28400,29300,30200],
    "LEVEL 3 (GP 2000)": [21700,22400,23100,23800,24500,25200,26000,26800,27600,28400,29300,30200,31100,32000,33000],
    "LEVEL 4 (GP 2400)": [25500,26300,27100,27900,28700,29600,30500,31400,32300,33300,34300,35300,36400,37500,38600],
    "LEVEL 5 (GP 2800)": [29200,30100,31000,31900,32900,33900,34900,35900,37000,38100,39200,40400,41600,42800,44100],
    "LEVEL 6 (GP 4200)": [35400,36500,37600,38700,39900,41100,42300,43600,44900,46200,47600,49000,50500,52000,53600],
    "LEVEL 7 (GP 4600)": [44900,46200,47600,49000,50500,52000,53600,55200,56900,58600,60400,62200,64100,66000,68000],
    "LEVEL 8 (GP 4800)": [47600,49000,50500,52000,53600,55200,56900,58600,60400,62200,64100,66000,68000,70000,72100],
    "LEVEL 9 (GP 5400)": [53100,54700,56300,58000,59700,61500,63300,65200,67200,69200,71300,73400,75600,77900,80200],
    "LEVEL 10 (GP 5400)": [56100,57800,59500,61300,63100,65000,67000,69000,71100,73200,75400,77700,80000,82400,84900],
    "LEVEL 11 (GP 6600)": [67700,69700,71800,74000,76200,78500,80900,83300,85800,88400,91100,93800,96600,99500,102500],
    "LEVEL 12 (GP 7600)": [78800,81200,83600,86100,88700,91400,94100,96900,99800,102800,105900,109100,112400,115800,119300],
}

JHARKHAND_BLOCK_DISTRICT_MAP = {
    "KHUNTI": ["KHUNTI", "ARKI", "TORPA", "MURHU", "RANIA", "KARRA"],
    "RANCHI": ["RANCHI", "BUNDU", "ORMANJHI", "KANKA", "NAGRI", "RATU", "SILLI", "ANGARA", "BERO", "BURMU", "CHANHO", "ITKI", "KHELARI", "LAPUNG", "MANDAR", "NAMKUM", "RAHE", "SONAHATU", "TAMAR"],
}

DEFAULT_TAX_RULES = {
    "AY 2025-26 (FY 2024-25)": {
        "financial_year": "FY 2024-25",
        "assessment_year": "AY 2025-26",
        "default_regime": "NEW REGIME",
        "standard_deduction_new": 75000.0,
        "standard_deduction_old": 50000.0,
        "rebate_limit_new": 700000.0,
        "rebate_max_new": 25000.0,
        "rebate_limit_old": 500000.0,
        "rebate_max_old": 12500.0,
        "cess_rate": 0.04,
        "new_slabs": [[0, 300000, 0.00], [300000, 600000, 0.05], [600000, 900000, 0.10], [900000, 1200000, 0.15], [1200000, 1500000, 0.20], [1500000, 999999999999, 0.30]],
        "old_slabs": [[0, 250000, 0.00], [250000, 500000, 0.05], [500000, 1000000, 0.20], [1000000, 999999999999, 0.30]],
    },
    "AY 2026-27 (FY 2025-26)": {
        "financial_year": "FY 2025-26",
        "assessment_year": "AY 2026-27",
        "default_regime": "NEW REGIME",
        "standard_deduction_new": 75000.0,
        "standard_deduction_old": 50000.0,
        "rebate_limit_new": 1200000.0,
        "rebate_max_new": 60000.0,
        "rebate_limit_old": 500000.0,
        "rebate_max_old": 12500.0,
        "cess_rate": 0.04,
        "new_slabs": [[0, 400000, 0.00], [400000, 800000, 0.05], [800000, 1200000, 0.10], [1200000, 1600000, 0.15], [1600000, 2000000, 0.20], [2000000, 2400000, 0.25], [2400000, 999999999999, 0.30]],
        "old_slabs": [[0, 250000, 0.00], [250000, 500000, 0.05], [500000, 1000000, 0.20], [1000000, 999999999999, 0.30]],
    },
}

TX_COLUMNS = [
    "id", "yearly_record_id", "financial_year", "assessment_year",
    "transaction_type", "payment_month", "payment_date", "bill_number",
    "bill_date", "original_salary_month", "original_salary_year",
    "original_period_from", "original_period_to", "arrear_type",
    "basic", "da", "hra", "medical", "other_allowance",
    "da_arrear", "pay_arrear", "hra_arrear", "medical_arrear",
    "other_arrear", "gross", "gpf", "nps", "gis", "professional_tax",
    "tds", "other_deduction", "recovery", "net", "remarks",
    "source_reference", "created_at", "updated_at", "created_by",
    "updated_by", "status",
]

MONEY_FIELDS = [
    "basic", "da", "hra", "medical", "other_allowance",
    "da_arrear", "pay_arrear", "hra_arrear", "medical_arrear",
    "other_arrear", "gross", "gpf", "nps", "gis", "professional_tax",
    "tds", "other_deduction", "recovery", "net",
]

COMPONENT_FIELDS = [
    "basic", "da", "hra", "medical", "other_allowance",
    "da_arrear", "pay_arrear", "hra_arrear", "medical_arrear",
    "other_arrear",
]

DEDUCTION_FIELDS = [
    "gpf", "nps", "gis", "professional_tax", "tds",
    "other_deduction", "recovery",
]

# --------------------------- generic helpers ---------------------------

def money(value):
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        if isinstance(value, str) and not value.strip():
            return 0.0
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid numeric value: {value!r}")

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

def row_to_dict(cursor, row):
    if row is None:
        return None
    names = [d[0] for d in cursor.description]
    return dict(zip(names, row))

def db_connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def backup_db():
    if not os.path.exists(DB_NAME):
        return None
    backup_name = f"backup_{os.path.basename(DB_NAME)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite"
    shutil.copy2(DB_NAME, backup_name)
    return backup_name

def get_setting(key, default=""):
    try:
        with db_connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default
    except Exception:
        return default

def set_setting(key, value):
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO app_settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()

def get_tax_rules(ay):
    rules = DEFAULT_TAX_RULES.get(ay)
    if rules is None:
        raise ValueError(f"No tax configuration exists for {ay}. Finalization is blocked.")
    return rules

def calculate_gross(row):
    return round(sum(money(row.get(k, 0)) for k in COMPONENT_FIELDS), 2)

def calculate_net(row, gross=None):
    gross = calculate_gross(row) if gross is None else money(gross)
    return round(gross - sum(money(row.get(k, 0)) for k in DEDUCTION_FIELDS), 2)

def get_quarter_from_date(date_str):
    if not date_str or not str(date_str).strip():
        return None
    try:
        dt = pd.to_datetime(date_str)
        m = dt.month
        if m in [4, 5, 6]:
            return "Q1"
        elif m in [7, 8, 9]:
            return "Q2"
        elif m in [10, 11, 12]:
            return "Q3"
        elif m in [1, 2, 3]:
            return "Q4"
    except Exception:
        pass
    return None

def get_month_name_from_date(date_str):
    if not date_str or not str(date_str).strip():
        return None
    try:
        dt = pd.to_datetime(date_str)
        return dt.strftime("%B").upper()
    except Exception:
        pass
    return None

def normalize_transaction(row, fy_rules):
    d = dict(row)
    d["status"] = str(d.get("status", "ACTIVE") or "ACTIVE").upper()
    d["transaction_type"] = str(d.get("transaction_type", "REGULAR") or "REGULAR").upper()
    d["payment_month"] = str(d.get("payment_month", "") or "").upper().strip()
    d["financial_year"] = d.get("financial_year") or fy_rules["financial_year"]
    d["assessment_year"] = d.get("assessment_year") or fy_rules["assessment_year"]
    for k in MONEY_FIELDS:
        d[k] = money(d.get(k, 0))
    d["gross"] = calculate_gross(d)
    d["net"] = calculate_net(d, d["gross"])
    return d

# --------------------------- database initialization ---------------------------

def init_db():
    if os.path.exists(DB_NAME):
        try:
            backup_db()
        except Exception as exc:
            logging.exception("Database backup failed")
            raise RuntimeError(f"Database backup failed; startup aborted: {exc}")

    conn = sqlite3.connect(DB_NAME)
    try:
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS app_settings(
            key TEXT PRIMARY KEY, value TEXT)""")

        defaults = {
            "admin_username": "admin",
            "admin_password": "change-this-password",
            "app_version": APP_VERSION,
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (k, v))

        c.execute("""CREATE TABLE IF NOT EXISTS ddo_masters(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL DEFAULT 'JHARKHAND',
            district TEXT NOT NULL DEFAULT 'KHUNTI',
            department TEXT NOT NULL DEFAULT 'SCHOOL EDUCATION & LITERACY',
            officer_name TEXT NOT NULL DEFAULT '',
            father_name TEXT NOT NULL DEFAULT '',
            tan TEXT UNIQUE NOT NULL,
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            pincode TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_master_profiles(
            pan TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            designation TEXT NOT NULL,
            mobile TEXT DEFAULT '',
            email TEXT DEFAULT '',
            gpf_no TEXT DEFAULT '',
            last_pay_level TEXT DEFAULT '',
            last_basic_pay REAL DEFAULT 0,
            updated_at TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_yearly_records(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ay TEXT NOT NULL,
            ddo_id INTEGER,
            pan TEXT NOT NULL,
            name TEXT NOT NULL,
            designation TEXT NOT NULL,
            office_name TEXT NOT NULL,
            service_status TEXT DEFAULT 'NORMAL',
            pay_level TEXT DEFAULT '',
            employer_type TEXT DEFAULT 'STATE GOVERNMENT',
            pension_type TEXT DEFAULT 'GPF',
            tax_regime TEXT DEFAULT 'NEW REGIME',
            payment_status TEXT DEFAULT 'PENDING',
            payment_mode TEXT DEFAULT '',
            utr_no TEXT DEFAULT '',
            amount_paid REAL DEFAULT 0,
            created_at TEXT DEFAULT '',
            UNIQUE(ay, pan))""")

        c.execute("""CREATE TABLE IF NOT EXISTS salary_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yearly_record_id INTEGER NOT NULL,
            financial_year TEXT NOT NULL,
            assessment_year TEXT NOT NULL,
            transaction_type TEXT DEFAULT 'REGULAR',
            payment_month TEXT DEFAULT '',
            payment_date TEXT DEFAULT '',
            bill_number TEXT DEFAULT '',
            bill_date TEXT DEFAULT '',
            original_salary_month TEXT DEFAULT '',
            original_salary_year TEXT DEFAULT '',
            original_period_from TEXT DEFAULT '',
            original_period_to TEXT DEFAULT '',
            arrear_type TEXT DEFAULT '',
            basic REAL DEFAULT 0,
            da REAL DEFAULT 0,
            hra REAL DEFAULT 0,
            medical REAL DEFAULT 0,
            other_allowance REAL DEFAULT 0,
            da_arrear REAL DEFAULT 0,
            pay_arrear REAL DEFAULT 0,
            hra_arrear REAL DEFAULT 0,
            medical_arrear REAL DEFAULT 0,
            other_arrear REAL DEFAULT 0,
            gross REAL DEFAULT 0,
            gpf REAL DEFAULT 0,
            nps REAL DEFAULT 0,
            gis REAL DEFAULT 0,
            professional_tax REAL DEFAULT 0,
            tds REAL DEFAULT 0,
            other_deduction REAL DEFAULT 0,
            recovery REAL DEFAULT 0,
            net REAL DEFAULT 0,
            remarks TEXT DEFAULT '',
            source_reference TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            updated_by TEXT DEFAULT '',
            status TEXT DEFAULT 'ACTIVE',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS transaction_audit_trail(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            yearly_record_id INTEGER,
            action_type TEXT NOT NULL,
            old_values TEXT,
            new_values TEXT,
            changed_by TEXT DEFAULT '',
            changed_at TEXT NOT NULL,
            reason TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_tax_declarations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yearly_record_id INTEGER UNIQUE,
            other_employer_salary REAL DEFAULT 0,
            house_property_loss REAL DEFAULT 0,
            bank_interest REAL DEFAULT 0,
            other_income REAL DEFAULT 0,
            relief_89 REAL DEFAULT 0,
            sec80c REAL DEFAULT 0,
            sec80d REAL DEFAULT 0,
            sec80e REAL DEFAULT 0,
            sec80g REAL DEFAULT 0,
            sec80tta REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS tds_deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yearly_record_id INTEGER NOT NULL,
            quarter TEXT NOT NULL,
            month_name TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            deposit_date TEXT DEFAULT '',
            mode TEXT DEFAULT 'Challan',
            bsr_code TEXT DEFAULT '',
            challan_serial TEXT DEFAULT '',
            bin TEXT DEFAULT '',
            receipt_no TEXT DEFAULT '',
            ddo_serial_no TEXT DEFAULT '',
            form24g_no TEXT DEFAULT '',
            voucher_date TEXT DEFAULT '',
            remarks TEXT DEFAULT '',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        # Legacy migration
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monthly_salary_ledgers'")
        legacy_exists = c.fetchone() is not None
        if legacy_exists:
            migrated = c.execute(
                "SELECT COUNT(*) FROM salary_transactions WHERE source_reference='LEGACY_MIGRATION'"
            ).fetchone()[0]
            if migrated == 0:
                cols = [x[1] for x in c.execute("PRAGMA table_info(monthly_salary_ledgers)").fetchall()]
                required = {"yearly_record_id","month_name","basic_pay","da","hra","medical","arrear_da","arrear_pay","gross","gpf","gis","ptax","tds","net"}
                if required.issubset(set(cols)):
                    rows = c.execute("""SELECT yearly_record_id,month_name,basic_pay,da,hra,medical,
                        arrear_da,arrear_pay,gross,gpf,gis,ptax,tds,net
                        FROM monthly_salary_ledgers""").fetchall()
                    for r in rows:
                        yid,m,b,d,h,med,ada,apa,g,gpf,gis,ptax,tds,net = r
                        ayrow = c.execute("SELECT ay FROM employee_yearly_records WHERE id=?", (yid,)).fetchone()
                        ay = ayrow[0] if ayrow else AY_OPTIONS[0]
                        rules = get_tax_rules(ay)
                        needs_review = bool(ada or apa)
                        c.execute("""INSERT INTO salary_transactions(
                            yearly_record_id,financial_year,assessment_year,transaction_type,
                            payment_month,basic,da,hra,medical,da_arrear,pay_arrear,gross,
                            gpf,gis,professional_tax,tds,net,remarks,source_reference,
                            created_at,status)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (yid,rules["financial_year"],rules["assessment_year"],"REGULAR",
                             str(m or "").upper(),b or 0,d or 0,h or 0,med or 0,ada or 0,apa or 0,
                             g or 0,gpf or 0,gis or 0,ptax or 0,tds or 0,net or 0,
                             "LEGACY_MIGRATION - NEEDS_REVIEW: arrear original period not recoverable"
                             if needs_review else "LEGACY_MIGRATION",
                             "LEGACY_MIGRATION",now_text(),
                             "NEEDS_REVIEW" if needs_review else "ACTIVE"))
        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Database initialization failed")
        raise
    finally:
        conn.close()

# --------------------------- validation ---------------------------

def validate_transactions(transactions):
    errors, warnings = [], []
    active = [t for t in transactions if str(t.get("status","ACTIVE")).upper() == "ACTIVE"]

    if not active:
        errors.append("No ACTIVE salary/arrear transaction exists.")

    seen_bills = {}
    regular_months = set()

    for i, tx in enumerate(active, 1):
        label = f"Row {i}"
        ttype = str(tx.get("transaction_type","REGULAR")).upper()

        p_date = tx.get("payment_date")
        p_month = str(tx.get("payment_month","") or "").upper().strip()
        if p_date and str(p_date).strip():
            derived_m = get_month_name_from_date(p_date)
            if derived_m and p_month and derived_m != p_month:
                errors.append(f"{label}: Payment month ({p_month}) conflicts with payment date month ({derived_m}).")

        gross_calc = calculate_gross(tx)
        net_calc = calculate_net(tx, gross_calc)

        if any(money(tx.get(k,0)) < 0 for k in MONEY_FIELDS):
            errors.append(f"{label}: Negative monetary value detected.")

        if abs(gross_calc - money(tx.get("gross",0))) > 0.01:
            errors.append(f"{label}: Gross mismatch: calculated ₹{gross_calc:,.2f}, stored ₹{money(tx.get('gross',0)):,.2f}.")

        if abs(net_calc - money(tx.get("net",0))) > 0.01:
            errors.append(f"{label}: Net mismatch: calculated ₹{net_calc:,.2f}, stored ₹{money(tx.get('net',0)):,.2f}.")

        bill = str(tx.get("bill_number","") or "").strip().upper()
        if bill:
            if bill in seen_bills:
                errors.append(f"{label}: Duplicate bill number {bill}; also used in {seen_bills[bill]}.")
            seen_bills[bill] = label

        if ttype == "REGULAR":
            month = p_month
            if not month:
                errors.append(f"{label}: Regular salary is missing payment month.")
            elif month in regular_months:
                errors.append(f"{label}: Duplicate REGULAR salary month {month}.")
            else:
                regular_months.add(month)

        if ttype == "ARREAR":
            if not str(tx.get("original_salary_month","") or "").strip() and not str(tx.get("original_period_from","") or "").strip():
                errors.append(f"{label}: ARREAR requires original salary month or original period.")
            if not str(tx.get("original_salary_year","") or "").strip() and not str(tx.get("original_period_from","") or "").strip():
                errors.append(f"{label}: ARREAR requires original salary year or original period.")
            if not str(tx.get("payment_date","") or "").strip():
                warnings.append(f"{label}: Arrear payment date is blank.")

    missing = set(MONTHS) - regular_months
    if missing:
        warnings.append("Missing regular salary months: " + ", ".join(sorted(missing)))

    return errors, warnings

# --------------------------- independent reconciliation datasets ---------------------------

def reconcile_form_16_dataset(active_txs, tax_summary, totals, fy_rules, decl_data):
    errors = []
    ledger_gross = totals["gross"]
    if abs(tax_summary["gross"] - ledger_gross) > 0.01:
        errors.append(f"Form-16 Gross (₹{tax_summary['gross']:,.2f}) does not match Ledger Gross (₹{ledger_gross:,.2f}).")
    expected_std = float(fy_rules["standard_deduction_new"] if tax_summary["regime"]=="NEW REGIME" else fy_rules["standard_deduction_old"])
    if abs(tax_summary["std_ded"] - expected_std) > 0.01:
        errors.append(f"Form-16 Standard Deduction conflicts with configuration.")
    expected_tds = totals["tds"]
    if abs(tax_summary["tds_paid"] - expected_tds) > 0.01:
        errors.append(f"Form-16 TDS Paid does not match Ledger TDS.")
    return errors

def reconcile_schedule_dataset(active_txs, totals):
    errors = []
    tx_basic = sum(money(t.get("basic",0)) for t in active_txs)
    if abs(totals["basic"] - tx_basic) > 0.01:
        errors.append("Schedule Basic does not match transaction Basic sum.")
    tx_gross = sum(money(t.get("gross",0)) for t in active_txs)
    if abs(totals["gross"] - tx_gross) > 0.01:
        errors.append("Schedule Gross does not match transaction Gross sum.")
    return errors

def reconcile_tds(active_transactions, deposit_rows):
    errors = []
    tx_total = round(sum(money(t.get("tds",0)) for t in active_transactions), 2)
    
    # Check independently via payment dates mapped to quarters
    q_map = {"Q1":0.0, "Q2":0.0, "Q3":0.0, "Q4":0.0}
    for t in active_transactions:
        pdate = t.get("payment_date")
        q = get_quarter_from_date(pdate)
        if q in q_map:
            q_map[q] += money(t["tds"])

    deposit_q_map = {"Q1":0.0, "Q2":0.0, "Q3":0.0, "Q4":0.0}
    for row in deposit_rows:
        q = str(row["quarter"] or "").upper().strip()
        q = q.split()[0] if q else ""
        if q in deposit_q_map:
            deposit_q_map[q] += money(row["amount"])

    dep_total = round(sum(deposit_q_map.values()), 2)
    if deposit_rows and abs(tx_total - dep_total) > 0.01:
        errors.append(f"TDS Deposit mismatch: Transaction TDS ₹{tx_total:,.2f} vs Deposit Challans ₹{dep_total:,.2f}.")

    return {
        "valid": not errors,
        "errors": errors,
        "transaction_tds": tx_total,
        "deposit_total": dep_total,
        "quarters_tx": q_map,
        "quarters_dep": deposit_q_map,
    }

# --------------------------- tax engine ---------------------------

def tax_engine(active_transactions, regime, declarations, rules):
    gross_salary = round(sum(money(t.get("gross",0)) for t in active_transactions), 2)
    tds_paid = round(sum(money(t.get("tds",0)) for t in active_transactions), 2)

    other_employer = money(declarations.get("other_employer_salary",0))
    house_loss = money(declarations.get("house_property_loss",0))
    other_income = money(declarations.get("bank_interest",0)) + money(declarations.get("other_income",0))
    relief_89 = money(declarations.get("relief_89",0))

    gross_total_income = round(gross_salary + other_employer + other_income - house_loss, 2)

    regime = regime.upper()
    if regime == "NEW REGIME":
        standard_deduction = money(rules["standard_deduction_new"])
        chapter_vi_a = 0.0
        slabs = rules["new_slabs"]
        rebate_limit = money(rules["rebate_limit_new"])
        rebate_max = money(rules["rebate_max_new"])
    else:
        standard_deduction = money(rules["standard_deduction_old"])
        c80c = min(150000.0, money(declarations.get("sec80c",0)))
        c80d = min(50000.0, money(declarations.get("sec80d",0)))
        c80e = money(declarations.get("sec80e",0))
        c80g = money(declarations.get("sec80g",0))
        c80tta = min(10000.0, money(declarations.get("sec80tta",0)))
        chapter_vi_a = c80c + c80d + c80e + c80g + c80tta
        slabs = rules["old_slabs"]
        rebate_limit = money(rules["rebate_limit_old"])
        rebate_max = money(rules["rebate_max_old"])

    taxable_income = max(0.0, gross_total_income - standard_deduction - chapter_vi_a)
    taxable_income = float(Decimal(str(taxable_income)).quantize(Decimal("10"), rounding=ROUND_HALF_UP))

    slab_details = []
    slab_tax = 0.0
    for lower, upper, rate in slabs:
        if taxable_income <= lower:
            continue
        taxable_part = taxable_income - lower if upper >= 999999999999 else min(taxable_income, upper) - lower
        taxable_part = max(0.0, taxable_part)
        amount = round(taxable_part * rate, 2)
        slab_tax += amount
        slab_details.append({
            "from": lower, "to": None if upper >= 999999999999 else upper,
            "rate": rate, "taxable_amount": taxable_part, "tax": amount
        })

    rebate = min(slab_tax, rebate_max) if taxable_income <= rebate_limit else 0.0
    tax_after_rebate = max(0.0, slab_tax - rebate)
    cess = round(tax_after_rebate * money(rules["cess_rate"]), 2)
    total_tax = max(0.0, tax_after_rebate + cess - relief_89)
    balance = round(total_tax - tds_paid, 2)

    arrears = round(sum(
        money(t.get("da_arrear",0)) + money(t.get("pay_arrear",0)) +
        money(t.get("hra_arrear",0)) + money(t.get("medical_arrear",0)) +
        money(t.get("other_arrear",0)) for t in active_transactions
    ), 2)

    totals = {
        "basic": round(sum(money(t.get("basic",0)) for t in active_transactions),2),
        "da": round(sum(money(t.get("da",0)) for t in active_transactions),2),
        "hra": round(sum(money(t.get("hra",0)) for t in active_transactions),2),
        "medical": round(sum(money(t.get("medical",0)) for t in active_transactions),2),
        "arrear": arrears,
        "gross": gross_salary,
        "gpf": round(sum(money(t.get("gpf",0)) for t in active_transactions),2),
        "nps": round(sum(money(t.get("nps",0)) for t in active_transactions),2),
        "gis": round(sum(money(t.get("gis",0)) for t in active_transactions),2),
        "ptax": round(sum(money(t.get("professional_tax",0)) for t in active_transactions),2),
        "tds": tds_paid,
        "net": round(sum(money(t.get("net",0)) for t in active_transactions),2),
    }

    tax = {
        "regime": regime,
        "gross": gross_salary,
        "gross_total_income": gross_total_income,
        "standard_deduction": standard_deduction,
        "std_ded": standard_deduction,
        "chapter_vi_a": chapter_vi_a,
        "taxable_income": taxable_income,
        "slab_details": slab_details,
        "slab_tax": round(slab_tax,2),
        "rebate_87a": round(rebate,2),
        "cess": cess,
        "relief_89": relief_89,
        "total_tax": round(total_tax,2),
        "tds_paid": tds_paid,
        "net_balance": balance,
        "financial_year": rules["financial_year"],
        "assessment_year": rules["assessment_year"],
    }
    return totals, tax

# --------------------------- audit persistence ---------------------------

def audit_insert(conn, tx_id, yid, action, old_values=None, new_values=None, reason=""):
    conn.execute(
        """INSERT INTO transaction_audit_trail
        (transaction_id,yearly_record_id,action_type,old_values,new_values,changed_by,changed_at,reason)
        VALUES(?,?,?,?,?,?,?,?)""",
        (
            tx_id, yid, action,
            json.dumps(old_values, default=json_default, sort_keys=True) if old_values is not None else None,
            json.dumps(new_values, default=json_default, sort_keys=True) if new_values is not None else None,
            st.session_state.get("actor","USER"),
            now_text(), reason
        )
    )

def save_transactions(yid, edited_df, fy_rules):
    proposed = []
    for _, row in edited_df.iterrows():
        d = normalize_transaction(dict(row), fy_rules)
        proposed.append(d)

    # STRICT VALIDATION GATE BEFORE DATABASE TRANSACTION COMMITS
    errors, warnings = validate_transactions(proposed)
    if errors:
        return False, errors, warnings

    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE")

        valid_ids = {
            int(r["id"]) for r in conn.execute(
                "SELECT id FROM salary_transactions WHERE yearly_record_id=?",
                (yid,)
            ).fetchall()
        }

        submitted_ids = set()
        for tx in proposed:
            if tx.get("id") not in (None, "", 0) and not pd.isna(tx.get("id")):
                tid = int(tx["id"])
                submitted_ids.add(tid)
                if tid not in valid_ids:
                    raise RuntimeError(f"Security violation: transaction {tid} does not belong to current employee/FY.")

        # Removed UI rows become VOID with field-level audit trails
        for tid in sorted(valid_ids - submitted_ids):
            old = conn.execute("SELECT * FROM salary_transactions WHERE id=?", (tid,)).fetchone()
            if old and str(old["status"]).upper() != "VOID":
                old_dict = dict(old)
                new_dict = dict(old_dict)
                new_dict["status"] = "VOID"
                conn.execute(
                    "UPDATE salary_transactions SET status='VOID',updated_at=?,updated_by=? WHERE id=? AND yearly_record_id=?",
                    (now_text(), st.session_state.get("actor","USER"), tid, yid)
                )
                audit_insert(conn, tid, yid, "VOID", old_dict, new_dict, "Removed from spreadsheet editor")

        update_sql = """UPDATE salary_transactions SET
            financial_year=?,assessment_year=?,transaction_type=?,payment_month=?,payment_date=?,
            bill_number=?,bill_date=?,original_salary_month=?,original_salary_year=?,
            original_period_from=?,original_period_to=?,arrear_type=?,basic=?,da=?,hra=?,medical=?,
            other_allowance=?,da_arrear=?,pay_arrear=?,hra_arrear=?,medical_arrear=?,other_arrear=?,
            gross=?,gpf=?,nps=?,gis=?,professional_tax=?,tds=?,other_deduction=?,recovery=?,net=?,
            remarks=?,source_reference=?,updated_at=?,updated_by=?,status=?
            WHERE id=? AND yearly_record_id=?"""

        insert_sql = """INSERT INTO salary_transactions(
            yearly_record_id,financial_year,assessment_year,transaction_type,payment_month,payment_date,
            bill_number,bill_date,original_salary_month,original_salary_year,original_period_from,
            original_period_to,arrear_type,basic,da,hra,medical,other_allowance,da_arrear,pay_arrear,
            hra_arrear,medical_arrear,other_arrear,gross,gpf,nps,gis,professional_tax,tds,
            other_deduction,recovery,net,remarks,source_reference,created_at,created_by,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""

        for tx in proposed:
            tid = tx.get("id")
            params = (
                tx.get("financial_year"), tx.get("assessment_year"), tx.get("transaction_type"),
                tx.get("payment_month"), tx.get("payment_date",""), tx.get("bill_number",""),
                tx.get("bill_date",""), tx.get("original_salary_month",""), tx.get("original_salary_year",""),
                tx.get("original_period_from",""), tx.get("original_period_to",""), tx.get("arrear_type",""),
                *[tx.get(k,0) for k in [
                    "basic","da","hra","medical","other_allowance","da_arrear","pay_arrear",
                    "hra_arrear","medical_arrear","other_arrear","gross","gpf","nps","gis",
                    "professional_tax","tds","other_deduction","recovery","net"
                ]],
                tx.get("remarks",""), tx.get("source_reference",""),
                now_text(), st.session_state.get("actor","USER"), tx.get("status","ACTIVE")
            )
            if tid not in (None, "", 0) and not pd.isna(tid):
                tid = int(tid)
                old = conn.execute("SELECT * FROM salary_transactions WHERE id=? AND yearly_record_id=?", (tid,yid)).fetchone()
                if old is None:
                    raise RuntimeError(f"Transaction {tid} disappeared during save.")
                old_dict = dict(old)
                conn.execute(update_sql, params + (tid, yid))
                new_dict = dict(tx)
                audit_insert(conn, tid, yid, "UPDATE", old_dict, new_dict)
            else:
                conn.execute(
                    insert_sql,
                    (yid, *params)
                )
                new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                audit_insert(conn, new_id, yid, "INSERT", None, dict(tx))

        conn.commit()
        return True, [], warnings
    except Exception as exc:
        conn.rollback()
        logging.exception("Transaction save failed")
        return False, [f"Database transaction rolled back: {exc}"], warnings
    finally:
        conn.close()

# --------------------------- PDF ---------------------------

HTML_TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page { size:A4 portrait; margin:8mm; }
@page ledger { size:A4 landscape; margin:6mm; }
body { font-family: DejaVu Sans, Arial, sans-serif; font-size:9px; color:#000; }
.page { page-break-after:always; }
.ledger { page:ledger; }
h1,h2,h3 { text-align:center; margin:3px 0; }
table { width:100%; border-collapse:collapse; margin:4px 0; }
th,td { border:0.5px solid #000; padding:3px; }
.right { text-align:right; }
.center { text-align:center; }
.bold { font-weight:bold; }
.note { border:1px solid #000; padding:5px; margin:5px 0; }
</style>
</head>
<body>
<div class="page">
<h2>T.D.S. FORM NO. 16 — PART A</h2>
<table>
<tr><td><b>EMPLOYER</b></td><td>{{ ddo.department }}, {{ ddo.district }}</td></tr>
<tr><td><b>TAN</b></td><td>{{ ddo.tan }}</td></tr>
<tr><td><b>EMPLOYEE</b></td><td>{{ emp.name }}</td></tr>
<tr><td><b>PAN</b></td><td>{{ emp.pan }}</td></tr>
<tr><td><b>ASSESSMENT YEAR</b></td><td>{{ emp.ay }}</td></tr>
</table>
{% if is_trial %}<div class="note center"><b>TRIAL COPY — FOR VERIFICATION ONLY</b></div>{% endif %}
</div>

<div class="page">
<h2>FORM 16 — PART B / TAX COMPUTATION</h2>
<table>
<tr><td>Gross Salary</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
<tr><td>Standard Deduction</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
<tr><td>Chapter VI-A</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
<tr><td>Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
<tr><td>Tax before Rebate</td><td class="right">{{ "%.2f"|format(tax.slab_tax) }}</td></tr>
<tr><td>Rebate</td><td class="right">{{ "%.2f"|format(tax.rebate_87a) }}</td></tr>
<tr><td>Cess</td><td class="right">{{ "%.2f"|format(tax.cess) }}</td></tr>
<tr><td>Relief u/s 89</td><td class="right">{{ "%.2f"|format(tax.relief_89) }}</td></tr>
<tr class="bold"><td>Total Tax</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
<tr><td>TDS Paid</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
<tr class="bold"><td>Balance Payable / (Refund)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
</table>
</div>

<div class="page">
<h2>SCHEDULE OF INCOME / TAX RECONCILIATION</h2>
<table>
<tr><th>Description</th><th>Amount</th></tr>
<tr><td>Gross Salary</td><td class="right">{{ "%.2f"|format(totals.gross) }}</td></tr>
<tr><td>Standard Deduction</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
<tr><td>Chapter VI-A</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
<tr><td>Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
<tr><td>Total Tax</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
<tr><td>TDS Paid</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
</table>
<div class="note">This schedule is generated only after passing strict validation, independent Form-16, Schedule and TDS deposit reconciliation gates.</div>
</div>

<div class="ledger">
<h2>MONTHLY SALARY & TRANSACTION LEDGER</h2>
<table>
<tr>
<th>TYPE</th><th>PAYMENT MONTH</th><th>BILL</th><th>ORIGINAL PERIOD</th>
<th>BASIC</th><th>DA</th><th>HRA</th><th>MEDICAL</th><th>ARREARS</th>
<th>GROSS</th><th>GPF/NPS</th><th>GIS</th><th>PTAX</th><th>TDS</th><th>NET</th>
</tr>
{% for r in records %}
<tr>
<td>{{ r.transaction_type }}</td><td>{{ r.payment_month }}</td><td>{{ r.bill_number or "-" }}</td>
<td>{{ r.original_period_from or r.original_salary_month }} {{ r.original_salary_year }}</td>
<td class="right">{{ "%.2f"|format(r.basic) }}</td><td class="right">{{ "%.2f"|format(r.da) }}</td>
<td class="right">{{ "%.2f"|format(r.hra) }}</td><td class="right">{{ "%.2f"|format(r.medical) }}</td>
<td class="right">{{ "%.2f"|format(r.da_arrear+r.pay_arrear+r.hra_arrear+r.medical_arrear+r.other_arrear) }}</td>
<td class="right">{{ "%.2f"|format(r.gross) }}</td>
<td class="right">{{ "%.2f"|format(r.gpf+r.nps) }}</td><td class="right">{{ "%.2f"|format(r.gis) }}</td>
<td class="right">{{ "%.2f"|format(r.professional_tax) }}</td><td class="right">{{ "%.2f"|format(r.tds) }}</td>
<td class="right">{{ "%.2f"|format(r.net) }}</td>
</tr>
{% endfor %}
<tr class="bold">
<td colspan="4">TOTAL</td><td class="right">{{ "%.2f"|format(totals.basic) }}</td>
<td class="right">{{ "%.2f"|format(totals.da) }}</td><td class="right">{{ "%.2f"|format(totals.hra) }}</td>
<td class="right">{{ "%.2f"|format(totals.medical) }}</td><td class="right">{{ "%.2f"|format(totals.arrear) }}</td>
<td class="right">{{ "%.2f"|format(totals.gross) }}</td><td class="right">{{ "%.2f"|format(totals.gpf+totals.nps) }}</td>
<td class="right">{{ "%.2f"|format(totals.gis) }}</td><td class="right">{{ "%.2f"|format(totals.ptax) }}</td>
<td class="right">{{ "%.2f"|format(totals.tds) }}</td><td class="right">{{ "%.2f"|format(totals.net) }}</td>
</tr>
</table>
</div>
</body>
</html>
"""

def generate_pdf(ddo, emp, records, tax, totals, is_trial=False):
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF dependencies unavailable. Install jinja2 and weasyprint.")
    html = Template(HTML_TEMPLATE).render(
        ddo=ddo, emp=emp, records=records, tax=tax, totals=totals,
        is_trial=is_trial,
    )
    return HTML(string=html).write_pdf()

# --------------------------- UI helpers ---------------------------

def require_admin():
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False
    if st.session_state.admin_logged_in:
        return True
    with st.form("admin_login"):
        u = st.text_input("Admin username")
        p = st.text_input("Admin password", type="password")
        ok = st.form_submit_button("Authenticate")
    if ok:
        if u == get_setting("admin_username","admin") and p == get_setting("admin_password","change-this-password"):
            st.session_state.admin_logged_in = True
            st.session_state.actor = u
            st.rerun()
        st.error("Invalid admin credentials.")
    return False

def load_transactions(yid):
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM salary_transactions WHERE yearly_record_id=? AND status='ACTIVE' ORDER BY id",
            (yid,)
        ).fetchall()
        return [dict(r) for r in rows]

def ensure_employee(ay, pan):
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM employee_yearly_records WHERE ay=? AND pan=?", (ay,pan)).fetchone()
        return dict(row) if row else None

def initialize_employee(ay, pan):
    rules = get_tax_rules(ay)
    with db_connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO employee_yearly_records
            (ay,pan,name,designation,office_name,tax_regime,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (ay,pan,"NEW EMPLOYEE","CLERK","DEFAULT SCHOOL",rules["default_regime"],now_text())
        )
        conn.commit()

def get_declarations(yid):
    with db_connect() as conn:
        r = conn.execute("SELECT * FROM employee_tax_declarations WHERE yearly_record_id=?", (yid,)).fetchone()
        return dict(r) if r else {}

def get_tds_deposits(yid):
    with db_connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM tds_deposits WHERE yearly_record_id=? ORDER BY id",(yid,)
        ).fetchall()]

# --------------------------- main employee UI ---------------------------

def render_employee():
    st.subheader("📊 Spreadsheet Salary & Transaction Register")
    st.caption("Each salary/arrear bill is stored as an independent transaction. No consolidation of separate bills.")

    pan = st.text_input("PAN", placeholder="ABCDE1234F").strip().upper()
    if len(pan) != 10:
        st.info("Enter a valid 10-character PAN to load/create the yearly ledger.")
        return

    record = ensure_employee(GLOBAL_AY, pan)
    if record is None:
        if st.button("Initialize New Employee Yearly Ledger"):
            initialize_employee(GLOBAL_AY, pan)
            st.rerun()
        return

    yid = record["id"]
    rules = get_tax_rules(GLOBAL_AY)

    st.success(f"Employee record ID: {yid} | FY: {rules['financial_year']} | AY: {rules['assessment_year']}")

    with st.expander("👤 Employee Master / Yearly Profile", expanded=False):
        c1,c2,c3 = st.columns(3)
        name = c1.text_input("Name", value=record["name"])
        designation = c2.text_input("Designation", value=record["designation"])
        office = c3.text_input("Office", value=record["office_name"])
        regime = st.selectbox("Tax Regime", ["NEW REGIME","OLD REGIME"],
                              index=0 if record["tax_regime"]=="NEW REGIME" else 1)
        if st.button("Save Employee Profile"):
            with db_connect() as conn:
                conn.execute(
                    "UPDATE employee_yearly_records SET name=?,designation=?,office_name=?,tax_regime=? WHERE id=?",
                    (name,designation,office,regime,yid)
                )
                conn.commit()
            st.success("Profile saved.")
            st.rerun()

    active = load_transactions(yid)
    if active:
        df = pd.DataFrame(active)
    else:
        df = pd.DataFrame(columns=TX_COLUMNS)

    display_cols = [
        "id","transaction_type","payment_month","payment_date","bill_number","bill_date",
        "original_salary_month","original_salary_year","original_period_from","original_period_to",
        "arrear_type","basic","da","hra","medical","other_allowance",
        "da_arrear","pay_arrear","hra_arrear","medical_arrear","other_arrear",
        "gpf","nps","gis","professional_tax","tds","other_deduction","recovery",
        "remarks","source_reference"
    ]
    for col in display_cols:
        if col not in df.columns:
            df[col] = "" if col not in MONEY_FIELDS else 0.0

    edited = st.data_editor(
        df[display_cols],
        num_rows="dynamic",
        use_container_width=True,
        key="salary_transaction_editor",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "transaction_type": st.column_config.SelectboxColumn("Type", options=["REGULAR","ARREAR","RECOVERY","ADJUSTMENT","OTHER"]),
            "payment_month": st.column_config.SelectboxColumn("Payment Month", options=MONTHS),
            "original_salary_month": st.column_config.SelectboxColumn("Original Month", options=[""]+MONTHS),
        },
    )

    if st.button("💾 Save Ledger Transactions & Validate", type="primary"):
        ok, errors, warnings = save_transactions(yid, edited, rules)
        if not ok:
            st.error("❌ SAVE BLOCKED — NO DATABASE COMMIT OR TAX CALCULATION OCCURRED.")
            for e in errors:
                st.write("•", e)
            return

        for w in warnings:
            st.warning(w)
        st.success("Database transaction committed with audit trail.")

        # Re-read authoritative ACTIVE state
        active = load_transactions(yid)
        errors, warnings2 = validate_transactions(active)
        if errors:
            st.error("❌ AUTHORITATIVE VALIDATION FAILED — FINALIZATION BLOCKED.")
            for e in errors:
                st.write("•", e)
            return

        declarations = get_declarations(yid)
        totals, tax = tax_engine(active, record["tax_regime"], declarations, rules)

        deposits = get_tds_deposits(yid)
        tds_rec = reconcile_tds(active, deposits, strict_quarters=True)

        form16_errs = reconcile_form_16_dataset(active, tax, totals, rules, declarations)
        schedule_errs = reconcile_schedule_dataset(active, totals)
        all_recon_errors = form16_errs + schedule_errs + tds_rec["errors"]

        if all_recon_errors:
            st.error("🔒 FINALIZATION BLOCKED — INDEPENDENT RECONCILIATION GATES FAILED.")
            for e in all_recon_errors:
                st.write("•", e)
            return

        st.success("✅ All strict validation and independent reconciliation gates passed.")

        ddo = get_ddo()
        emp = {
            "ay": rules["assessment_year"],
            "pan": pan,
            "name": record["name"],
            "designation": record["designation"],
            "office_name": record["office_name"],
        }
        try:
            pdf = generate_pdf(ddo, emp, active, tax, totals, is_trial=False)
            st.download_button(
                "📥 Download Final Audit-Ready PDF Bundle",
                pdf,
                f"FORM16_{pan}_{rules['assessment_year'].replace(' ','_')}.pdf",
                "application/pdf",
            )
        except Exception as exc:
            logging.exception("PDF generation failed")
            st.error(f"PDF generation failed; no document was produced: {exc}")

    st.divider()
    st.subheader("🧾 Tax / TDS Preview")
    active = load_transactions(yid)
    if active:
        declarations = get_declarations(yid)
        totals, tax = tax_engine(active, record["tax_regime"], declarations, rules)
        deposits = get_tds_deposits(yid)
        tds_rec = reconcile_tds(active, deposits, strict_quarters=False)
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Gross Salary", f"₹{totals['gross']:,.2f}")
        c2.metric("TDS", f"₹{totals['tds']:,.2f}")
        c3.metric("Taxable Income", f"₹{tax['taxable_income']:,.2f}")
        c4.metric("Tax Liability", f"₹{tax['total_tax']:,.2f}")
        st.json({
            "FY": rules["financial_year"],
            "AY": rules["assessment_year"],
            "Regime": record["tax_regime"],
            "Gross": totals["gross"],
            "Taxable Income": tax["taxable_income"],
            "Tax": tax["total_tax"],
            "TDS": tax["tds_paid"],
            "Balance": tax["net_balance"],
            "Quarter TDS (Tx derived)": tds_rec["quarters_tx"],
            "Quarter TDS (Deposit Challans)": tds_rec["quarters_dep"],
        })

# --------------------------- archive search UI ---------------------------

def render_archive():
    st.subheader("🔍 Re-Download Archive / Search")
    pan_search = st.text_input("Search PAN", key="archive_pan").strip().upper()
    if pan_search:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT id,ay,pan,name,designation,office_name,payment_status FROM employee_yearly_records WHERE pan=? ORDER BY id DESC",
                (pan_search,)
            ).fetchall()
        if rows:
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)
        else:
            st.info("No yearly record found.")

# --------------------------- admin panel ---------------------------

def get_ddo():
    with db_connect() as conn:
        r = conn.execute("SELECT * FROM ddo_masters ORDER BY id LIMIT 1").fetchone()
        if not r:
            return {
                "state":"JHARKHAND","district":"KHUNTI",
                "department":"SCHOOL EDUCATION & LITERACY",
                "officer_name":"","father_name":"","tan":"",
                "address":"","city":"KHUNTI","pincode":""
            }
        return dict(r)

def admin_panel():
    if not require_admin():
        return

    st.subheader("🔒 Admin Command Center")
    tabs = st.tabs([
        "📊 Revenue & Analytics",
        "🗃️ Master DB Manager",
        "📥 Payment Queue",
        "🏦 Statutory TDS Deposits",
        "🏛️ DDO Master",
        "⚙️ Config & Credentials",
        "🧾 Audit Trail",
    ])

    with tabs[0]:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT payment_status,amount_paid FROM employee_yearly_records WHERE ay=?",(GLOBAL_AY,)
            ).fetchall()
        approved = sum(money(r["amount_paid"]) for r in rows if str(r["payment_status"]).upper()=="APPROVED")
        st.metric("Approved Revenue", f"₹{approved:,.2f}")
        st.metric("Registered Yearly Records", len(rows))

    with tabs[1]:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT id,pan,name,designation,office_name,tax_regime,payment_status FROM employee_yearly_records WHERE ay=? ORDER BY id",
                (GLOBAL_AY,)
            ).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

    with tabs[2]:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT id,pan,name,payment_status,payment_mode,amount_paid,utr_no FROM employee_yearly_records WHERE ay=? ORDER BY id",
                (GLOBAL_AY,)
            ).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

    with tabs[3]:
        st.caption("Quarterly TDS deposit records are maintained separately from employee transaction TDS.")
        with db_connect() as conn:
            employees = conn.execute(
                "SELECT id,pan,name FROM employee_yearly_records WHERE ay=? ORDER BY id",(GLOBAL_AY,)
            ).fetchall()
        if employees:
            labels = {f"{r['id']} | {r['pan']} | {r['name']}":r["id"] for r in employees}
            label = st.selectbox("Employee", list(labels))
            yid = labels[label]
            q = st.selectbox("Quarter", ["Q1","Q2","Q3","Q4"])
            month = st.text_input("Month")
            amount = st.number_input("Amount", min_value=0.0, step=100.0)
            deposit_date = st.date_input("Deposit Date", value=date.today())
            bsr = st.text_input("BSR Code")
            challan = st.text_input("Challan Serial")
            if st.button("Add TDS Deposit"):
                with db_connect() as conn:
                    conn.execute(
                        """INSERT INTO tds_deposits(yearly_record_id,quarter,month_name,amount,deposit_date,bsr_code,challan_serial)
                           VALUES(?,?,?,?,?,?,?)""",
                        (yid,q,month,amount,deposit_date.isoformat(),bsr,challan)
                    )
                    conn.commit()
                st.success("TDS deposit record added.")
            with db_connect() as conn:
                dep = conn.execute("SELECT * FROM tds_deposits WHERE yearly_record_id=? ORDER BY id",(yid,)).fetchall()
            st.dataframe(pd.DataFrame([dict(r) for r in dep]), use_container_width=True)

    with tabs[4]:
        ddo = get_ddo()
        with st.form("ddo_form"):
            state = st.text_input("State", ddo["state"])
            district = st.text_input("District", ddo["district"])
            department = st.text_input("Department", ddo["department"])
            officer = st.text_input("Officer Name", ddo["officer_name"])
            father = st.text_input("Father Name", ddo["father_name"])
            tan = st.text_input("TAN", ddo["tan"])
            address = st.text_input("Address", ddo["address"])
            city = st.text_input("City", ddo["city"])
            pincode = st.text_input("Pincode", ddo["pincode"])
            save = st.form_submit_button("Save DDO Master")
        if save:
            if not tan.strip():
                st.error("TAN is required.")
            else:
                with db_connect() as conn:
                    existing = conn.execute("SELECT id FROM ddo_masters ORDER BY id LIMIT 1").fetchone()
                    if existing:
                        conn.execute("""UPDATE ddo_masters SET state=?,district=?,department=?,officer_name=?,
                            father_name=?,tan=?,address=?,city=?,pincode=? WHERE id=?""",
                            (state.upper(),district.upper(),department.upper(),officer.upper(),father.upper(),
                             tan.upper(),address.upper(),city.upper(),pincode,existing["id"]))
                    else:
                        conn.execute("""INSERT INTO ddo_masters(state,district,department,officer_name,father_name,tan,address,city,pincode)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                            (state.upper(),district.upper(),department.upper(),officer.upper(),father.upper(),
                             tan.upper(),address.upper(),city.upper(),pincode))
                    conn.commit()
                st.success("DDO master saved.")

    with tabs[5]:
        st.write("Tax configuration is kept in code as FY/AY-specific configuration. Do not alter statutory values without verification.")
        new_user = st.text_input("Admin username", get_setting("admin_username","admin"))
        new_pass = st.text_input("Admin password", type="password")
        if st.button("Update Admin Credentials"):
            set_setting("admin_username", new_user)
            if new_pass:
                set_setting("admin_password", new_pass)
            st.success("Credentials updated.")

    with tabs[6]:
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT id,transaction_id,yearly_record_id,action_type,old_values,new_values,changed_by,changed_at,reason "
                "FROM transaction_audit_trail ORDER BY id DESC LIMIT 500"
            ).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

# --------------------------- app start ---------------------------

try:
    init_db()
except Exception as exc:
    st.error(f"Application startup aborted: {exc}")
    st.stop()

GLOBAL_AY = st.selectbox("Active Assessment Year", AY_OPTIONS)

st.title("🏛️ Kosh-Tax — Enterprise Salary / TDS / Form-16 Portal")
st.caption(f"Version {APP_VERSION} | Source of truth: ACTIVE salary_transactions")

tab_employee, tab_archive, tab_admin = st.tabs([
    "👤 Salary Register", "🔍 Archive / Search", "🔒 Admin Command Center"
])

with tab_employee:
    render_employee()

with tab_archive:
    render_archive()

with tab_admin:
    admin_panel()

st.markdown(
    "<hr><div style='text-align:center;font-size:11px;'>"
    "🏛️ KOSH-TAX | COMPREHENSIVE TDS & FORM-16 MANAGEMENT PORTAL<br>"
    "DESIGNED & DEVELOPED BY NITIN"
    "</div>",
    unsafe_allow_html=True,
)


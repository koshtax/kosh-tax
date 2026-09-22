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
APP_VERSION = "2.2.0-granular-audit-public-scan-integrated"

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

def match_district_from_text(raw_text):
    text_upper = raw_text.upper()
    for dist, blocks in JHARKHAND_BLOCK_DISTRICT_MAP.items():
        if dist in text_upper:
            return dist
        for blk in blocks:
            if re.search(r'\b' + re.escape(blk) + r'\b', text_upper):
                return dist
    return "KHUNTI"

def get_clean_num(text, labels):
    for label in labels:
        pat = rf"{re.escape(label)}\s*[:\-]?\s*[₹Rs\.\s]*([0-9][0-9,]*(?:\.[0-9]+)?)"
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except Exception:
                pass
    return 0.0

def parse_slip_in_memory(uploaded_file):
    extracted = {
        'name': '',
        'pan': '',
        'designation': 'ASSISTANT TEACHER',
        'gpf_no': '',
        'office_name': '',
        'basic': 55200.0,
        'da': 27600.0,
        'hra': 4968.0,
        'medical': 1000.0,
        'gpf': 5000.0,
        'gis': 60.0,
        'ptax': 200.0,
        'tds': 3000.0,
        'auto_district': 'KHUNTI',
        'auto_state': 'JHARKHAND',
        'employer_type': 'STATE GOVERNMENT',
        'pension_type': 'OLD PENSION (GPF / OPS)',
        'arrear_da': 0.0,
        'arrear_pay': 0.0,
        'custom_arrear_rows': []
    }
    try:
        reader = PdfReader(uploaded_file)
        pages_text = [p.extract_text() or "" for p in reader.pages]
        full_text = "\n".join(pages_text)
        raw_clean = re.sub(r'[ \t]+', ' ', full_text).upper()
        
        extracted['auto_district'] = match_district_from_text(raw_clean)
        pan_m = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', raw_clean)
        if pan_m: extracted['pan'] = pan_m.group(1).strip()
        
        name_m = re.search(r'EMPLOYEE\s*NAME\s*[:\-]?\s*([A-Z\s\.]+?)(?=\s*PAN|\s*DDO|\s*DESIGNATION|\n|$)', raw_clean)
        if name_m:
            c = name_m.group(1).strip()
            if len(c) > 2 and not any(ch.isdigit() for ch in c): extracted['name'] = c
            
        des_m = re.search(r'DESIGNATION\s*[:\-]?\s*([A-Z0-9\s\.\+\/\-]+?)(?=\s*PAY\s*SCALE|\s*TV|\s*ALLOWANCES|\n|$)', raw_clean)
        if des_m: extracted['designation'] = des_m.group(1).strip()
        
        gpf_m = re.search(r'(?:EMPLOYEE\s*)?(?:GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', raw_clean)
        if gpf_m: extracted['gpf_no'] = gpf_m.group(1).strip()

        b_val = get_clean_num(raw_clean, ["BASIC", "मूल वेतन"])
        if b_val > 0: extracted['basic'] = b_val
        da_val = get_clean_num(raw_clean, ["DA", "DEARNESS ALLOWANCE"])
        if da_val > 0: extracted['da'] = da_val
        hra_val = get_clean_num(raw_clean, ["HRA"])
        if hra_val > 0: extracted['hra'] = hra_val
        med_val = get_clean_num(raw_clean, ["MEDICAL"])
        if med_val > 0: extracted['medical'] = med_val
        gpf_val = get_clean_num(raw_clean, ["GPF", "NPS", "PRAN", "EPF"])
        if gpf_val > 0: extracted['gpf'] = gpf_val
        tds_val = get_clean_num(raw_clean, ["I.TAX", "ITAX", "1.TAX", "TDS"])
        if tds_val > 0: extracted['tds'] = tds_val
    except Exception:
        pass
    return extracted

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

def initialize_employee(ay, pan, name="NEW EMPLOYEE", designation="CLERK", office="DEFAULT SCHOOL"):
    rules = get_tax_rules(ay)
    with db_connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO employee_yearly_records
            (ay,pan,name,designation,office_name,tax_regime,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (ay,pan,name,designation,office,rules["default_regime"],now_text())
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

    st.markdown("#### 📄 Salary Slip Upload & Dynamic Auto-Fill (Scan)")
    slip_up = st.file_uploader(
        "Upload Salary Slip (PDF) — District, Sector & Basic data auto-detect ho jayengi:", 
        type=["pdf"], 
        key="public_slip_scan"
    )
    
    scanned_data = None
    if slip_up:
        if "last_uploaded_slip" not in st.session_state or st.session_state["last_uploaded_slip"] != slip_up.name:
            scanned_data = parse_slip_in_memory(slip_up)
            st.session_state["scanned_slip_data"] = scanned_data
            st.session_state["last_uploaded_slip"] = slip_up.name
            if scanned_data.get('pan'):
                st.session_state["scanned_pan_input"] = scanned_data['pan'].upper()
            st.rerun()

    scanned_data = st.session_state.get("scanned_slip_data", None)
    if scanned_data and scanned_data.get('pan'):
        with st.expander("📋 Extracted Slip Data Summary & Auto-Detection", expanded=True):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Employee Name", (scanned_data.get('name') or "N/A").upper())
            r2.metric("PAN Number", (scanned_data.get('pan') or "N/A").upper())
            r3.metric("Auto District", (scanned_data.get('auto_district') or "KHUNTI").upper())
            r4.metric("Basic Pay", f"₹{scanned_data.get('basic', 0):,.0f}")

    pan = st.text_input("PAN", value=st.session_state.get("scanned_pan_input", ""), placeholder="ABCDE1234F").strip().upper()
    if len(pan) != 10:
        st.info("Enter a valid 10-character PAN to load/create the yearly ledger.")
        return

    record = ensure_employee(GLOBAL_AY, pan)
    if record is None:
        init_name = scanned_data.get('name', 'NEW EMPLOYEE') if scanned_data else 'NEW EMPLOYEE'
        init_des = scanned_data.get('designation', 'CLERK') if scanned_data else 'CLERK'
        if st.button("Initialize New Employee Yearly Ledger"):
            initialize_employee(GLOBAL_AY, pan, name=init_name, designation=init_des)
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
        tds_rec = reconcile_tds(active, deposits)

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
        tds_rec = reconcile_tds(active, deposits)
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
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import smtplib
import re

# ============================================================
# KOSH-TAX — ENTERPRISE SALARY / ARREAR / TDS / FORM-16 PORTAL
# ============================================================

st.set_page_config(
    page_title="Kosh-Tax | TDS & Form 16 Enterprise Management Portal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = os.environ.get("KOSHTAX_DB", "tds_enterprise_master.sqlite")
APP_VERSION = "2.3.0-complete-monolithic-production"

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

JHARKHAND_MONTHS = [
    "MARCH 2024", "APRIL 2024", "MAY 2024", "JUNE 2024", 
    "JULY 2024", "AUGUST 2024", "SEPTEMBER 2024", "OCTOBER 2024", 
    "NOVEMBER 2024", "DECEMBER 2024", "JANUARY 2025", "FEBRUARY 2025"
]

AY_OPTIONS = [
    "AY 2025-26 (FY 2024-25)",
    "AY 2026-27 (FY 2025-26)",
]

CPC_7TH_MATRIX = {
    "LEVEL 1 (GP 1800)": [18000, 18500, 19100, 19700, 20300, 20900, 21500, 22100, 22800, 23500, 24200, 24900, 25600, 26400, 27200],
    "LEVEL 2 (GP 1900)": [19900, 20500, 21100, 21700, 22400, 23100, 23800, 24500, 25200, 26000, 26800, 27600, 28400, 29300, 30200],
    "LEVEL 3 (GP 2000)": [21700, 22400, 23100, 23800, 24500, 25200, 26000, 26800, 27600, 28400, 29300, 30200, 31100, 32000, 33000],
    "LEVEL 4 (GP 2400)": [25500, 26300, 27100, 27900, 28700, 29600, 30500, 31400, 32300, 33300, 34300, 35300, 36400, 37500, 38600],
    "LEVEL 5 (GP 2800)": [29200, 30100, 31000, 31900, 32900, 33900, 34900, 35900, 37000, 38100, 39200, 40400, 41600, 42800, 44100],
    "LEVEL 6 (GP 4200)": [35400, 36500, 37600, 38700, 39900, 41100, 42300, 43600, 44900, 46200, 47600, 49000, 50500, 52000, 53600],
    "LEVEL 7 (GP 4600)": [44900, 46200, 47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000],
    "LEVEL 8 (GP 4800)": [47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000, 70000, 72100],
    "LEVEL 9 (GP 5400)": [53100, 54700, 56300, 58000, 59700, 61500, 63300, 65200, 67200, 69200, 71300, 73400, 75600, 77900, 80200],
    "LEVEL 10 (GP 5400)": [56100, 57800, 59500, 61300, 63100, 65000, 67000, 69000, 71100, 73200, 75400, 77700, 80000, 82400, 84900],
    "LEVEL 11 (GP 6600)": [67700, 69700, 71800, 74000, 76200, 78500, 80900, 83300, 85800, 88400, 91100, 93800, 96600, 99500, 102500],
    "LEVEL 12 (GP 7600)": [78800, 81200, 83600, 86100, 88700, 91400, 94100, 96900, 99800, 102800, 105900, 109100, 112400, 115800, 119300]
}

JHARKHAND_BLOCK_DISTRICT_MAP = {
    "KHUNTI": ["KHUNTI", "ARKI", "TORPA", "MURHU", "RANIA", "KARRA"],
    "RANCHI": ["RANCHI", "BUNDU", "ORMANJHI", "KANKA", "NAGRI", "RATU", "SILLI", "ANGARA", "BERO", "BURMU", "CHANHO", "ITKI", "KHELARI", "LAPUNG", "MANDAR", "NAMKUM", "RAHE", "SONAHATU", "TAMAR"],
    "GUMLA": ["GUMLA", "BISHUNPUR", "CHAINPUR", "GHAGHRA", "RAIDIH", "SISAI", "VERNO", "BASIA", "KAMDARA", "PALKOT", "DUMRI", "ALHAU"],
    "SIMDEGA": ["SIMDEGA", "BANO", "BANSJOR", "BOLBA", "JALDEGA", "KERSAI", "KOLEBIRA", "KURDEG", "PAIKPARA", "THETHAI TANGER"],
    "LOHARDAGA": ["LOHARDAGA", "BHANDRA", "KUDU", "KISKO", "PESHRAR", "SENA", "KAIRO"],
    "EAST SINGHBHUM": ["JAMSHEDPUR", "GOLMURI", "POTKA", "PATAMDA", "BORAM", "GHATSHILA", "DHALBHUMGARH", "MUSABANI", "DUMARIA", "BAHRA GORA", "CHAKULIA"],
    "WEST SINGHBHUM": ["CHAIBASA", "CHAKRADHARPUR", "JHINKPANI", "KHAIRPAL", "KUMARDUNGI", "MANJHARI", "MANJHGON", "NOAMUNDI", "TANTNAGAR", "GOILKERA", "SONUA", "ANANDPUR", "BANDGAON", "MANOHARPUR", "HAT GAMHARIA", "JAGANNATHPUR", "GUWA"],
    "SERAIKELA KHARSAWAN": ["SERAIKELA", "KHARSAWAN", "CHANDIL", "ICHAGARH", "KUKRU", "NIMDIH", "ADITYAPUR", "GAMHARIA", "RAJNAGAR", "KUCHAI"],
    "PALAMU": ["MEDININAGAR", "DALTONGANJ", "BISHRAMPUR", "CHHATARPUR", "CHAINPUR", "HARIHARGANJ", "HUSSAINABAD", "LESLEGANJ", "MANATU", "PANDU", "PANKI", "PATAN", "PIPRA", "SATBARWA", "TARHASI", "UTTARI"],
    "GARHWA": ["GARHWA", "BHAWANATHPUR", "DANDA", "DANDAI", "DHURKI", "KANDI", "KHAROUNDHI", "MAJHIAON", "MERAL", "NAGAR UNTARI", "RAMKANDA", "RAMUNA", "SAGMA", "CHINIYA"],
    "LATEHAR": ["LATEHAR", "BALUMATH", "BARWADIH", "BARELY", "CHANDWA", "GARU", "HERHANJ", "MAHUADANR", "MANIKA"],
    "HAZARIBAGH": ["HAZARIBAGH", "BARHI", "BARKAGAON", "BARKATHA", "BISHNUGARH", "CHAU PARAN", "CHURCHU", "DARU", "ICHAK", "KATKAMSANDI", "KATKAMDAG", "KEREDARI", "PADMA", "TATIPARAI"],
    "RAMGARH": ["RAMGARH", "DULLI", "GOLA", "MANDU", "PATRATU", "CHITARPUR"],
    "BOKARO": ["CHAS", "CHANDANKIYARI", "BERMO", "GOMIA", "BOKARO", "JARIDIH", "KASMAR", "NAWADIH", "PETERBAR"],
    "DHANBAD": ["DHANBAD", "BAGHMARA", "BALIAPUR", "GOVINDPUR", "JHARIA", "NIRSA", "TOPCHANCHI", "TUNDI", "PURBO TUNDI", "ECL"],
    "GIRIDIH": ["GIRIDIH", "BAGODAR", "BENGIABAD", "BIRNI", "DEORI", "DHANWAR", "DUMRI", "GANDEY", "GAWAN", "JAMUA", "PIRTAND", "SURIYA", "TISRI"],
    "CHATRA": ["CHATRA", "HUNTERGANJ", "ITARHI", "KANHAPRA", "KUNDA", "LAWALAUNG", "MAYUR HAND", "PATHALGADA", "PRATAPPUR", "SIMARIA", "TANDWA"],
    "KODERMA": ["KODERMA", "JHUMRI TELAIYA", "CHANDWARA", "DOMCHANCH", "JAINAGAR", "MARKACHO", "SATGAWAN"],
    "DEOGHAR": ["DEOGHAR", "MADHUPUR", "DEVIPUR", "KARON", "MARGO MUNDA", "MOHANPUR", "PALOJORI", "SARATH", "SARWAN", "SONARAITHARHI"],
    "DUMKA": ["DUMKA", "GOPIKANDAR", "JAMA", "JARMUNDI", "KATHIKUND", "MASALIA", "RAMGARH DUMKA", "RANISHWAR", "SARAIYAHAT", "SHIKARIPARA"],
    "GODDA": ["GODDA", "BOARIJOR", "MAHAGAMA", "MEHERMA", "PATHARGAMA", "PORAIYAHAT", "SUNDARPAHARI", "THAKURGANGI"],
    "JAMTARA": ["JAMTARA", "FATHEPUR", "KUNDAHIT", "NARAYANPUR", "NALA", "KARMATAUR"],
    "PAKUR": ["PAKUR", "HIRANPUR", "LITIPARA", "AMRAPARA", "MAHESHPUR", "PAKURIA"],
    "SAHIBGANJ": ["SAHIBGANJ", "BORIO", "BARHARWA", "MANDRO", "TALJHARI", "RAJMAHAL", "PATNA SAHIBGANJ", "UDHWA"]
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

# ================= HELPER & UTILITIES =================

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

def match_district_from_text(raw_text):
    text_upper = raw_text.upper()
    for dist, blocks in JHARKHAND_BLOCK_DISTRICT_MAP.items():
        if dist in text_upper:
            return dist
        for blk in blocks:
            if re.search(r'\b' + re.escape(blk) + r'\b', text_upper):
                return dist
    return "KHUNTI"

def get_clean_num(text, labels):
    for label in labels:
        pat = rf"{re.escape(label)}\s*[:\-]?\s*[₹Rs\.\s]*([0-9][0-9,]*(?:\.[0-9]+)?)"
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except Exception:
                pass
    return 0.0

def get_next_matrix_cell(level, current_basic):
    if level in CPC_7TH_MATRIX:
        cells = CPC_7TH_MATRIX[level]
        for idx, cell in enumerate(cells):
            if int(current_basic) == cell and idx + 1 < len(cells):
                return cells[idx + 1]
            elif int(current_basic) < cell:
                return cell
        if cells:
            return cells[-1]
    return int(current_basic)

def get_matching_levels(basic_pay):
    matches = []
    b_val = int(basic_pay)
    for lvl, cells in CPC_7TH_MATRIX.items():
        if b_val in cells:
            matches.append(lvl)
    return matches

def find_nearest_level_by_amount(basic_pay):
    b_val = int(basic_pay)
    best_lvl = "LEVEL 7 (GP 4600)"
    min_diff = 999999
    for lvl, cells in CPC_7TH_MATRIX.items():
        for c in cells:
            diff = abs(c - b_val)
            if diff < min_diff:
                min_diff = diff
                best_lvl = lvl
    return best_lvl

def parse_slip_in_memory(uploaded_file):
    extracted = {
        'name': '',
        'pan': '',
        'designation': 'ASSISTANT TEACHER',
        'gpf_no': '',
        'office_name': '',
        'basic': 55200.0,
        'da': 27600.0,
        'hra': 4968.0,
        'medical': 1000.0,
        'gpf': 5000.0,
        'gis': 60.0,
        'ptax': 200.0,
        'tds': 3000.0,
        'inc_month': '1ST JULY',
        'inc_basic': 56900.0,
        'pay_level': 'LEVEL 7 (GP 4600)',
        'auto_district': 'KHUNTI',
        'auto_state': 'JHARKHAND',
        'employer_type': 'STATE GOVERNMENT',
        'pension_type': 'OLD PENSION (GPF / OPS)',
        'arrear_da': 0.0,
        'arrear_pay': 0.0,
        'custom_arrear_rows': []
    }
    try:
        reader = PdfReader(uploaded_file)
        pages_text = [p.extract_text() or "" for p in reader.pages]
        full_text = "\n".join(pages_text)
        raw_clean = re.sub(r'[ \t]+', ' ', full_text).upper()
        
        extracted['auto_district'] = match_district_from_text(raw_clean)
        pan_m = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', raw_clean)
        if pan_m: extracted['pan'] = pan_m.group(1).strip()
        
        name_m = re.search(r'EMPLOYEE\s*NAME\s*[:\-]?\s*([A-Z\s\.]+?)(?=\s*PAN|\s*DDO|\s*DESIGNATION|\n|$)', raw_clean)
        if name_m:
            c = name_m.group(1).strip()
            if len(c) > 2 and not any(ch.isdigit() for ch in c): extracted['name'] = c
            
        des_m = re.search(r'DESIGNATION\s*[:\-]?\s*([A-Z0-9\s\.\+\/\-]+?)(?=\s*PAY\s*SCALE|\s*TV|\s*ALLOWANCES|\n|$)', raw_clean)
        if des_m: extracted['designation'] = des_m.group(1).strip()
        
        gpf_m = re.search(r'(?:EMPLOYEE\s*)?(?:GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', raw_clean)
        if gpf_m: extracted['gpf_no'] = gpf_m.group(1).strip()

        b_val = get_clean_num(raw_clean, ["BASIC", "मूल वेतन"])
        if b_val > 0: extracted['basic'] = b_val
        da_val = get_clean_num(raw_clean, ["DA", "DEARNESS ALLOWANCE"])
        if da_val > 0: extracted['da'] = da_val
        hra_val = get_clean_num(raw_clean, ["HRA"])
        if hra_val > 0: extracted['hra'] = hra_val
        med_val = get_clean_num(raw_clean, ["MEDICAL"])
        if med_val > 0: extracted['medical'] = med_val
        gpf_val = get_clean_num(raw_clean, ["GPF", "NPS", "PRAN", "EPF"])
        if gpf_val > 0: extracted['gpf'] = gpf_val
        tds_val = get_clean_num(raw_clean, ["I.TAX", "ITAX", "1.TAX", "TDS"])
        if tds_val > 0: extracted['tds'] = tds_val
    except Exception:
        pass
    return extracted

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

# ================= DATABASE INITIALIZATION =================

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
            "admin_username": "__nit@def@admin26__",
            "admin_password": "19052027def@admin",
            "form_fee": "100",
            "upi_id": "nitinmallick111-1@okicici",
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
        "tot_arrear_da": sum(money(t.get("da_arrear",0)) for t in active_transactions),
        "tot_arrear_pay": sum(money(t.get("pay_arrear",0)) for t in active_transactions),
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

# --------------------------- PDF DUAL-ORIENTATION TEMPLATE ---------------------------

HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&family=Roboto:wght@400;500;700&display=swap');
  
  @page {
    size: A4 portrait;
    margin: 6mm 8mm 6mm 8mm;
  }
  
  @page landscape-section {
    size: A4 landscape;
    margin: 6mm 8mm 6mm 8mm;
  }
  
  * { 
    box-sizing: border-box; 
    -webkit-print-color-adjust: exact; 
    text-transform: uppercase;
  }
  
  body { 
    font-family: 'Noto Sans Devanagari', 'Roboto', 'Arial Unicode MS', sans-serif; 
    font-size: 9px; 
    color: #000; 
    line-height: 1.2; 
    margin: 0; 
    padding: 0; 
  }
  
  .page-portrait {
    page-break-after: always;
    page-break-inside: avoid;
    position: relative;
    width: 100%;
  }
  
  .page-landscape {
    page: landscape-section;
    page-break-after: always;
    page-break-inside: avoid;
    position: relative;
    width: 100%;
  }
  
  .center { text-align: center; } 
  .right { text-align: right; } 
  .bold { font-weight: 700; }
  
  .title-main { font-size: 11px; font-weight: 700; line-height: 1.3; }
  .title-sub { font-size: 12.5px; font-weight: 700; line-height: 1.3; margin: 2px 0; }
  
  table { 
    width: 100%; 
    border-collapse: collapse; 
    margin-top: 3px; 
    margin-bottom: 3px; 
  }
  
  table.border, table.border th, table.border td { 
    border: 0.8px solid #000; 
  }
  
  th, td { 
    padding: 2.5px 4px; 
    vertical-align: middle; 
  }
  
  .no-border td { 
    border: none !important; 
    padding: 1.5px 3px; 
  }
  
  .bg-gray { 
    background-color: #f2f2f2 !important; 
  }
  
  .sign-area { 
    margin-top: 15px; 
    width: 100%; 
  }
  
  .sign-box-space {
    height: 38px;
  }
  
  .pdf-footer-credit {
    position: absolute;
    bottom: 2mm;
    left: 0;
    width: 100%;
    text-align: center;
    font-size: 8px;
    color: #555;
    border-top: 0.5px solid #ccc;
    padding-top: 2px;
  }
  
  {% if is_trial %}
  .watermark-layer-p {
    position: absolute;
    top: 32%;
    left: 2%;
    width: 96%;
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    color: rgba(220, 53, 69, 0.16);
    transform: rotate(-30deg);
    border: 3px dashed rgba(220, 53, 69, 0.22);
    padding: 25px 10px;
    letter-spacing: 2px;
    pointer-events: none;
    z-index: 10;
  }
  
  .watermark-layer-l {
    position: absolute;
    top: 30%;
    left: 10%;
    width: 80%;
    text-align: center;
    font-size: 52px;
    font-weight: 800;
    color: rgba(220, 53, 69, 0.16);
    transform: rotate(-22deg);
    border: 3px dashed rgba(220, 53, 69, 0.22);
    padding: 30px 10px;
    letter-spacing: 2px;
    pointer-events: none;
    z-index: 10;
  }
  {% endif %}
</style>
</head>
<body>
<!-- SECTION 1: FORM 16 PART A (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-sub">T.D.S.<br>FORM NO. 16<br>PART A</div>
  <div class="center" style="font-size: 8px; margin-bottom: 6px;">
    CERTIFICATE UNDER SECTION 203 OF THE INCOME-TAX ACT, 1961 FOR TAX DEDUCTION AT SOURCE FROM INCOME CHARGEABLE UNDER THE HEAD "SALARIES"
  </div>
  
  <table class="border">
    <tr>
      <td style="width: 50%; vertical-align: top; height: 50px;">
        <b>Name and address of the Employer:</b><br>
        {{ ddo.department }}, {{ ddo.district }} ({{ ddo.state }})<br>
        {% if ddo.address %}{{ ddo.address }}<br>{% endif %}
        City: {{ ddo.city or ddo.district }} &nbsp;&nbsp;&nbsp;&nbsp; Pin code: {{ ddo.pincode or '------' }}
      </td>
      <td style="width: 50%; vertical-align: top; height: 50px;">
        <b>Name and address of the Employee:</b><br>
        <b>{{ emp.name }}</b><br>
        {{ emp.office_name }}<br>
        District: {{ ddo.district }} ({{ ddo.state }})
      </td>
    </tr>
    <tr>
      <td>
        <table class="no-border" style="width: 100%;">
          <tr><td><b>PAN of the Deductor:</b></td><td><b>TAN of the Deductor:</b> {{ ddo.tan }}</td></tr>
        </table>
      </td>
      <td>
        <table class="no-border" style="width: 100%;">
          <tr>
            <td><b>PAN of the Employee:</b><br>{{ emp.pan }}</td>
            <td><b>Employee Reference No.:</b><br>{{ emp.gpf_no or 'N/A' }}</td>
          </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td>
        <b>CIT (TDS):</b><br>
        Address: ......................................................<br>
        City: {{ ddo.city or ddo.district }} &nbsp;&nbsp;&nbsp;&nbsp; Pin code: {{ ddo.pincode or '------' }}
      </td>
      <td>
        <table class="no-border" style="width: 100%;">
          <tr>
            <td><b>Assessment Year:</b><br>{{ emp.ay }}</td>
            <td><b>Period with Employer:</b><br>From: 01.04.2024 &nbsp; To: 31.03.2025</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
  <div style="font-weight: 700; font-size: 8.5px; margin-top: 5px;">
    Summary of amount paid/credited and tax deducted at source thereon in respect of the employee
  </div>
  <table class="border">
    <tr class="bg-gray center bold" style="font-size: 8px;">
      <th>Quarter(s)</th>
      <th>Receipt Numbers of original quarterly statements of TDS under sub-section (3) of section 200</th>
      <th>Amount paid/credited</th>
      <th>Amount of tax deducted (Rs.)</th>
      <th>Amount of tax deposited/remitted (Rs.)</th>
    </tr>
    <tr class="center">
      <td>Quarter 1</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 2</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 3</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 4</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="bold bg-gray center">
      <td colspan="3">Total (Rs.)</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td>
    </tr>
  </table>
  <div style="font-weight: 700; font-size: 8.5px; margin-top: 5px;">
    I. DETAILS OF TAX DEDUCTED AND DEPOSITED IN THE CENTRAL GOVERNMENT ACCOUNT THROUGH BOOK ADJUSTMENT / CHALLAN
  </div>
  <table class="border" style="font-size: 7.5px;">
    <tr class="bg-gray bold center">
      <th style="width: 5%;">Sl.</th>
      <th>Tax Deposited (Rs.)</th>
      <th>Book Identification Number (BIN) / BSR</th>
      <th>DDO / Challan Serial No.</th>
      <th>Date of transfer voucher</th>
      <th>Status of matching</th>
    </tr>
    {% if deposits %}
      {% for d in deposits %}
      <tr class="center">
        <td>{{ loop.index }}</td>
        <td class="right">{{ "%.2f"|format(d['amount']) }}</td>
        <td>{{ d['bsr_code'] or d['bin'] or 'Book-Adj' }}</td>
        <td>{{ d['challan_serial'] or 'Treasury' }}</td>
        <td>{{ d['deposit_date'] }}</td>
        <td>MATCHED</td>
      </tr>
      {% endfor %}
    {% else %}
      <tr class="center">
        <td>1</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td>
        <td>Book Adjustment</td><td>Treasury Regular Bill</td><td>28.02.2025</td><td>MATCHED</td>
      </tr>
    {% endif %}
  </table>
  <div style="margin-top: 6px; font-size: 8.5px; border-top: 0.8px solid #000; padding-top: 4px;">
    <div class="center bold" style="margin-bottom: 2px;">Verification</div>
    I, <b>{{ ddo.officer_name }}</b>, son/daughter of <b>{{ ddo.father_name }}</b>, working in the capacity of <b>Drawing & Disbursing Officer (DDO)</b> do hereby certify that a sum of Rs. <b>{{ "%.2f"|format(tax.tds_paid) }}</b> has been deducted and deposited to the credit of the Central Government.
    <table class="no-border" style="margin-top: 10px;">
      <tr>
        <td style="width: 50%;">
          Place: {{ ddo.city or ddo.district }}<br>
          Date: {{ today_date }}<br>
          Designation: DDO
        </td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          ________________________________________<br>
          Signature of person responsible for deduction of tax<br>
          Full Name: <b>{{ ddo.officer_name }}</b>
        </td>
      </tr>
    </table>
  </div>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 2: FORM 16 PART B (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-sub">PART B (Annexure)</div>
  <div class="center bold" style="font-size: 9px; margin-bottom: 6px;">Certificate under section 203 of the Income-tax Act, 1961</div>
  <table class="border">
    <tr class="bg-gray bold center"><th style="width: 75%; text-align: left;">Details of Salary Paid and any other income and tax deducted</th><th style="width: 25%; text-align: right;">Amount (Rs.)</th></tr>
    <tr><td>1. Gross Salary</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>2. Less: Allowance to the extent exempt u/s 10</td><td class="right">0.00</td></tr>
    <tr><td>3. Balance (1 - 2)</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>4. Deductions under section 16(ia) Standard Deduction</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr class="bold"><td>5. Income chargeable under the head 'Salaries'</td><td class="right">{{ "%.2f"|format(tax.gross - tax.std_ded) }}</td></tr>
    <tr class="bold bg-gray"><td>6. Gross Total Income</td><td class="right">{{ "%.2f"|format(tax.gross_total_income) }}</td></tr>
    <tr><td>7. Deductions under Chapter VI-A</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
    <tr class="bold"><td>8. Total Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>9. Net Tax Liability</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>10. Total TDS Deducted</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>11. Balance Tax Payable / (Refundable)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  <div class="sign-area" style="margin-top: 15px;">
    <table class="no-border">
      <tr>
        <td style="width: 50%;">Place: {{ ddo.city or ddo.district }}<br>Date: {{ today_date }}</td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          ________________________________________<br>
          Signature of DDO
        </td>
      </tr>
    </table>
  </div>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 3: SCHEDULE OF INCOME TAX (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-main">{{ tax.regime }} के तहत</div>
  <div class="center title-sub">Schedule of Income - Tax</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 6px;">{{ emp.ay }}</div>
  <table class="no-border" style="margin-bottom: 6px;">
    <tr><td style="width: 25%;">करदाता का नाम</td><td>: <b>{{ emp.name }}</b></td></tr>
    <tr><td>पदनाम</td><td>: {{ emp.designation }}</td></tr>
    <tr><td>कार्यालय / विद्यालय का नाम</td><td>: {{ emp.office_name }}</td></tr>
    <tr><td>स्थायी लेखा संख्या (PAN)</td><td>: <b>{{ emp.pan }}</b></td></tr>
  </table>
  <table class="border">
    <tr class="bg-gray bold">
      <th style="width: 6%;">क</th>
      <th style="width: 70%; text-align: left;">वेतन स्रोत से आय का विवरण:</th>
      <th style="width: 24%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>मूल वेतन (Basic Salary)</td><td class="right">{{ "%.2f"|format(totals.basic) }}</td></tr>
    <tr><td>02.</td><td>महँगाई भत्ता (DA)</td><td class="right">{{ "%.2f"|format(totals.da) }}</td></tr>
    <tr><td>03.</td><td>मकान किराया भत्ता (HRA)</td><td class="right">{{ "%.2f"|format(totals.hra) }}</td></tr>
    <tr><td>04.</td><td>चिकित्सा भत्ता (Medical Allowance)</td><td class="right">{{ "%.2f"|format(totals.medical) }}</td></tr>
    <tr><td>05.</td><td>बकाया राशि (Arrears Total)</td><td class="right">{{ "%.2f"|format(totals.arrear) }}</td></tr>
    <tr class="bold bg-gray"><td>06.</td><td>सकल वेतन (Gross Salary)</td><td class="right">{{ "%.2f"|format(totals.gross) }}</td></tr>
  </table>
  <table class="border" style="margin-top: 6px;">
    <tr class="bg-gray bold">
      <th style="width: 6%;">ख</th>
      <th style="width: 70%; text-align: left;">आयकर की संगणना</th>
      <th style="width: 24%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>कर योग्य आय (Taxable Total Income)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>02.</td><td>कुल देय आयकर (Total Tax Liability)</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>03.</td><td>भुगतान किया गया कुल TDS</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>04.</td><td>शुद्ध देय / (रिफंड)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 4: MONTHLY SALARY LEDGER (LANDSCAPE) -->
<div class="page-landscape">
  {% if is_trial %}<div class="watermark-layer-l">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-sub">मासिक वेतन एवं कटौतियों की विवरणी (Monthly Salary & Transaction Ledger)</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 8px;">{{ emp.name }} (PAN: {{ emp.pan }}) | {{ emp.office_name }}</div>
  <table class="border" style="font-size: 8.5px; margin-top: 6px;">
    <tr class="bg-gray center bold">
      <th>Type / Period</th><th>Bill No</th><th>Basic</th><th>DA</th><th>HRA</th><th>Med</th><th>Arrears</th><th>Gross</th><th>GPF/NPS</th><th>GIS</th><th>PTax</th><th>TDS</th><th>Net</th>
    </tr>
    {% for r in records %}
    {% if r.status != 'VOID' %}
    <tr>
      <td><b>{{ r.payment_month }}</b> ({{ r.transaction_type }})</td>
      <td>{{ r.bill_number or '-' }}</td>
      <td class="right">{{ "%.2f"|format(r.basic) }}</td>
      <td class="right">{{ "%.2f"|format(r.da) }}</td>
      <td class="right">{{ "%.2f"|format(r.hra) }}</td>
      <td class="right">{{ "%.2f"|format(r.medical) }}</td>
      <td class="right">{{ "%.2f"|format(r.da_arrear + r.pay_arrear + r.hra_arrear + r.medical_arrear + r.other_arrear) }}</td>
      <td class="right bold">{{ "%.2f"|format(r.gross) }}</td>
      <td class="right">{{ "%.2f"|format(r.gpf + r.nps) }}</td>
      <td class="right">{{ "%.2f"|format(r.gis) }}</td>
      <td class="right">{{ "%.2f"|format(r.professional_tax) }}</td>
      <td class="right">{{ "%.2f"|format(r.tds) }}</td>
      <td class="right bold">{{ "%.2f"|format(r.net) }}</td>
    </tr>
    {% endif %}
    {% endfor %}
    <tr class="bold bg-gray">
      <td colspan="2">TOTAL</td>
      <td class="right">{{ "%.2f"|format(totals.basic) }}</td>
      <td class="right">{{ "%.2f"|format(totals.da) }}</td>
      <td class="right">{{ "%.2f"|format(totals.hra) }}</td>
      <td class="right">{{ "%.2f"|format(totals.medical) }}</td>
      <td class="right">{{ "%.2f"|format(totals.arrear) }}</td>
      <td class="right">{{ "%.2f"|format(totals.gross) }}</td>
      <td class="right">{{ "%.2f"|format(totals.gpf + totals.nps) }}</td>
      <td class="right">{{ "%.2f"|format(totals.gis) }}</td>
      <td class="right">{{ "%.2f"|format(totals.ptax) }}</td>
      <td class="right">{{ "%.2f"|format(totals.tds) }}</td>
      <td class="right">{{ "%.2f"|format(totals.net) }}</td>
    </tr>
  </table>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>
</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, transactions, tax_summary, totals, deposits=None, decl_dict=None, is_trial=False):
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF dependencies unavailable. Install jinja2 and weasyprint.")
    
    active_txs = [t for t in transactions if str(t.get('status', 'ACTIVE')).upper() != 'VOID']
    
    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=active_txs, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=decl_dict or {}, 
        today_date=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

# ================= APPLICATION SUITE & ROUTING =================

def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    st.markdown("#### 📄 Salary Slip Upload & Dynamic Auto-Fill (Scan)")
    slip_up = st.file_uploader(
        "Upload Salary Slip (PDF) — District, Sector & Basic data auto-detect ho jayengi:", 
        type=["pdf"], 
        key=f"{prefix}_slip"
    )
    
    scanned_data = None
    if slip_up:
        if f"{prefix}_last_uploaded" not in st.session_state or st.session_state[f"{prefix}_last_uploaded"] != slip_up.name:
            scanned_data = parse_slip_in_memory(slip_up)
            st.session_state[f"{prefix}_scanned"] = scanned_data
            st.session_state[f"{prefix}_last_uploaded"] = slip_up.name
            if scanned_data.get('pan'):
                st.session_state[f"{prefix}_pan_field"] = scanned_data['pan'].upper()
            st.rerun()

    scanned_data = st.session_state.get(f"{prefix}_scanned", None)
    if scanned_data and scanned_data.get('pan'):
        with st.expander("📋 Extracted Slip Data Summary & Auto-Detection", expanded=True):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Employee Name", (scanned_data.get('name') or "N/A").upper())
            r2.metric("PAN Number", (scanned_data.get('pan') or "N/A").upper())
            r3.metric("Auto District", (scanned_data.get('auto_district') or "KHUNTI").upper())
            r4.metric("Basic Pay", f"₹{scanned_data.get('basic', 0):,.0f}")

    pan_in = st.text_input("Permanent Account Number (PAN) *", placeholder="ABCDE1234F", key=f"{prefix}_pan_field").upper().strip()
    
    if pan_in and len(pan_in) == 10:
        conn = db_connect()
        y_rec = conn.execute("SELECT id, office_name, tax_regime FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()
        conn.close()
        
        if not y_rec:
            init_name = scanned_data.get('name', 'NEW EMPLOYEE') if scanned_data else 'NEW EMPLOYEE'
            init_des = scanned_data.get('designation', 'CLERK') if scanned_data else 'CLERK'
            if st.button("Initialize New Employee Yearly Ledger"):
                with db_connect() as conn:
                    rules = get_tax_rules(GLOBAL_AY)
                    conn.execute("INSERT OR IGNORE INTO employee_yearly_records (ay, pan, name, designation, office_name, tax_regime) VALUES (?, ?, ?, ?, ?, ?)",
                                  (GLOBAL_AY, pan_in, init_name, init_des, "DEFAULT SCHOOL", rules["default_regime"]))
                    conn.commit()
                st.rerun()
        else:
            y_id, office_name, current_regime = y_rec[0], y_rec[1], y_rec[2]
            st.success(f"Loaded Yearly Record ID: {y_id} | Office: {office_name}")
            
            rules = get_tax_rules(GLOBAL_AY)
            
            conn = db_connect()
            tx_rows = conn.execute("SELECT * FROM salary_transactions WHERE yearly_record_id=?", (y_id,)).fetchall()
            conn.close()
            
            tx_data = [dict(r) for r in tx_rows]
            df_tx = pd.DataFrame(tx_data) if tx_data else pd.DataFrame(columns=TX_COLUMNS)
            
            st.markdown("##### ✏️ Interactive Transaction Register (Editable Table)")
            edited_df = st.data_editor(
                df_tx,
                num_rows="dynamic",
                key=f"{prefix}_editor",
                use_container_width=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "transaction_type": st.column_config.SelectboxColumn("Type", options=["REGULAR","ARREAR","RECOVERY","ADJUSTMENT","OTHER"]),
                    "payment_month": st.column_config.SelectboxColumn("Payment Month", options=MONTHS),
                }
            )
            
            if st.button("💾 Save Ledger Transactions & Validate"):
                proposed = []
                for _, row in edited_df.iterrows():
                    d = normalize_transaction(dict(row), rules)
                    proposed.append(d)

                errors, warnings = validate_transactions(proposed)
                if errors:
                    st.error("❌ VALIDATION FAILED — COMMIT & PDF GENERATION BLOCKED:")
                    for e in errors:
                        st.markdown(f"- {e}")
                    return

                conn = db_connect()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    valid_ids = {r["id"] for r in conn.execute("SELECT id FROM salary_transactions WHERE yearly_record_id=?", (y_id,)).fetchall()}
                    submitted_ids = {int(r["id"]) for r in proposed if r.get("id") not in (None, "", 0) and not pd.isna(r.get("id"))}

                    for tid in sorted(valid_ids - submitted_ids):
                        old = conn.execute("SELECT * FROM salary_transactions WHERE id=?", (tid,)).fetchone()
                        if old and str(old["status"]).upper() != "VOID":
                            old_dict = dict(old)
                            new_dict = dict(old_dict)
                            new_dict["status"] = "VOID"
                            conn.execute("UPDATE salary_transactions SET status='VOID', updated_at=? WHERE id=?", (now_text(), tid))
                            audit_insert(conn, tid, y_id, "DELETE", old_dict, new_dict, "Removed from editor")

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
                            old = conn.execute("SELECT * FROM salary_transactions WHERE id=?", (tid,)).fetchone()
                            old_dict = dict(old) if old else None
                            conn.execute("""UPDATE salary_transactions SET 
                                financial_year=?, assessment_year=?, transaction_type=?, payment_month=?, payment_date=?,
                                bill_number=?, bill_date=?, original_salary_month=?, original_salary_year=?,
                                original_period_from=?, original_period_to=?, arrear_type=?, basic=?, da=?, hra=?, medical=?,
                                other_allowance=?, da_arrear=?, pay_arrear=?, hra_arrear=?, medical_arrear=?, other_arrear=?,
                                gross=?, gpf=?, nps=?, gis=?, professional_tax=?, tds=?, other_deduction=?, recovery=?, net=?,
                                remarks=?, source_reference=?, updated_at=?, updated_by=?, status=? WHERE id=?""", params + (tid,))
                            audit_insert(conn, tid, y_id, "UPDATE", old_dict, dict(tx))
                        else:
                            conn.execute("""INSERT INTO salary_transactions(
                                yearly_record_id, financial_year, assessment_year, transaction_type, payment_month, payment_date,
                                bill_number, bill_date, original_salary_month, original_salary_year, original_period_from,
                                original_period_to, arrear_type, basic, da, hra, medical, other_allowance, da_arrear, pay_arrear,
                                hra_arrear, medical_arrear, other_arrear, gross, gpf, nps, gis, professional_tax, tds,
                                other_deduction, recovery, net, remarks, source_reference, created_at, created_by, status)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (y_id, *params))
                            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                            audit_insert(conn, new_id, y_id, "INSERT", None, dict(tx))

                    conn.commit()
                    st.success("✅ Database committed successfully with audit trail!")
                except Exception as ex:
                    conn.rollback()
                    st.error(f"Database transaction rolled back: {ex}")
                    return
                finally:
                    conn.close()

                active_txs = load_transactions(y_id)
                declarations = get_declarations(y_id)
                totals, tax_summary = tax_engine(active_txs, current_regime, declarations, rules)
                
                deposits = get_tds_deposits(y_id)
                tds_rec = reconcile_tds(active_txs, deposits)
                form16_errs = reconcile_form_16_dataset(active_txs, tax_summary, totals, rules, declarations)
                sched_errs = reconcile_schedule_dataset(active_txs, totals)
                all_errs = form16_errs + sched_errs + tds_rec["errors"]

                if all_errs:
                    st.error("❌ RECONCILIATION GATES FAILED. PDF Generation Blocked.")
                    for err in all_errs:
                        st.markdown(f"- {err}")
                    return

                conn = db_connect()
                ddo_r = conn.execute("SELECT * FROM ddo_masters LIMIT 1").fetchone()
                conn.close()
                
                ddo_d = dict(ddo_r) if ddo_r else {
                    'state': 'JHARKHAND', 'district': 'KHUNTI', 'department': 'SCHOOL EDUCATION',
                    'officer_name': 'DDO OFFICER', 'father_name': 'FATHER', 'tan': 'PTIK01234A',
                    'address': 'SCHOOL CAMPUS', 'city': 'KHUNTI', 'pincode': '835210'
                }
                emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': record['name'], 'designation': record['designation'], 'office_name': office_name}

                pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, active_txs, tax_summary, totals, deposits=deposits, decl_dict=declarations, is_trial=False)
                st.success("🎉 All Validation & Reconciliation Gates Passed!")
                st.download_button("📥 Download Official Audit-Ready PDF Bundle", pdf_bytes, f"FORM16_{pan_in}_{GLOBAL_AY.replace(' ','_')}.pdf", "application/pdf")

# ================= TOP BAR & ROUTING =================

try:
    init_db()
except Exception as exc:
    st.error(f"Application startup aborted: {exc}")
    st.stop()

query_params = st.query_params
is_admin_url = query_params.get("admin", "").lower() == "true"

col_ay1, col_ay2 = st.columns([3, 1])
with col_ay1: st.markdown("## 🏛️ Kosh-Tax | Enterprise Salary, TDS & Form-16 Portal")
with col_ay2: GLOBAL_AY = st.selectbox("Active Assessment Year", AY_OPTIONS, index=0)

if is_admin_url:
    tab_emp, tab_redownload, tab_admin = st.tabs([
        "👤 Public Employee Self-Service",
        "🔍 Already Paid? Re-Download Archive",
        "🔒 Admin Command Center"
    ])
else:
    tab_emp, tab_redownload = st.tabs([
        "👤 Public Employee Self-Service",
        "🔍 Already Paid? Re-Download Archive"
    ])
    tab_admin = None

with tab_emp:
    render_full_employee_suite(is_admin_mode=False, prefix="emp_public")

with tab_redownload:
    st.markdown("### 🔍 Re-Download Official Form 16 & Tax Schedule")
    rd_pan = st.text_input("Enter PAN Number", key="rd_pan_field").upper().strip()
    if rd_pan:
        with db_connect() as conn:
            y_rec = conn.execute("SELECT * FROM employee_yearly_records WHERE pan=?", (rd_pan,)).fetchone()
        if y_rec:
            st.success(f"Record found for: {y_rec['name']} | Office: {y_rec['office_name']}")
        else:
            st.error("No record found for this PAN.")

if tab_admin and is_admin_url:
    with tab_admin:
        if 'admin_logged_in' not in st.session_state:
            st.session_state.admin_logged_in = False

        if not st.session_state.admin_logged_in:
            st.markdown("### 🔒 Secure Admin Authentication Gateway")
            with st.form("admin_auth_form"):
                in_user = st.text_input("Admin Username")
                in_pass = st.text_input("Admin Password", type="password")
                btn_login = st.form_submit_button("Authenticate & Access Dashboard")
                if btn_login:
                    cur_u = get_setting('admin_username', '__nit@def@admin26__')
                    cur_p = get_setting('admin_password', '19052027def@admin')
                    if in_user == cur_u and in_pass == cur_p:
                        st.session_state.admin_logged_in = True
                        st.success("Authentication Successful!")
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password.")
        else:
            if st.button("🚪 Logout Admin"):
                st.session_state.admin_logged_in = False
                st.rerun()

            adm_sub_tab1, adm_sub_tab2, adm_sub_tab3, adm_sub_tab4, adm_sub_tab5, adm_sub_tab6 = st.tabs([
                "📊 Revenue & Analytics",
                "🗃️ Master DB Manager",
                "📥 Payment Queue",
                "🏦 Statutory TDS Deposits",
                "🏛️ DDO Master",
                "⚙️ Config & Credentials"
            ])
            with adm_sub_tab1:
                st.subheader("📊 Financial Collection Analytics")
                with db_connect() as conn:
                    raw_records = conn.execute("SELECT payment_status, amount_paid FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                total_rev = sum(r["amount_paid"] for r in raw_records if r["payment_status"] == 'APPROVED')
                st.metric("Total Approved Revenue", f"₹{total_rev:,.0f}")
            with adm_sub_tab2:
                st.subheader("🗃️ Master Database Manager")
                with db_connect() as conn:
                    users = conn.execute("SELECT id, pan, name, office_name, payment_status FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                st.write(f"Total Registered Profiles: {len(users)}")
                for u in users:
                    st.text(f"ID: {u['id']} | PAN: {u['pan']} | Name: {u['name']} | Office: {u['office_name']} | Status: {u['payment_status']}")
            with adm_sub_tab3:
                st.subheader("📥 Live Payment Queue")
                with db_connect() as conn:
                    reqs = conn.execute("SELECT id, pan, name, payment_status, payment_mode FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                for r in reqs:
                    st.text(f"PAN: {r['pan']} | Name: {r['name']} | Status: {r['payment_status']} | Mode: {r['payment_mode']}")
            with adm_sub_tab4:
                st.subheader("🏦 Statutory TDS Deposits (Challan / BIN)")
                st.write("Tag challans and BSR codes here.")
            with adm_sub_tab5:
                st.subheader("🏛️ DDO & Hierarchy Master")
                with db_connect() as conn:
                    ddo_table = conn.execute("SELECT id, district, department, officer_name, tan FROM ddo_masters").fetchall()
                st.dataframe(pd.DataFrame([dict(r) for r in ddo_table]), use_container_width=True)
            with adm_sub_tab6:
                st.subheader("⚙️ Config & Credentials")
                new_u = st.text_input("Admin Username", value=get_setting('admin_username', '__nit@def@admin26__'))
                new_p = st.text_input("Admin Password", type="password", value=get_setting('admin_password', '19052027def@admin'))
                if st.button("Update Credentials"):
                    set_setting('admin_username', new_u)
                    set_setting('admin_password', new_p)
                    st.success("Updated successfully!")

# ================= WEB FOOTER (BRANDING) =================
st.markdown("""
<div style="margin-top: 50px; text-align: center; color: #888; font-size: 11px; border-top: 1px solid #333; padding-top: 15px;">
  🏛️ <b>KOSH-TAX</b> | COMPREHENSIVE TDS & FORM 16 MANAGEMENT PORTAL<br>
  <span style="color: #aaa;">DESIGNED & DEVELOPED BY NITIN</span>
</div>
""", unsafe_allow_html=True)


































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
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import smtplib
import re

# ============================================================
# KOSH-TAX — ENTERPRISE SALARY / ARREAR / TDS / FORM-16 PORTAL
# ============================================================

st.set_page_config(
    page_title="Kosh-Tax | TDS & Form 16 Enterprise Management Portal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = os.environ.get("KOSHTAX_DB", "tds_enterprise_master.sqlite")
APP_VERSION = "2.4.0-complete-unabbreviated-master"

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

JHARKHAND_MONTHS = [
    "MARCH 2024", "APRIL 2024", "MAY 2024", "JUNE 2024", 
    "JULY 2024", "AUGUST 2024", "SEPTEMBER 2024", "OCTOBER 2024", 
    "NOVEMBER 2024", "DECEMBER 2024", "JANUARY 2025", "FEBRUARY 2025"
]

AY_OPTIONS = [
    "AY 2025-26 (FY 2024-25)",
    "AY 2026-27 (FY 2025-26)",
]

CPC_7TH_MATRIX = {
    "LEVEL 1 (GP 1800)": [18000, 18500, 19100, 19700, 20300, 20900, 21500, 22100, 22800, 23500, 24200, 24900, 25600, 26400, 27200],
    "LEVEL 2 (GP 1900)": [19900, 20500, 21100, 21700, 22400, 23100, 23800, 24500, 25200, 26000, 26800, 27600, 28400, 29300, 30200],
    "LEVEL 3 (GP 2000)": [21700, 22400, 23100, 23800, 24500, 25200, 26000, 26800, 27600, 28400, 29300, 30200, 31100, 32000, 33000],
    "LEVEL 4 (GP 2400)": [25500, 26300, 27100, 27900, 28700, 29600, 30500, 31400, 32300, 33300, 34300, 35300, 36400, 37500, 38600],
    "LEVEL 5 (GP 2800)": [29200, 30100, 31000, 31900, 32900, 33900, 34900, 35900, 37000, 38100, 39200, 40400, 41600, 42800, 44100],
    "LEVEL 6 (GP 4200)": [35400, 36500, 37600, 38700, 39900, 41100, 42300, 43600, 44900, 46200, 47600, 49000, 50500, 52000, 53600],
    "LEVEL 7 (GP 4600)": [44900, 46200, 47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000],
    "LEVEL 8 (GP 4800)": [47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000, 70000, 72100],
    "LEVEL 9 (GP 5400)": [53100, 54700, 56300, 58000, 59700, 61500, 63300, 65200, 67200, 69200, 71300, 73400, 75600, 77900, 80200],
    "LEVEL 10 (GP 5400)": [56100, 57800, 59500, 61300, 63100, 65000, 67000, 69000, 71100, 73200, 75400, 77700, 80000, 82400, 84900],
    "LEVEL 11 (GP 6600)": [67700, 69700, 71800, 74000, 76200, 78500, 80900, 83300, 85800, 88400, 91100, 93800, 96600, 99500, 102500],
    "LEVEL 12 (GP 7600)": [78800, 81200, 83600, 86100, 88700, 91400, 94100, 96900, 99800, 102800, 105900, 109100, 112400, 115800, 119300]
}

JHARKHAND_BLOCK_DISTRICT_MAP = {
    "KHUNTI": ["KHUNTI", "ARKI", "TORPA", "MURHU", "RANIA", "KARRA"],
    "RANCHI": ["RANCHI", "BUNDU", "ORMANJHI", "KANKA", "NAGRI", "RATU", "SILLI", "ANGARA", "BERO", "BURMU", "CHANHO", "ITKI", "KHELARI", "LAPUNG", "MANDAR", "NAMKUM", "RAHE", "SONAHATU", "TAMAR"],
    "GUMLA": ["GUMLA", "BISHUNPUR", "CHAINPUR", "GHAGHRA", "RAIDIH", "SISAI", "VERNO", "BASIA", "KAMDARA", "PALKOT", "DUMRI", "ALHAU"],
    "SIMDEGA": ["SIMDEGA", "BANO", "BANSJOR", "BOLBA", "JALDEGA", "KERSAI", "KOLEBIRA", "KURDEG", "PAIKPARA", "THETHAI TANGER"],
    "LOHARDAGA": ["LOHARDAGA", "BHANDRA", "KUDU", "KISKO", "PESHRAR", "SENA", "KAIRO"],
    "EAST SINGHBHUM": ["JAMSHEDPUR", "GOLMURI", "POTKA", "PATAMDA", "BORAM", "GHATSHILA", "DHALBHUMGARH", "MUSABANI", "DUMARIA", "BAHRA GORA", "CHAKULIA"],
    "WEST SINGHBHUM": ["CHAIBASA", "CHAKRADHARPUR", "JHINKPANI", "KHAIRPAL", "KUMARDUNGI", "MANJHARI", "MANJHGON", "NOAMUNDI", "TANTNAGAR", "GOILKERA", "SONUA", "ANANDPUR", "BANDGAON", "MANOHARPUR", "HAT GAMHARIA", "JAGANNATHPUR", "GUWA"],
    "SERAIKELA KHARSAWAN": ["SERAIKELA", "KHARSAWAN", "CHANDIL", "ICHAGARH", "KUKRU", "NIMDIH", "ADITYAPUR", "GAMHARIA", "RAJNAGAR", "KUCHAI"],
    "PALAMU": ["MEDININAGAR", "DALTONGANJ", "BISHRAMPUR", "CHHATARPUR", "CHAINPUR", "HARIHARGANJ", "HUSSAINABAD", "LESLEGANJ", "MANATU", "PANDU", "PANKI", "PATAN", "PIPRA", "SATBARWA", "TARHASI", "UTTARI"],
    "GARHWA": ["GARHWA", "BHAWANATHPUR", "DANDA", "DANDAI", "DHURKI", "KANDI", "KHAROUNDHI", "MAJHIAON", "MERAL", "NAGAR UNTARI", "RAMKANDA", "RAMUNA", "SAGMA", "CHINIYA"],
    "LATEHAR": ["LATEHAR", "BALUMATH", "BARWADIH", "BARELY", "CHANDWA", "GARU", "HERHANJ", "MAHUADANR", "MANIKA"],
    "HAZARIBAGH": ["HAZARIBAGH", "BARHI", "BARKAGAON", "BARKATHA", "BISHNUGARH", "CHAU PARAN", "CHURCHU", "DARU", "ICHAK", "KATKAMSANDI", "KATKAMDAG", "KEREDARI", "PADMA", "TATIPARAI"],
    "RAMGARH": ["RAMGARH", "DULLI", "GOLA", "MANDU", "PATRATU", "CHITARPUR"],
    "BOKARO": ["CHAS", "CHANDANKIYARI", "BERMO", "GOMIA", "BOKARO", "JARIDIH", "KASMAR", "NAWADIH", "PETERBAR"],
    "DHANBAD": ["DHANBAD", "BAGHMARA", "BALIAPUR", "GOVINDPUR", "JHARIA", "NIRSA", "TOPCHANCHI", "TUNDI", "PURBO TUNDI", "ECL"],
    "GIRIDIH": ["GIRIDIH", "BAGODAR", "BENGIABAD", "BIRNI", "DEORI", "DHANWAR", "DUMRI", "GANDEY", "GAWAN", "JAMUA", "PIRTAND", "SURIYA", "TISRI"],
    "CHATRA": ["CHATRA", "HUNTERGANJ", "ITARHI", "KANHAPRA", "KUNDA", "LAWALAUNG", "MAYUR HAND", "PATHALGADA", "PRATAPPUR", "SIMARIA", "TANDWA"],
    "KODERMA": ["KODERMA", "JHUMRI TELAIYA", "CHANDWARA", "DOMCHANCH", "JAINAGAR", "MARKACHO", "SATGAWAN"],
    "DEOGHAR": ["DEOGHAR", "MADHUPUR", "DEVIPUR", "KARON", "MARGO MUNDA", "MOHANPUR", "PALOJORI", "SARATH", "SARWAN", "SONARAITHARHI"],
    "DUMKA": ["DUMKA", "GOPIKANDAR", "JAMA", "JARMUNDI", "KATHIKUND", "MASALIA", "RAMGARH DUMKA", "RANISHWAR", "SARAIYAHAT", "SHIKARIPARA"],
    "GODDA": ["GODDA", "BOARIJOR", "MAHAGAMA", "MEHERMA", "PATHARGAMA", "PORAIYAHAT", "SUNDARPAHARI", "THAKURGANGI"],
    "JAMTARA": ["JAMTARA", "FATHEPUR", "KUNDAHIT", "NARAYANPUR", "NALA", "KARMATAUR"],
    "PAKUR": ["PAKUR", "HIRANPUR", "LITIPARA", "AMRAPARA", "MAHESHPUR", "PAKURIA"],
    "SAHIBGANJ": ["SAHIBGANJ", "BORIO", "BARHARWA", "MANDRO", "TALJHARI", "RAJMAHAL", "PATNA SAHIBGANJ", "UDHWA"]
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

# ================= HELPER & REPOSITORY UTILITIES =================

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

def match_district_from_text(raw_text):
    text_upper = raw_text.upper()
    for dist, blocks in JHARKHAND_BLOCK_DISTRICT_MAP.items():
        if dist in text_upper:
            return dist
        for blk in blocks:
            if re.search(r'\b' + re.escape(blk) + r'\b', text_upper):
                return dist
    return "KHUNTI"

def get_clean_num(text, labels):
    for label in labels:
        pat = rf"{re.escape(label)}\s*[:\-]?\s*[₹Rs\.\s]*([0-9][0-9,]*(?:\.[0-9]+)?)"
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return float(m.group(1).replace(',', ''))
            except Exception:
                pass
    return 0.0

def get_next_matrix_cell(level, current_basic):
    if level in CPC_7TH_MATRIX:
        cells = CPC_7TH_MATRIX[level]
        for idx, cell in enumerate(cells):
            if int(current_basic) == cell and idx + 1 < len(cells):
                return cells[idx + 1]
            elif int(current_basic) < cell:
                return cell
        if cells:
            return cells[-1]
    return int(current_basic)

def get_matching_levels(basic_pay):
    matches = []
    b_val = int(basic_pay)
    for lvl, cells in CPC_7TH_MATRIX.items():
        if b_val in cells:
            matches.append(lvl)
    return matches

def find_nearest_level_by_amount(basic_pay):
    b_val = int(basic_pay)
    best_lvl = "LEVEL 7 (GP 4600)"
    min_diff = 999999
    for lvl, cells in CPC_7TH_MATRIX.items():
        for c in cells:
            diff = abs(c - b_val)
            if diff < min_diff:
                min_diff = diff
                best_lvl = lvl
    return best_lvl

def parse_slip_in_memory(uploaded_file):
    extracted = {
        'name': '', 'pan': '', 'designation': 'ASSISTANT TEACHER', 'gpf_no': '', 'office_name': '',
        'basic': 55200.0, 'da': 27600.0, 'hra': 4968.0, 'medical': 1000.0, 'gpf': 5000.0, 'gis': 60.0, 'ptax': 200.0, 'tds': 3000.0,
        'inc_month': '1ST JULY', 'inc_basic': 56900.0, 'pay_level': 'LEVEL 7 (GP 4600)', 'auto_district': 'KHUNTI', 'auto_state': 'JHARKHAND',
        'employer_type': 'STATE GOVERNMENT', 'pension_type': 'OLD PENSION (GPF / OPS)', 'arrear_da': 0.0, 'arrear_pay': 0.0, 'custom_arrear_rows': []
    }
    try:
        reader = PdfReader(uploaded_file)
        pages_text = [p.extract_text() or "" for p in reader.pages]
        full_text = "\n".join(pages_text)
        raw_clean = re.sub(r'[ \t]+', ' ', full_text).upper()
        
        extracted['auto_district'] = match_district_from_text(raw_clean)
        pan_m = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', raw_clean)
        if pan_m: extracted['pan'] = pan_m.group(1).strip()
        
        name_m = re.search(r'EMPLOYEE\s*NAME\s*[:\-]?\s*([A-Z\s\.]+?)(?=\s*PAN|\s*DDO|\s*DESIGNATION|\n|$)', raw_clean)
        if name_m:
            c = name_m.group(1).strip()
            if len(c) > 2 and not any(ch.isdigit() for ch in c): extracted['name'] = c
            
        des_m = re.search(r'DESIGNATION\s*[:\-]?\s*([A-Z0-9\s\.\+\/\-]+?)(?=\s*PAY\s*SCALE|\s*TV|\s*ALLOWANCES|\n|$)', raw_clean)
        if des_m: extracted['designation'] = des_m.group(1).strip()
        
        gpf_m = re.search(r'(?:EMPLOYEE\s*)?(?:GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', raw_clean)
        if gpf_m: extracted['gpf_no'] = gpf_m.group(1).strip()

        b_val = get_clean_num(raw_clean, ["BASIC", "मूल वेतन"])
        if b_val > 0: extracted['basic'] = b_val
        da_val = get_clean_num(raw_clean, ["DA", "DEARNESS ALLOWANCE"])
        if da_val > 0: extracted['da'] = da_val
        hra_val = get_clean_num(raw_clean, ["HRA"])
        if hra_val > 0: extracted['hra'] = hra_val
        med_val = get_clean_num(raw_clean, ["MEDICAL"])
        if med_val > 0: extracted['medical'] = med_val
        gpf_val = get_clean_num(raw_clean, ["GPF", "NPS", "PRAN", "EPF"])
        if gpf_val > 0: extracted['gpf'] = gpf_val
        tds_val = get_clean_num(raw_clean, ["I.TAX", "ITAX", "1.TAX", "TDS"])
        if tds_val > 0: extracted['tds'] = tds_val
    except Exception:
        pass
    return extracted

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

# ================= DATABASE INITIALIZATION =================

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
            "admin_username": "__nit@def@admin26__",
            "admin_password": "19052027def@admin",
            "form_fee": "100",
            "upi_id": "nitinmallick111-1@okicici",
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
        "tot_arrear_da": sum(money(t.get("da_arrear",0)) for t in active_transactions),
        "tot_arrear_pay": sum(money(t.get("pay_arrear",0)) for t in active_transactions),
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

# --------------------------- PDF DUAL-ORIENTATION TEMPLATE ---------------------------

HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&family=Roboto:wght@400;500;700&display=swap');
  
  @page {
    size: A4 portrait;
    margin: 6mm 8mm 6mm 8mm;
  }
  
  @page landscape-section {
    size: A4 landscape;
    margin: 6mm 8mm 6mm 8mm;
  }
  
  * { 
    box-sizing: border-box; 
    -webkit-print-color-adjust: exact; 
    text-transform: uppercase;
  }
  
  body { 
    font-family: 'Noto Sans Devanagari', 'Roboto', 'Arial Unicode MS', sans-serif; 
    font-size: 9px; 
    color: #000; 
    line-height: 1.2; 
    margin: 0; 
    padding: 0; 
  }
  
  .page-portrait {
    page-break-after: always;
    page-break-inside: avoid;
    position: relative;
    width: 100%;
  }
  
  .page-landscape {
    page: landscape-section;
    page-break-after: always;
    page-break-inside: avoid;
    position: relative;
    width: 100%;
  }
  
  .center { text-align: center; } 
  .right { text-align: right; } 
  .bold { font-weight: 700; }
  
  .title-main { font-size: 11px; font-weight: 700; line-height: 1.3; }
  .title-sub { font-size: 12.5px; font-weight: 700; line-height: 1.3; margin: 2px 0; }
  
  table { 
    width: 100%; 
    border-collapse: collapse; 
    margin-top: 3px; 
    margin-bottom: 3px; 
  }
  
  table.border, table.border th, table.border td { 
    border: 0.8px solid #000; 
  }
  
  th, td { 
    padding: 2.5px 4px; 
    vertical-align: middle; 
  }
  
  .no-border td { 
    border: none !important; 
    padding: 1.5px 3px; 
  }
  
  .bg-gray { 
    background-color: #f2f2f2 !important; 
  }
  
  .sign-area { 
    margin-top: 15px; 
    width: 100%; 
  }
  
  .sign-box-space {
    height: 38px;
  }
  
  .pdf-footer-credit {
    position: absolute;
    bottom: 2mm;
    left: 0;
    width: 100%;
    text-align: center;
    font-size: 8px;
    color: #555;
    border-top: 0.5px solid #ccc;
    padding-top: 2px;
  }
  
  {% if is_trial %}
  .watermark-layer-p {
    position: absolute;
    top: 32%;
    left: 2%;
    width: 96%;
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    color: rgba(220, 53, 69, 0.16);
    transform: rotate(-30deg);
    border: 3px dashed rgba(220, 53, 69, 0.22);
    padding: 25px 10px;
    letter-spacing: 2px;
    pointer-events: none;
    z-index: 10;
  }
  
  .watermark-layer-l {
    position: absolute;
    top: 30%;
    left: 10%;
    width: 80%;
    text-align: center;
    font-size: 52px;
    font-weight: 800;
    color: rgba(220, 53, 69, 0.16);
    transform: rotate(-22deg);
    border: 3px dashed rgba(220, 53, 69, 0.22);
    padding: 30px 10px;
    letter-spacing: 2px;
    pointer-events: none;
    z-index: 10;
  }
  {% endif %}
</style>
</head>
<body>
<!-- SECTION 1: FORM 16 PART A (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-sub">T.D.S.<br>FORM NO. 16<br>PART A</div>
  <div class="center" style="font-size: 8px; margin-bottom: 6px;">
    CERTIFICATE UNDER SECTION 203 OF THE INCOME-TAX ACT, 1961 FOR TAX DEDUCTION AT SOURCE FROM INCOME CHARGEABLE UNDER THE HEAD "SALARIES"
  </div>
  
  <table class="border">
    <tr>
      <td style="width: 50%; vertical-align: top; height: 50px;">
        <b>Name and address of the Employer:</b><br>
        {{ ddo.department }}, {{ ddo.district }} ({{ ddo.state }})<br>
        {% if ddo.address %}{{ ddo.address }}<br>{% endif %}
        City: {{ ddo.city or ddo.district }} &nbsp;&nbsp;&nbsp;&nbsp; Pin code: {{ ddo.pincode or '------' }}
      </td>
      <td style="width: 50%; vertical-align: top; height: 50px;">
        <b>Name and address of the Employee:</b><br>
        <b>{{ emp.name }}</b><br>
        {{ emp.office_name }}<br>
        District: {{ ddo.district }} ({{ ddo.state }})
      </td>
    </tr>
    <tr>
      <td>
        <table class="no-border" style="width: 100%;">
          <tr><td><b>PAN of the Deductor:</b></td><td><b>TAN of the Deductor:</b> {{ ddo.tan }}</td></tr>
        </table>
      </td>
      <td>
        <table class="no-border" style="width: 100%;">
          <tr>
            <td><b>PAN of the Employee:</b><br>{{ emp.pan }}</td>
            <td><b>Employee Reference No.:</b><br>{{ emp.gpf_no or 'N/A' }}</td>
          </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td>
        <b>CIT (TDS):</b><br>
        Address: ......................................................<br>
        City: {{ ddo.city or ddo.district }} &nbsp;&nbsp;&nbsp;&nbsp; Pin code: {{ ddo.pincode or '------' }}
      </td>
      <td>
        <table class="no-border" style="width: 100%;">
          <tr>
            <td><b>Assessment Year:</b><br>{{ emp.ay }}</td>
            <td><b>Period with Employer:</b><br>From: 01.04.2024 &nbsp; To: 31.03.2025</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
  <div style="font-weight: 700; font-size: 8.5px; margin-top: 5px;">
    Summary of amount paid/credited and tax deducted at source thereon in respect of the employee
  </div>
  <table class="border">
    <tr class="bg-gray center bold" style="font-size: 8px;">
      <th>Quarter(s)</th>
      <th>Receipt Numbers of original quarterly statements of TDS under sub-section (3) of section 200</th>
      <th>Amount paid/credited</th>
      <th>Amount of tax deducted (Rs.)</th>
      <th>Amount of tax deposited/remitted (Rs.)</th>
    </tr>
    <tr class="center">
      <td>Quarter 1</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 2</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 3</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 4</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid * 0.25) }}</td>
    </tr>
    <tr class="bold bg-gray center">
      <td colspan="3">Total (Rs.)</td>
      <td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td>
    </tr>
  </table>
  <div style="font-weight: 700; font-size: 8.5px; margin-top: 5px;">
    I. DETAILS OF TAX DEDUCTED AND DEPOSITED IN THE CENTRAL GOVERNMENT ACCOUNT THROUGH BOOK ADJUSTMENT / CHALLAN
  </div>
  <table class="border" style="font-size: 7.5px;">
    <tr class="bg-gray bold center">
      <th style="width: 5%;">Sl.</th>
      <th>Tax Deposited (Rs.)</th>
      <th>Book Identification Number (BIN) / BSR</th>
      <th>DDO / Challan Serial No.</th>
      <th>Date of transfer voucher</th>
      <th>Status of matching</th>
    </tr>
    {% if deposits %}
      {% for d in deposits %}
      <tr class="center">
        <td>{{ loop.index }}</td>
        <td class="right">{{ "%.2f"|format(d['amount']) }}</td>
        <td>{{ d['bsr_code'] or d['bin'] or 'Book-Adj' }}</td>
        <td>{{ d['challan_serial'] or 'Treasury' }}</td>
        <td>{{ d['deposit_date'] }}</td>
        <td>MATCHED</td>
      </tr>
      {% endfor %}
    {% else %}
      <tr class="center">
        <td>1</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td>
        <td>Book Adjustment</td><td>Treasury Regular Bill</td><td>28.02.2025</td><td>MATCHED</td>
      </tr>
    {% endif %}
  </table>
  <div style="margin-top: 6px; font-size: 8.5px; border-top: 0.8px solid #000; padding-top: 4px;">
    <div class="center bold" style="margin-bottom: 2px;">Verification</div>
    I, <b>{{ ddo.officer_name }}</b>, son/daughter of <b>{{ ddo.father_name }}</b>, working in the capacity of <b>Drawing & Disbursing Officer (DDO)</b> do hereby certify that a sum of Rs. <b>{{ "%.2f"|format(tax.tds_paid) }}</b> has been deducted and deposited to the credit of the Central Government.
    <table class="no-border" style="margin-top: 10px;">
      <tr>
        <td style="width: 50%;">
          Place: {{ ddo.city or ddo.district }}<br>
          Date: {{ today_date }}<br>
          Designation: DDO
        </td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          ________________________________________<br>
          Signature of person responsible for deduction of tax<br>
          Full Name: <b>{{ ddo.officer_name }}</b>
        </td>
      </tr>
    </table>
  </div>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 2: FORM 16 PART B (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-sub">PART B (Annexure)</div>
  <div class="center bold" style="font-size: 9px; margin-bottom: 6px;">Certificate under section 203 of the Income-tax Act, 1961</div>
  <table class="border">
    <tr class="bg-gray bold center"><th style="width: 75%; text-align: left;">Details of Salary Paid and any other income and tax deducted</th><th style="width: 25%; text-align: right;">Amount (Rs.)</th></tr>
    <tr><td>1. Gross Salary</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>2. Less: Allowance to the extent exempt u/s 10</td><td class="right">0.00</td></tr>
    <tr><td>3. Balance (1 - 2)</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>4. Deductions under section 16(ia) Standard Deduction</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr class="bold"><td>5. Income chargeable under the head 'Salaries'</td><td class="right">{{ "%.2f"|format(tax.gross - tax.std_ded) }}</td></tr>
    <tr class="bold bg-gray"><td>6. Gross Total Income</td><td class="right">{{ "%.2f"|format(tax.gross_total_income) }}</td></tr>
    <tr><td>7. Deductions under Chapter VI-A</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
    <tr class="bold"><td>8. Total Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>9. Net Tax Liability</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>10. Total TDS Deducted</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>11. Balance Tax Payable / (Refundable)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  <div class="sign-area" style="margin-top: 15px;">
    <table class="no-border">
      <tr>
        <td style="width: 50%;">Place: {{ ddo.city or ddo.district }}<br>Date: {{ today_date }}</td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          ________________________________________<br>
          Signature of DDO
        </td>
      </tr>
    </table>
  </div>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 3: SCHEDULE OF INCOME TAX (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-main">{{ tax.regime }} के तहत</div>
  <div class="center title-sub">Schedule of Income - Tax</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 6px;">{{ emp.ay }}</div>
  <table class="no-border" style="margin-bottom: 6px;">
    <tr><td style="width: 25%;">करदाता का नाम</td><td>: <b>{{ emp.name }}</b></td></tr>
    <tr><td>पदनाम</td><td>: {{ emp.designation }}</td></tr>
    <tr><td>कार्यालय / विद्यालय का नाम</td><td>: {{ emp.office_name }}</td></tr>
    <tr><td>स्थायी लेखा संख्या (PAN)</td><td>: <b>{{ emp.pan }}</b></td></tr>
  </table>
  <table class="border">
    <tr class="bg-gray bold">
      <th style="width: 6%;">क</th>
      <th style="width: 70%; text-align: left;">वेतन स्रोत से आय का विवरण:</th>
      <th style="width: 24%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>मूल वेतन (Basic Salary)</td><td class="right">{{ "%.2f"|format(totals.basic) }}</td></tr>
    <tr><td>02.</td><td>महँगाई भत्ता (DA)</td><td class="right">{{ "%.2f"|format(totals.da) }}</td></tr>
    <tr><td>03.</td><td>मकान किराया भत्ता (HRA)</td><td class="right">{{ "%.2f"|format(totals.hra) }}</td></tr>
    <tr><td>04.</td><td>चिकित्सा भत्ता (Medical Allowance)</td><td class="right">{{ "%.2f"|format(totals.medical) }}</td></tr>
    <tr><td>05.</td><td>बकाया राशि (Arrears Total)</td><td class="right">{{ "%.2f"|format(totals.arrear) }}</td></tr>
    <tr class="bold bg-gray"><td>06.</td><td>सकल वेतन (Gross Salary)</td><td class="right">{{ "%.2f"|format(totals.gross) }}</td></tr>
  </table>
  <table class="border" style="margin-top: 6px;">
    <tr class="bg-gray bold">
      <th style="width: 6%;">ख</th>
      <th style="width: 70%; text-align: left;">आयकर की संगणना</th>
      <th style="width: 24%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>कर योग्य आय (Taxable Total Income)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>02.</td><td>कुल देय आयकर (Total Tax Liability)</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>03.</td><td>भुगतान किया गया कुल TDS</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>04.</td><td>शुद्ध देय / (रिफंड)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 4: MONTHLY SALARY LEDGER (LANDSCAPE) -->
<div class="page-landscape">
  {% if is_trial %}<div class="watermark-layer-l">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="center title-sub">मासिक वेतन एवं कटौतियों की विवरणी (Monthly Salary & Transaction Ledger)</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 8px;">{{ emp.name }} (PAN: {{ emp.pan }}) | {{ emp.office_name }}</div>
  <table class="border" style="font-size: 8.5px; margin-top: 6px;">
    <tr class="bg-gray center bold">
      <th>Type / Period</th><th>Bill No</th><th>Basic</th><th>DA</th><th>HRA</th><th>Med</th><th>Arrears</th><th>Gross</th><th>GPF/NPS</th><th>GIS</th><th>PTax</th><th>TDS</th><th>Net</th>
    </tr>
    {% for r in records %}
    {% if r.status != 'VOID' %}
    <tr>
      <td><b>{{ r.payment_month }}</b> ({{ r.transaction_type }})</td>
      <td>{{ r.bill_number or '-' }}</td>
      <td class="right">{{ "%.2f"|format(r.basic) }}</td>
      <td class="right">{{ "%.2f"|format(r.da) }}</td>
      <td class="right">{{ "%.2f"|format(r.hra) }}</td>
      <td class="right">{{ "%.2f"|format(r.medical) }}</td>
      <td class="right">{{ "%.2f"|format(r.da_arrear + r.pay_arrear + r.hra_arrear + r.medical_arrear + r.other_arrear) }}</td>
      <td class="right bold">{{ "%.2f"|format(r.gross) }}</td>
      <td class="right">{{ "%.2f"|format(r.gpf + r.nps) }}</td>
      <td class="right">{{ "%.2f"|format(r.gis) }}</td>
      <td class="right">{{ "%.2f"|format(r.professional_tax) }}</td>
      <td class="right">{{ "%.2f"|format(r.tds) }}</td>
      <td class="right bold">{{ "%.2f"|format(r.net) }}</td>
    </tr>
    {% endif %}
    {% endfor %}
    <tr class="bold bg-gray">
      <td colspan="2">TOTAL</td>
      <td class="right">{{ "%.2f"|format(totals.basic) }}</td>
      <td class="right">{{ "%.2f"|format(totals.da) }}</td>
      <td class="right">{{ "%.2f"|format(totals.hra) }}</td>
      <td class="right">{{ "%.2f"|format(totals.medical) }}</td>
      <td class="right">{{ "%.2f"|format(totals.arrear) }}</td>
      <td class="right">{{ "%.2f"|format(totals.gross) }}</td>
      <td class="right">{{ "%.2f"|format(totals.gpf + totals.nps) }}</td>
      <td class="right">{{ "%.2f"|format(totals.gis) }}</td>
      <td class="right">{{ "%.2f"|format(totals.ptax) }}</td>
      <td class="right">{{ "%.2f"|format(totals.tds) }}</td>
      <td class="right">{{ "%.2f"|format(totals.net) }}</td>
    </tr>
  </table>
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>
</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, transactions, tax_summary, totals, deposits=None, decl_dict=None, is_trial=False):
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF dependencies unavailable. Install jinja2 and weasyprint.")
    
    active_txs = [t for t in transactions if str(t.get('status', 'ACTIVE')).upper() != 'VOID']
    
    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=active_txs, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=decl_dict or {}, 
        today_date=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

# ================= APPLICATION SUITE & ROUTING =================

def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    st.markdown("#### 📄 Salary Slip Upload & Dynamic Auto-Fill (Scan)")
    slip_up = st.file_uploader(
        "Upload Salary Slip (PDF) — District, Sector & Basic data auto-detect ho jayengi:", 
        type=["pdf"], 
        key=f"{prefix}_slip"
    )
    
    scanned_data = None
    if slip_up:
        if f"{prefix}_last_uploaded" not in st.session_state or st.session_state[f"{prefix}_last_uploaded"] != slip_up.name:
            scanned_data = parse_slip_in_memory(slip_up)
            st.session_state[f"{prefix}_scanned"] = scanned_data
            st.session_state[f"{prefix}_last_uploaded"] = slip_up.name
            if scanned_data.get('pan'):
                st.session_state[f"{prefix}_pan_field"] = scanned_data['pan'].upper()
            st.rerun()

    scanned_data = st.session_state.get(f"{prefix}_scanned", None)
    if scanned_data and scanned_data.get('pan'):
        with st.expander("📋 Extracted Slip Data Summary & Auto-Detection", expanded=True):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Employee Name", (scanned_data.get('name') or "N/A").upper())
            r2.metric("PAN Number", (scanned_data.get('pan') or "N/A").upper())
            r3.metric("Auto District", (scanned_data.get('auto_district') or "KHUNTI").upper())
            r4.metric("Basic Pay", f"₹{scanned_data.get('basic', 0):,.0f}")

    pan_in = st.text_input("Permanent Account Number (PAN) *", placeholder="ABCDE1234F", key=f"{prefix}_pan_field").upper().strip()
    
    if pan_in and len(pan_in) == 10:
        conn = db_connect()
        y_rec = conn.execute("SELECT id, office_name, tax_regime FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()
        conn.close()
        
        if not y_rec:
            init_name = scanned_data.get('name', 'NEW EMPLOYEE') if scanned_data else 'NEW EMPLOYEE'
            init_des = scanned_data.get('designation', 'CLERK') if scanned_data else 'CLERK'
            if st.button("Initialize New Employee Yearly Ledger"):
                with db_connect() as conn:
                    rules = get_tax_rules(GLOBAL_AY)
                    conn.execute("INSERT OR IGNORE INTO employee_yearly_records (ay, pan, name, designation, office_name, tax_regime) VALUES (?, ?, ?, ?, ?, ?)",
                                  (GLOBAL_AY, pan_in, init_name, init_des, "DEFAULT SCHOOL", rules["default_regime"]))
                    conn.commit()
                st.rerun()
        else:
            y_id, office_name, current_regime = y_rec[0], y_rec[1], y_rec[2]
            st.success(f"Loaded Yearly Record ID: {y_id} | Office: {office_name}")
            
            rules = get_tax_rules(GLOBAL_AY)
            
            conn = db_connect()
            tx_rows = conn.execute("SELECT * FROM salary_transactions WHERE yearly_record_id=?", (y_id,)).fetchall()
            conn.close()
            
            tx_data = [dict(r) for r in tx_rows]
            df_tx = pd.DataFrame(tx_data) if tx_data else pd.DataFrame(columns=TX_COLUMNS)
            
            st.markdown("##### ✏️ Interactive Transaction Register (Editable Table)")
            edited_df = st.data_editor(
                df_tx,
                num_rows="dynamic",
                key=f"{prefix}_editor",
                use_container_width=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "transaction_type": st.column_config.SelectboxColumn("Type", options=["REGULAR","ARREAR","RECOVERY","ADJUSTMENT","OTHER"]),
                    "payment_month": st.column_config.SelectboxColumn("Payment Month", options=MONTHS),
                }
            )
            
            if st.button("💾 Save Ledger Transactions & Validate"):
                proposed = []
                for _, row in edited_df.iterrows():
                    d = normalize_transaction(dict(row), rules)
                    proposed.append(d)

                errors, warnings = validate_transactions(proposed)
                if errors:
                    st.error("❌ VALIDATION FAILED — COMMIT & PDF GENERATION BLOCKED:")
                    for e in errors:
                        st.markdown(f"- {e}")
                    return

                conn = db_connect()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    valid_ids = {r["id"] for r in conn.execute("SELECT id FROM salary_transactions WHERE yearly_record_id=?", (y_id,)).fetchall()}
                    submitted_ids = {int(r["id"]) for r in proposed if r.get("id") not in (None, "", 0) and not pd.isna(r.get("id"))}

                    for tid in sorted(valid_ids - submitted_ids):
                        old = conn.execute("SELECT * FROM salary_transactions WHERE id=?", (tid,)).fetchone()
                        if old and str(old["status"]).upper() != "VOID":
                            old_dict = dict(old)
                            new_dict = dict(old_dict)
                            new_dict["status"] = "VOID"
                            conn.execute("UPDATE salary_transactions SET status='VOID', updated_at=? WHERE id=?", (now_text(), tid))
                            audit_insert(conn, tid, y_id, "DELETE", old_dict, new_dict, "Removed from editor")

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
                            old = conn.execute("SELECT * FROM salary_transactions WHERE id=?", (tid,)).fetchone()
                            old_dict = dict(old) if old else None
                            conn.execute("""UPDATE salary_transactions SET 
                                financial_year=?, assessment_year=?, transaction_type=?, payment_month=?, payment_date=?,
                                bill_number=?, bill_date=?, original_salary_month=?, original_salary_year=?,
                                original_period_from=?, original_period_to=?, arrear_type=?, basic=?, da=?, hra=?, medical=?,
                                other_allowance=?, da_arrear=?, pay_arrear=?, hra_arrear=?, medical_arrear=?, other_arrear=?,
                                gross=?, gpf=?, nps=?, gis=?, professional_tax=?, tds=?, other_deduction=?, recovery=?, net=?,
                                remarks=?, source_reference=?, updated_at=?, updated_by=?, status=? WHERE id=?""", params + (tid,))
                            audit_insert(conn, tid, y_id, "UPDATE", old_dict, dict(tx))
                        else:
                            conn.execute("""INSERT INTO salary_transactions(
                                yearly_record_id, financial_year, assessment_year, transaction_type, payment_month, payment_date,
                                bill_number, bill_date, original_salary_month, original_salary_year, original_period_from,
                                original_period_to, arrear_type, basic, da, hra, medical, other_allowance, da_arrear, pay_arrear,
                                hra_arrear, medical_arrear, other_arrear, gross, gpf, nps, gis, professional_tax, tds,
                                other_deduction, recovery, net, remarks, source_reference, created_at, created_by, status)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (y_id, *params))
                            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                            audit_insert(conn, new_id, y_id, "INSERT", None, dict(tx))

                    conn.commit()
                    st.success("✅ Database committed successfully with audit trail!")
                except Exception as ex:
                    conn.rollback()
                    st.error(f"Database transaction rolled back: {ex}")
                    return
                finally:
                    conn.close()

                active_txs = load_transactions(y_id)
                declarations = get_declarations(y_id)
                totals, tax_summary = tax_engine(active_txs, current_regime, declarations, rules)
                
                deposits = get_tds_deposits(y_id)
                tds_rec = reconcile_tds(active_txs, deposits)
                form16_errs = reconcile_form_16_dataset(active_txs, tax_summary, totals, rules, declarations)
                sched_errs = reconcile_schedule_dataset(active_txs, totals)
                all_errs = form16_errs + sched_errs + tds_rec["errors"]

                if all_errs:
                    st.error("❌ RECONCILIATION GATES FAILED. PDF Generation Blocked.")
                    for err in all_errs:
                        st.markdown(f"- {err}")
                    return

                conn = db_connect()
                ddo_r = conn.execute("SELECT * FROM ddo_masters LIMIT 1").fetchone()
                conn.close()
                
                ddo_d = dict(ddo_r) if ddo_r else {
                    'state': 'JHARKHAND', 'district': 'KHUNTI', 'department': 'SCHOOL EDUCATION',
                    'officer_name': 'DDO OFFICER', 'father_name': 'FATHER', 'tan': 'PTIK01234A',
                    'address': 'SCHOOL CAMPUS', 'city': 'KHUNTI', 'pincode': '835210'
                }
                emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': record['name'], 'designation': record['designation'], 'office_name': office_name}

                pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, active_txs, tax_summary, totals, deposits=deposits, decl_dict=declarations, is_trial=False)
                st.success("🎉 All Validation & Reconciliation Gates Passed!")
                st.download_button("📥 Download Official Audit-Ready PDF Bundle", pdf_bytes, f"FORM16_{pan_in}_{GLOBAL_AY.replace(' ','_')}.pdf", "application/pdf")

# ================= TOP BAR & ROUTING =================

try:
    init_db()
except Exception as exc:
    st.error(f"Application startup aborted: {exc}")
    st.stop()

query_params = st.query_params
is_admin_url = query_params.get("admin", "").lower() == "true"

col_ay1, col_ay2 = st.columns([3, 1])
with col_ay1: st.markdown("## 🏛️ Kosh-Tax | Comprehensive TDS & Form 16 Portal")
with col_ay2: GLOBAL_AY = st.selectbox("Active Assessment Year", AY_OPTIONS, index=0)

if is_admin_url:
    tab_emp, tab_redownload, tab_admin = st.tabs([
        "👤 Public Employee Self-Service",
        "🔍 Already Paid? Re-Download Archive",
        "🔒 Admin Command Center"
    ])
else:
    tab_emp, tab_redownload = st.tabs([
        "👤 Public Employee Self-Service",
        "🔍 Already Paid? Re-Download Archive"
    ])
    tab_admin = None

with tab_emp:
    render_full_employee_suite(is_admin_mode=False, prefix="emp_public")

with tab_redownload:
    st.markdown("### 🔍 Re-Download Official Form 16 & Tax Schedule")
    rd_pan = st.text_input("Enter PAN Number", key="rd_pan_field").upper().strip()
    if rd_pan:
        with db_connect() as conn:
            y_rec = conn.execute("SELECT * FROM employee_yearly_records WHERE pan=?", (rd_pan,)).fetchone()
        if y_rec:
            st.success(f"Record found for: {y_rec['name']} | Office: {y_rec['office_name']}")
        else:
            st.error("No record found for this PAN.")

if tab_admin and is_admin_url:
    with tab_admin:
        if 'admin_logged_in' not in st.session_state:
            st.session_state.admin_logged_in = False

        if not st.session_state.admin_logged_in:
            st.markdown("### 🔒 Secure Admin Authentication Gateway")
            with st.form("admin_auth_form"):
                in_user = st.text_input("Admin Username")
                in_pass = st.text_input("Admin Password", type="password")
                btn_login = st.form_submit_button("Authenticate & Access Dashboard")
                if btn_login:
                    cur_u = get_setting('admin_username', '__nit@def@admin26__')
                    cur_p = get_setting('admin_password', '19052027def@admin')
                    if in_user == cur_u and in_pass == cur_p:
                        st.session_state.admin_logged_in = True
                        st.success("Authentication Successful!")
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password.")
        else:
            if st.button("🚪 Logout Admin"):
                st.session_state.admin_logged_in = False
                st.rerun()

            adm_sub_tab1, adm_sub_tab2, adm_sub_tab3, adm_sub_tab4, adm_sub_tab5, adm_sub_tab6 = st.tabs([
                "📊 Revenue & Analytics",
                "🗃️ Master DB Manager",
                "📥 Payment Queue",
                "🏦 Statutory TDS Deposits",
                "🏛️ DDO Master",
                "⚙️ Config & Credentials"
            ])
            with adm_sub_tab1:
                st.subheader("📊 Financial Collection Analytics")
                with db_connect() as conn:
                    raw_records = conn.execute("SELECT payment_status, amount_paid FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                total_rev = sum(r["amount_paid"] for r in raw_records if r["payment_status"] == 'APPROVED')
                st.metric("Total Approved Revenue", f"₹{total_rev:,.0f}")
            with adm_sub_tab2:
                st.subheader("🗃️ Master Database Manager")
                with db_connect() as conn:
                    users = conn.execute("SELECT id, pan, name, office_name, payment_status FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                st.write(f"Total Registered Profiles: {len(users)}")
                for u in users:
                    st.text(f"ID: {u['id']} | PAN: {u['pan']} | Name: {u['name']} | Office: {u['office_name']} | Status: {u['payment_status']}")
            with adm_sub_tab3:
                st.subheader("📥 Live Payment Queue")
                with db_connect() as conn:
                    reqs = conn.execute("SELECT id, pan, name, payment_status, payment_mode FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                for r in reqs:
                    st.text(f"PAN: {r['pan']} | Name: {r['name']} | Status: {r['payment_status']} | Mode: {r['payment_mode']}")
            with adm_sub_tab4:
                st.subheader("🏦 Statutory TDS Deposits (Challan / BIN)")
                st.write("Tag challans and BSR codes here.")
            with adm_sub_tab5:
                st.subheader("🏛️ DDO & Hierarchy Master")
                with db_connect() as conn:
                    ddo_table = conn.execute("SELECT id, district, department, officer_name, tan FROM ddo_masters").fetchall()
                st.dataframe(pd.DataFrame([dict(r) for r in ddo_table]), use_container_width=True)
            with adm_sub_tab6:
                st.subheader("⚙️ Config & Credentials")
                new_u = st.text_input("Admin Username", value=get_setting('admin_username', '__nit@def@admin26__'))
                new_p = st.text_input("Admin Password", type="password", value=get_setting('admin_password', '19052027def@admin'))
                if st.button("Update Credentials"):
                    set_setting('admin_username', new_u)
                    set_setting('admin_password', new_p)
                    st.success("Updated successfully!")

# ================= WEB FOOTER (BRANDING) =================
st.markdown("""
<div style="margin-top: 50px; text-align: center; color: #888; font-size: 11px; border-top: 1px solid #333; padding-top: 15px;">
  🏛️ <b>KOSH-TAX</b> | COMPREHENSIVE TDS & FORM 16 MANAGEMENT PORTAL<br>
  <span style="color: #aaa;">DESIGNED & DEVELOPED BY NITIN</span>
</div>
""", unsafe_allow_html=True)


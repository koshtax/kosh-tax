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

def calculate_gross(row):
    return round(sum(money(row.get(k, 0)) for k in COMPONENT_FIELDS), 2)

def calculate_net(row, gross=None):
    gross = calculate_gross(row) if gross is None else money(gross)
    return round(gross - sum(money(row.get(k, 0)) for k in DEDUCTION_FIELDS), 2)

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
        'name': '', 'pan': '', 'designation': 'ASSISTANT TEACHER', 'gpf_no': '', 'office_name': '',
        'basic': 55200.0, 'da': 27600.0, 'hra': 4968.0, 'medical': 1000.0, 'gpf': 5000.0, 'gis': 60.0, 'ptax': 200.0, 'tds': 3000.0,
        'auto_district': 'KHUNTI', 'auto_state': 'JHARKHAND', 'employer_type': 'STATE GOVERNMENT', 'pension_type': 'OLD PENSION (GPF / OPS)',
        'arrear_da': 0.0, 'arrear_pay': 0.0, 'custom_arrear_rows': []
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
        c.execute("""CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT)""")
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
            id INTEGER PRIMARY KEY AUTOINCREMENT, state TEXT NOT NULL DEFAULT 'JHARKHAND', district TEXT NOT NULL DEFAULT 'KHUNTI',
            department TEXT NOT NULL DEFAULT 'SCHOOL EDUCATION & LITERACY', officer_name TEXT NOT NULL DEFAULT '', father_name TEXT NOT NULL DEFAULT '',
            tan TEXT UNIQUE NOT NULL, address TEXT DEFAULT '', city TEXT DEFAULT '', pincode TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_master_profiles(
            pan TEXT PRIMARY KEY, name TEXT NOT NULL, designation TEXT NOT NULL, mobile TEXT DEFAULT '', email TEXT DEFAULT '',
            gpf_no TEXT DEFAULT '', last_pay_level TEXT DEFAULT '', last_basic_pay REAL DEFAULT 0, updated_at TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_yearly_records(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ay TEXT NOT NULL, ddo_id INTEGER, pan TEXT NOT NULL, name TEXT NOT NULL,
            designation TEXT NOT NULL, office_name TEXT NOT NULL, service_status TEXT DEFAULT 'NORMAL', pay_level TEXT DEFAULT '',
            employer_type TEXT DEFAULT 'STATE GOVERNMENT', pension_type TEXT DEFAULT 'GPF', tax_regime TEXT DEFAULT 'NEW REGIME',
            payment_status TEXT DEFAULT 'PENDING', payment_mode TEXT DEFAULT '', utr_no TEXT DEFAULT '', amount_paid REAL DEFAULT 0,
            created_at TEXT DEFAULT '', UNIQUE(ay, pan))""")

        c.execute("""CREATE TABLE IF NOT EXISTS salary_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, yearly_record_id INTEGER NOT NULL, financial_year TEXT NOT NULL, assessment_year TEXT NOT NULL,
            transaction_type TEXT DEFAULT 'REGULAR', payment_month TEXT DEFAULT '', payment_date TEXT DEFAULT '', bill_number TEXT DEFAULT '',
            bill_date TEXT DEFAULT '', original_salary_month TEXT DEFAULT '', original_salary_year TEXT DEFAULT '', original_period_from TEXT DEFAULT '',
            original_period_to TEXT DEFAULT '', arrear_type TEXT DEFAULT '', basic REAL DEFAULT 0, da REAL DEFAULT 0, hra REAL DEFAULT 0, medical REAL DEFAULT 0,
            other_allowance REAL DEFAULT 0, da_arrear REAL DEFAULT 0, pay_arrear REAL DEFAULT 0, hra_arrear REAL DEFAULT 0, medical_arrear REAL DEFAULT 0,
            other_arrear REAL DEFAULT 0, gross REAL DEFAULT 0, gpf REAL DEFAULT 0, nps REAL DEFAULT 0, gis REAL DEFAULT 0, professional_tax REAL DEFAULT 0,
            tds REAL DEFAULT 0, other_deduction REAL DEFAULT 0, recovery REAL DEFAULT 0, net REAL DEFAULT 0, remarks TEXT DEFAULT '', source_reference TEXT DEFAULT '',
            created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '', created_by TEXT DEFAULT '', updated_by TEXT DEFAULT '', status TEXT DEFAULT 'ACTIVE',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS transaction_audit_trail(
            id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER, yearly_record_id INTEGER, action_type TEXT NOT NULL,
            old_values TEXT, new_values TEXT, changed_by TEXT DEFAULT '', changed_at TEXT NOT NULL, reason TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_tax_declarations(
            id INTEGER PRIMARY KEY AUTOINCREMENT, yearly_record_id INTEGER UNIQUE, other_employer_salary REAL DEFAULT 0, house_property_loss REAL DEFAULT 0,
            bank_interest REAL DEFAULT 0, other_income REAL DEFAULT 0, relief_89 REAL DEFAULT 0, sec80c REAL DEFAULT 0, sec80d REAL DEFAULT 0,
            sec80e REAL DEFAULT 0, sec80g REAL DEFAULT 0, sec80tta REAL DEFAULT 0, notes TEXT DEFAULT '', updated_at TEXT DEFAULT '',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS tds_deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, yearly_record_id INTEGER NOT NULL, quarter TEXT NOT NULL, month_name TEXT DEFAULT '',
            amount REAL DEFAULT 0, deposit_date TEXT DEFAULT '', mode TEXT DEFAULT 'Challan', bsr_code TEXT DEFAULT '', challan_serial TEXT DEFAULT '',
            bin TEXT DEFAULT '', receipt_no TEXT DEFAULT '', ddo_serial_no TEXT DEFAULT '', form24g_no TEXT DEFAULT '', voucher_date TEXT DEFAULT '',
            remarks TEXT DEFAULT '', FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Database initialization failed")
        raise
    finally:
        conn.close()

init_db()
# ================= PART 2 START =================

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

        gross_calc = calculate_gross(tx)
        net_calc = calculate_net(tx, gross_calc)

        if any(money(tx.get(k,0)) < 0 for k in MONEY_FIELDS):
            errors.append(f"{label}: Negative monetary value detected.")

        if abs(gross_calc - money(tx.get("gross",0))) > 0.01:
            errors.append(f"{label}: Gross mismatch.")

        if abs(net_calc - money(tx.get("net",0))) > 0.01:
            errors.append(f"{label}: Net mismatch.")

        bill = str(tx.get("bill_number","") or "").strip().upper()
        if bill:
            if bill in seen_bills:
                errors.append(f"{label}: Duplicate bill number {bill}.")
            seen_bills[bill] = label

        if ttype == "REGULAR":
            month = str(tx.get("payment_month","") or "").upper().strip()
            if not month:
                errors.append(f"{label}: Regular salary missing payment month.")
            elif month in regular_months:
                errors.append(f"{label}: Duplicate REGULAR salary month {month}.")
            else:
                regular_months.add(month)

        if ttype == "ARREAR":
            if not str(tx.get("original_salary_month","") or "").strip() and not str(tx.get("original_period_from","") or "").strip():
                errors.append(f"{label}: ARREAR requires original salary period.")

    return errors, warnings

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
        chapter_vi_a = c80c + c80d
        slabs = rules["old_slabs"]
        rebate_limit = money(rules["rebate_limit_old"])
        rebate_max = money(rules["rebate_max_old"])

    taxable_income = max(0.0, gross_total_income - standard_deduction - chapter_vi_a)
    taxable_income = float(Decimal(str(taxable_income)).quantize(Decimal("10"), rounding=ROUND_HALF_UP))

    slab_tax = 0.0
    for lower, upper, rate in slabs:
        if taxable_income <= lower:
            continue
        taxable_part = taxable_income - lower if upper >= 999999999999 else min(taxable_income, upper) - lower
        slab_tax += max(0.0, taxable_part) * rate

    rebate = min(slab_tax, rebate_max) if taxable_income <= rebate_limit else 0.0
    tax_after_rebate = max(0.0, slab_tax - rebate)
    cess = round(tax_after_rebate * money(rules["cess_rate"]), 2)
    total_tax = max(0.0, tax_after_rebate + cess - relief_89)
    balance = round(total_tax - tds_paid, 2)

    totals = {
        "basic": round(sum(money(t.get("basic",0)) for t in active_transactions),2),
        "da": round(sum(money(t.get("da",0)) for t in active_transactions),2),
        "hra": round(sum(money(t.get("hra",0)) for t in active_transactions),2),
        "medical": round(sum(money(t.get("medical",0)) for t in active_transactions),2),
        "gross": gross_salary,
        "tds": tds_paid,
        "net": round(sum(money(t.get("net",0)) for t in active_transactions),2),
    }

    tax = {
        "regime": regime, "gross": gross_salary, "gross_total_income": gross_total_income,
        "std_ded": standard_deduction, "chapter_vi_a": chapter_vi_a, "taxable_income": taxable_income,
        "slab_tax": round(slab_tax,2), "rebate_87a": round(rebate,2), "cess": cess, "relief_89": relief_89,
        "total_tax": round(total_tax,2), "tds_paid": tds_paid, "net_balance": balance,
        "financial_year": rules["financial_year"], "assessment_year": rules["assessment_year"],
    }
    return totals, tax

HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
@page { size: A4 portrait; margin: 8mm; }
body { font-family: Arial, sans-serif; font-size: 10px; color: #000; }
.page { page-break-after: always; }
table { width: 100%; border-collapse: collapse; margin-top: 5px; }
table, th, td { border: 1px solid #000; padding: 4px; }
.right { text-align: right; } .center { text-align: center; } .bold { font-weight: bold; }
</style></head>
<body>
<div class="page">
  <h2>T.D.S. FORM NO. 16 — PART A & B</h2>
  <table>
    <tr><td><b>Employee Name:</b> {{ emp.name }}</td><td><b>PAN:</b> {{ emp.pan }}</td></tr>
    <tr><td><b>Assessment Year:</b> {{ emp.ay }}</td><td><b>Gross Salary:</b> ₹{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td><b>Taxable Income:</b> ₹{{ "%.2f"|format(tax.taxable_income) }}</td><td><b>Total Tax:</b> ₹{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td><b>TDS Paid:</b> ₹{{ "%.2f"|format(tax.tds_paid) }}</td><td><b>Balance Payable:</b> ₹{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
</div>
</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, transactions, tax_summary, totals, deposits=None, decl_dict=None, is_trial=False):
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF dependencies unavailable.")
    active_txs = [t for t in transactions if str(t.get('status', 'ACTIVE')).upper() != 'VOID']
    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=active_txs, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=decl_dict or {}, is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

def load_transactions(yid):
    with db_connect() as conn:
        rows = conn.execute("SELECT * FROM salary_transactions WHERE yearly_record_id=? AND status='ACTIVE' ORDER BY id", (yid,)).fetchall()
        return [dict(r) for r in rows]

def ensure_employee(ay, pan):
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM employee_yearly_records WHERE ay=? AND pan=?", (ay, pan)).fetchone()
        return dict(row) if row else None

def render_employee():
    st.subheader("📊 Spreadsheet Salary & Transaction Register")
    pan = st.text_input("PAN", placeholder="ABCDE1234F").strip().upper()
    if len(pan) != 10:
        st.info("Enter a valid 10-character PAN.")
        return

    record = ensure_employee(GLOBAL_AY, pan)
    if record is None:
        if st.button("Initialize New Employee Yearly Ledger"):
            rules = get_tax_rules(GLOBAL_AY)
            with db_connect() as conn:
                conn.execute("INSERT OR IGNORE INTO employee_yearly_records (ay, pan, name, designation, office_name, tax_regime) VALUES (?, ?, ?, ?, ?, ?)",
                             (GLOBAL_AY, pan, "NEW EMPLOYEE", "CLERK", "DEFAULT SCHOOL", rules["default_regime"]))
                conn.commit()
            st.rerun()
        return

    yid = record["id"]
    rules = get_tax_rules(GLOBAL_AY)
    
    active = load_transactions(yid)
    df = pd.DataFrame(active) if active else pd.DataFrame(columns=TX_COLUMNS)
    
    display_cols = ["id", "transaction_type", "payment_month", "bill_number", "basic", "da", "hra", "medical", "gross", "gpf", "tds", "net"]
    for col in display_cols:
        if col not in df.columns:
            df[col] = "" if col not in MONEY_FIELDS else 0.0

    edited = st.data_editor(df[display_cols], num_rows="dynamic", use_container_width=True, key="sal_editor")

    if st.button("💾 Save Ledger Transactions & Validate", type="primary"):
        proposed = []
        for _, row in edited.iterrows():
            d = dict(row)
            d["status"] = "ACTIVE"
            d["financial_year"] = rules["financial_year"]
            d["assessment_year"] = rules["assessment_year"]
            for m in MONEY_FIELDS:
                d[m] = money(d.get(m, 0))
            d["gross"] = calculate_gross(d)
            d["net"] = calculate_net(d, d["gross"])
            proposed.append(d)

        errors, warnings = validate_transactions(proposed)
        if errors:
            st.error("❌ VALIDATION FAILED — COMMIT BLOCKED:")
            for e in errors: st.write("•", e)
            return

        conn = db_connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for tx in proposed:
                conn.execute("""INSERT INTO salary_transactions(yearly_record_id, financial_year, assessment_year, transaction_type, payment_month, bill_number, basic, da, hra, medical, gross, gpf, tds, net, status)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (yid, tx["financial_year"], tx["assessment_year"], tx["transaction_type"], tx["payment_month"], tx["bill_number"],
                              tx["basic"], tx["da"], tx["hra"], tx["medical"], tx["gross"], tx["gpf"], tx["tds"], tx["net"], tx["status"]))
            conn.commit()
            st.success("✅ Saved successfully!")
        except Exception as ex:
            conn.rollback()
            st.error(f"Error: {ex}")
        finally:
            conn.close()

query_params = st.query_params
is_admin_url = query_params.get("admin", "").lower() == "true"

col_ay1, col_ay2 = st.columns([3, 1])
with col_ay1: st.markdown("## 🏛️ Kosh-Tax | Enterprise Portal")
with col_ay2: GLOBAL_AY = st.selectbox("Active Assessment Year", AY_OPTIONS, index=0)

if is_admin_url:
    tab_emp, tab_admin = st.tabs(["👤 Salary Register", "🔒 Admin Command Center"])
else:
    tab_emp = st.container()
    tab_admin = None

with tab_emp:
    render_employee()

if tab_admin and is_admin_url:
    with tab_admin:
        st.subheader("🔒 Admin Control Center")
        st.write("Admin access granted.")

st.markdown("<hr><div style='text-align:center;font-size:11px;'>🏛️ KOSH-TAX PORTAL</div>", unsafe_allow_html=True)

# ================= PART 2 END =================
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
import openpyxl
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
APP_VERSION = "2.5.0-full-monolithic-production"

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

def calculate_gross(row):
    return round(sum(money(row.get(k, 0)) for k in COMPONENT_FIELDS), 2)

def calculate_net(row, gross=None):
    gross = calculate_gross(row) if gross is None else money(gross)
    return round(gross - sum(money(row.get(k, 0)) for k in DEDUCTION_FIELDS), 2)

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
        'name': '', 'pan': '', 'designation': 'ASSISTANT TEACHER', 'gpf_no': '', 'office_name': '',
        'basic': 55200.0, 'da': 27600.0, 'hra': 4968.0, 'medical': 1000.0, 'gpf': 5000.0, 'gis': 60.0, 'ptax': 200.0, 'tds': 3000.0,
        'auto_district': 'KHUNTI', 'auto_state': 'JHARKHAND', 'employer_type': 'STATE GOVERNMENT', 'pension_type': 'OLD PENSION (GPF / OPS)',
        'arrear_da': 0.0, 'arrear_pay': 0.0, 'custom_arrear_rows': []
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
        c.execute("""CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT)""")
        defaults = {
            "admin_username": "__nit@def@admin26__",
            "admin_password": "19052027def@admin",
            "form_fee": "100",
            "upi_id": "nitinmallick111-1@okicici",
            "app_version": APP_VERSION,
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)", (k, v))

        c.execute("""CREATE TABLE IF NOT EXISTS master_states (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS master_districts (id INTEGER PRIMARY KEY AUTOINCREMENT, state_name TEXT, name TEXT, UNIQUE(state_name, name))""")
        c.execute("""CREATE TABLE IF NOT EXISTS master_departments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS master_offices (id INTEGER PRIMARY KEY AUTOINCREMENT, district TEXT, department TEXT, name_and_address TEXT UNIQUE)""")

        c.execute("""CREATE TABLE IF NOT EXISTS ddo_masters(
            id INTEGER PRIMARY KEY AUTOINCREMENT, state TEXT NOT NULL DEFAULT 'JHARKHAND', district TEXT NOT NULL DEFAULT 'KHUNTI',
            department TEXT NOT NULL DEFAULT 'SCHOOL EDUCATION & LITERACY', officer_name TEXT NOT NULL DEFAULT '', father_name TEXT NOT NULL DEFAULT '',
            tan TEXT UNIQUE NOT NULL, address TEXT DEFAULT '', city TEXT DEFAULT '', pincode TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_master_profiles(
            pan TEXT PRIMARY KEY, name TEXT NOT NULL, designation TEXT NOT NULL, mobile TEXT DEFAULT '', email TEXT DEFAULT '',
            gpf_no TEXT DEFAULT '', last_pay_level TEXT DEFAULT '', last_basic_pay REAL DEFAULT 0, updated_at TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_yearly_records(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ay TEXT NOT NULL, ddo_id INTEGER, pan TEXT NOT NULL, name TEXT NOT NULL,
            designation TEXT NOT NULL, office_name TEXT NOT NULL, service_status TEXT DEFAULT 'NORMAL', pay_level TEXT DEFAULT '',
            employer_type TEXT DEFAULT 'STATE GOVERNMENT', pension_type TEXT DEFAULT 'GPF', tax_regime TEXT DEFAULT 'NEW REGIME',
            payment_status TEXT DEFAULT 'PENDING', payment_mode TEXT DEFAULT '', utr_no TEXT DEFAULT '', amount_paid REAL DEFAULT 0,
            created_at TEXT DEFAULT '', UNIQUE(ay, pan))""")

        c.execute("""CREATE TABLE IF NOT EXISTS salary_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, yearly_record_id INTEGER NOT NULL, financial_year TEXT NOT NULL, assessment_year TEXT NOT NULL,
            transaction_type TEXT DEFAULT 'REGULAR', payment_month TEXT DEFAULT '', payment_date TEXT DEFAULT '', bill_number TEXT DEFAULT '',
            bill_date TEXT DEFAULT '', original_salary_month TEXT DEFAULT '', original_salary_year TEXT DEFAULT '', original_period_from TEXT DEFAULT '',
            original_period_to TEXT DEFAULT '', arrear_type TEXT DEFAULT '', basic REAL DEFAULT 0, da REAL DEFAULT 0, hra REAL DEFAULT 0, medical REAL DEFAULT 0,
            other_allowance REAL DEFAULT 0, da_arrear REAL DEFAULT 0, pay_arrear REAL DEFAULT 0, hra_arrear REAL DEFAULT 0, medical_arrear REAL DEFAULT 0,
            other_arrear REAL DEFAULT 0, gross REAL DEFAULT 0, gpf REAL DEFAULT 0, nps REAL DEFAULT 0, gis REAL DEFAULT 0, professional_tax REAL DEFAULT 0,
            tds REAL DEFAULT 0, other_deduction REAL DEFAULT 0, recovery REAL DEFAULT 0, net REAL DEFAULT 0, remarks TEXT DEFAULT '', source_reference TEXT DEFAULT '',
            created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '', created_by TEXT DEFAULT '', updated_by TEXT DEFAULT '', status TEXT DEFAULT 'ACTIVE',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS transaction_audit_trail(
            id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER, yearly_record_id INTEGER, action_type TEXT NOT NULL,
            old_values TEXT, new_values TEXT, changed_by TEXT DEFAULT '', changed_at TEXT NOT NULL, reason TEXT DEFAULT '')""")

        c.execute("""CREATE TABLE IF NOT EXISTS employee_tax_declarations(
            id INTEGER PRIMARY KEY AUTOINCREMENT, yearly_record_id INTEGER UNIQUE, other_employer_salary REAL DEFAULT 0, house_property_loss REAL DEFAULT 0,
            bank_interest REAL DEFAULT 0, other_income REAL DEFAULT 0, relief_89 REAL DEFAULT 0, sec80c REAL DEFAULT 0, sec80d REAL DEFAULT 0,
            sec80e REAL DEFAULT 0, sec80g REAL DEFAULT 0, sec80tta REAL DEFAULT 0, notes TEXT DEFAULT '', updated_at TEXT DEFAULT '',
            FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        c.execute("""CREATE TABLE IF NOT EXISTS tds_deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT, yearly_record_id INTEGER NOT NULL, quarter TEXT NOT NULL, month_name TEXT DEFAULT '',
            amount REAL DEFAULT 0, deposit_date TEXT DEFAULT '', mode TEXT DEFAULT 'Challan', bsr_code TEXT DEFAULT '', challan_serial TEXT DEFAULT '',
            bin TEXT DEFAULT '', receipt_no TEXT DEFAULT '', ddo_serial_no TEXT DEFAULT '', form24g_no TEXT DEFAULT '', voucher_date TEXT DEFAULT '',
            remarks TEXT DEFAULT '', FOREIGN KEY(yearly_record_id) REFERENCES employee_yearly_records(id))""")

        conn.commit()
    except Exception:
        conn.rollback()
        logging.exception("Database initialization failed")
        raise
    finally:
        conn.close()

init_db()

# ================= VALIDATION & RECONCILIATION =================

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

        gross_calc = calculate_gross(tx)
        net_calc = calculate_net(tx, gross_calc)

        if any(money(tx.get(k,0)) < 0 for k in MONEY_FIELDS):
            errors.append(f"{label}: Negative monetary value detected.")

        if abs(gross_calc - money(tx.get("gross",0))) > 0.01:
            errors.append(f"{label}: Gross mismatch.")

        if abs(net_calc - money(tx.get("net",0))) > 0.01:
            errors.append(f"{label}: Net mismatch.")

        bill = str(tx.get("bill_number","") or "").strip().upper()
        if bill:
            if bill in seen_bills:
                errors.append(f"{label}: Duplicate bill number {bill}.")
            seen_bills[bill] = label

        if ttype == "REGULAR":
            month = str(tx.get("payment_month","") or "").upper().strip()
            if not month:
                errors.append(f"{label}: Regular salary missing payment month.")
            elif month in regular_months:
                errors.append(f"{label}: Duplicate REGULAR salary month {month}.")
            else:
                regular_months.add(month)

        if ttype == "ARREAR":
            if not str(tx.get("original_salary_month","") or "").strip() and not str(tx.get("original_period_from","") or "").strip():
                errors.append(f"{label}: ARREAR requires original salary period.")

    return errors, warnings

def reconcile_form_16_dataset(active_txs, tax_summary, totals, fy_rules, decl_data):
    errors = []
    ledger_gross = totals["gross"]
    if abs(tax_summary["gross"] - ledger_gross) > 0.01:
        errors.append(f"Form-16 Gross does not match Ledger Gross.")
    return errors

def reconcile_schedule_dataset(active_txs, totals):
    errors = []
    tx_basic = sum(money(t.get("basic",0)) for t in active_txs)
    if abs(totals["basic"] - tx_basic) > 0.01:
        errors.append("Schedule Basic does not match transaction Basic sum.")
    return errors

def reconcile_tds(active_transactions, deposit_rows):
    errors = []
    tx_total = round(sum(money(t.get("tds",0)) for t in active_transactions), 2)
    return {"valid": not errors, "errors": errors, "transaction_tds": tx_total}

# ================= TAX ENGINE & PDF MASTER TEMPLATE =================

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
        chapter_vi_a = min(150000.0, money(declarations.get("sec80c",0))) + min(50000.0, money(declarations.get("sec80d",0)))
        slabs = rules["old_slabs"]
        rebate_limit = money(rules["rebate_limit_old"])
        rebate_max = money(rules["rebate_max_old"])

    taxable_income = max(0.0, gross_total_income - standard_deduction - chapter_vi_a)
    taxable_income = float(Decimal(str(taxable_income)).quantize(Decimal("10"), rounding=ROUND_HALF_UP))

    slab_tax = 0.0
    for lower, upper, rate in slabs:
        if taxable_income <= lower:
            continue
        taxable_part = taxable_income - lower if upper >= 999999999999 else min(taxable_income, upper) - lower
        slab_tax += max(0.0, taxable_part) * rate

    rebate = min(slab_tax, rebate_max) if taxable_income <= rebate_limit else 0.0
    tax_after_rebate = max(0.0, slab_tax - rebate)
    cess = round(tax_after_rebate * money(rules["cess_rate"]), 2)
    total_tax = max(0.0, tax_after_rebate + cess - relief_89)
    balance = round(total_tax - tds_paid, 2)

    totals = {
        "basic": round(sum(money(t.get("basic",0)) for t in active_transactions),2),
        "da": round(sum(money(t.get("da",0)) for t in active_transactions),2),
        "hra": round(sum(money(t.get("hra",0)) for t in active_transactions),2),
        "medical": round(sum(money(t.get("medical",0)) for t in active_transactions),2),
        "gross": gross_salary,
        "tds": tds_paid,
        "net": round(sum(money(t.get("net",0)) for t in active_transactions),2),
    }

    tax = {
        "regime": regime, "gross": gross_salary, "gross_total_income": gross_total_income,
        "std_ded": standard_deduction, "chapter_vi_a": chapter_vi_a, "taxable_income": taxable_income,
        "slab_tax": round(slab_tax,2), "rebate_87a": round(rebate,2), "cess": cess, "relief_89": relief_89,
        "total_tax": round(total_tax,2), "tds_paid": tds_paid, "net_balance": balance,
        "financial_year": rules["financial_year"], "assessment_year": rules["assessment_year"],
    }
    return totals, tax

HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
@page { size: A4 portrait; margin: 8mm; }
body { font-family: Arial, sans-serif; font-size: 10px; color: #000; }
.page { page-break-after: always; }
table { width: 100%; border-collapse: collapse; margin-top: 5px; }
table, th, td { border: 1px solid #000; padding: 4px; }
.right { text-align: right; } .center { text-align: center; } .bold { font-weight: bold; }
</style></head>
<body>
<div class="page">
  <h2>T.D.S. FORM NO. 16 — PART A & B</h2>
  <table>
    <tr><td><b>Employee Name:</b> {{ emp.name }}</td><td><b>PAN:</b> {{ emp.pan }}</td></tr>
    <tr><td><b>Assessment Year:</b> {{ emp.ay }}</td><td><b>Gross Salary:</b> ₹{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td><b>Taxable Income:</b> ₹{{ "%.2f"|format(tax.taxable_income) }}</td><td><b>Total Tax:</b> ₹{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td><b>TDS Paid:</b> ₹{{ "%.2f"|format(tax.tds_paid) }}</td><td><b>Balance Payable:</b> ₹{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
</div>
</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, transactions, tax_summary, totals, deposits=None, decl_dict=None, is_trial=False):
    if not PDF_AVAILABLE:
        raise RuntimeError("PDF dependencies unavailable.")
    active_txs = [t for t in transactions if str(t.get('status', 'ACTIVE')).upper() != 'VOID']
    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=active_txs, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=decl_dict or {}, is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

def load_transactions(yid):
    with db_connect() as conn:
        rows = conn.execute("SELECT * FROM salary_transactions WHERE yearly_record_id=? AND status='ACTIVE' ORDER BY id", (yid,)).fetchall()
        return [dict(r) for r in rows]

def ensure_employee(ay, pan):
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM employee_yearly_records WHERE ay=? AND pan=?", (ay, pan)).fetchone()
        return dict(row) if row else None

def audit_insert(conn, tx_id, yid, action, old_values=None, new_values=None, reason=""):
    conn.execute(
        """INSERT INTO transaction_audit_trail (transaction_id, yearly_record_id, action_type, old_values, new_values, changed_by, changed_at, reason)
           VALUES(?,?,?,?,?,?,?,?)""",
        (tx_id, yid, action, json.dumps(old_values, default=json_default) if old_values else None,
         json.dumps(new_values, default=json_default) if new_values else None, st.session_state.get("actor","USER"), now_text(), reason)
    )

# ================= PUBLIC & ADMIN SUITES =================

def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    st.markdown("#### 📄 Salary Slip Upload & Dynamic Auto-Fill (Scan)")
    slip_up = st.file_uploader("Upload Salary Slip (PDF):", type=["pdf"], key=f"{prefix}_slip")
    
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
        with st.expander("📋 Extracted Slip Data Summary", expanded=True):
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
                rules = DEFAULT_TAX_RULES[GLOBAL_AY]
                with db_connect() as conn:
                    conn.execute("INSERT OR IGNORE INTO employee_yearly_records (ay, pan, name, designation, office_name, tax_regime) VALUES (?, ?, ?, ?, ?, ?)",
                                  (GLOBAL_AY, pan_in, init_name, init_des, "DEFAULT SCHOOL", rules["default_regime"]))
                    conn.commit()
                st.rerun()
        else:
            y_id, office_name, current_regime = y_rec[0], y_rec[1], y_rec[2]
            st.success(f"Loaded Yearly Record ID: {y_id} | Office: {office_name}")
            
            rules = DEFAULT_TAX_RULES[GLOBAL_AY]
            active = load_transactions(y_id)
            df_tx = pd.DataFrame(active) if active else pd.DataFrame(columns=TX_COLUMNS)
            
            st.markdown("##### ✏️ Interactive Transaction Register (Editable Table)")
            edited_df = st.data_editor(
                df_tx[["id", "transaction_type", "payment_month", "bill_number", "basic", "da", "hra", "medical", "gross", "gpf", "tds", "net"]],
                num_rows="dynamic", key=f"{prefix}_editor", use_container_width=True,
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "transaction_type": st.column_config.SelectboxColumn("Type", options=["REGULAR","ARREAR","RECOVERY","ADJUSTMENT","OTHER"]),
                    "payment_month": st.column_config.SelectboxColumn("Payment Month", options=MONTHS),
                }
            )
            
            if st.button("💾 Save Ledger Transactions & Validate"):
                proposed = []
                for _, row in edited_df.iterrows():
                    d = dict(row)
                    d["status"] = "ACTIVE"
                    d["financial_year"] = rules["financial_year"]
                    d["assessment_year"] = rules["assessment_year"]
                    for m in MONEY_FIELDS:
                        d[m] = money(d.get(m, 0))
                    d["gross"] = calculate_gross(d)
                    d["net"] = calculate_net(d, d["gross"])
                    proposed.append(d)

                errors, warnings = validate_transactions(proposed)
                if errors:
                    st.error("❌ VALIDATION FAILED — COMMIT BLOCKED:")
                    for e in errors: st.write("•", e)
                    return

                conn = db_connect()
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    for tx in proposed:
                        conn.execute("""INSERT INTO salary_transactions(yearly_record_id, financial_year, assessment_year, transaction_type, payment_month, bill_number, basic, da, hra, medical, gross, gpf, tds, net, status)
                                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                     (yid, tx["financial_year"], tx["assessment_year"], tx["transaction_type"], tx["payment_month"], tx["bill_number"],
                                      tx["basic"], tx["da"], tx["hra"], tx["medical"], tx["gross"], tx["gpf"], tx["tds"], tx["net"], tx["status"]))
                    conn.commit()
                    st.success("✅ Saved successfully!")
                except Exception as ex:
                    conn.rollback()
                    st.error(f"Error: {ex}")
                finally:
                    conn.close()

# ================= APP ROUTING & TABS =================

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

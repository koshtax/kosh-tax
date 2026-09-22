import streamlit as st
import sqlite3
import openpyxl
from jinja2 import Template
from weasyprint import HTML
import io
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime, date
from pypdf import PdfReader
import pandas as pd

# ================= PAGE CONFIGURATION =================
st.set_page_config(
    page_title="Kosh-Tax | TDS & Form 16 Enterprise Management Portal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "tds_enterprise_master.sqlite"

# Complete 7th CPC Pay Matrix
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

JHARKHAND_MONTHS_CYCLE = [
    "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", 
    "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER", "JANUARY", "FEBRUARY"
]

AY_OPTIONS = ["AY 2025-26 (FY 2024-25)", "AY 2026-27 (FY 2025-26)"]

# ================= DATABASE INITIALIZATION & MIGRATION =================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS master_states (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS master_districts (id INTEGER PRIMARY KEY AUTOINCREMENT, state_name TEXT, name TEXT, UNIQUE(state_name, name))''')
    c.execute('''CREATE TABLE IF NOT EXISTS master_departments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS master_offices (id INTEGER PRIMARY KEY AUTOINCREMENT, district TEXT, department TEXT, name_and_address TEXT UNIQUE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ddo_masters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT NOT NULL,
        district TEXT NOT NULL,
        department TEXT NOT NULL,
        officer_name TEXT NOT NULL,
        father_name TEXT NOT NULL,
        tan TEXT UNIQUE NOT NULL,
        address TEXT,
        city TEXT,
        pincode TEXT
    )''')

    for col in ["address", "city", "pincode"]:
        try:
            c.execute(f"ALTER TABLE ddo_masters ADD COLUMN {col} TEXT")
        except Exception:
            pass

    c.execute('''CREATE TABLE IF NOT EXISTS employee_master_profiles (
        pan TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        designation TEXT NOT NULL,
        mobile TEXT,
        email TEXT,
        gpf_no TEXT,
        last_state TEXT,
        last_district TEXT,
        last_dept TEXT,
        last_office TEXT,
        last_ddo_id INTEGER,
        last_pay_level TEXT,
        last_basic_pay REAL,
        last_inc_month TEXT,
        employer_type TEXT DEFAULT 'STATE GOVERNMENT',
        pension_type TEXT DEFAULT 'GPF',
        updated_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS employee_yearly_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ay TEXT NOT NULL,
        ddo_id INTEGER,
        pan TEXT NOT NULL,
        name TEXT NOT NULL,
        designation TEXT NOT NULL,
        office_name TEXT NOT NULL,
        service_status TEXT DEFAULT 'NORMAL',
        pay_level TEXT,
        employer_type TEXT DEFAULT 'STATE GOVERNMENT',
        pension_type TEXT DEFAULT 'GPF',
        tax_regime TEXT DEFAULT 'NEW REGIME',
        start_basic REAL DEFAULT 0,
        inc_month TEXT DEFAULT 'NONE',
        inc_basic REAL DEFAULT 0,
        default_da REAL DEFAULT 0,
        default_hra REAL DEFAULT 0,
        default_med REAL DEFAULT 1000,
        default_gpf REAL DEFAULT 0,
        default_gis REAL DEFAULT 60,
        default_ptax REAL DEFAULT 200,
        monthly_tds REAL DEFAULT 0,
        mobile TEXT,
        email TEXT,
        payment_status TEXT DEFAULT 'PENDING',
        payment_mode TEXT,
        utr_no TEXT,
        amount_paid REAL DEFAULT 0,
        created_at TEXT,
        created_date TEXT,
        UNIQUE(ay, pan)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS salary_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        yearly_record_id INTEGER,
        financial_year TEXT NOT NULL,
        transaction_type TEXT DEFAULT 'REGULAR',
        payment_month TEXT,
        payment_date TEXT,
        bill_number TEXT,
        bill_date TEXT,
        original_salary_month TEXT,
        original_salary_year TEXT,
        arrear_type TEXT,
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
        remarks TEXT,
        source_reference TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (yearly_record_id) REFERENCES employee_yearly_records(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS employee_tax_declarations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        yearly_record_id INTEGER UNIQUE,
        other_employer_salary REAL DEFAULT 0,
        house_property_loss REAL DEFAULT 0,
        bank_interest REAL DEFAULT 0,
        other_income REAL DEFAULT 0,
        relief_89 REAL DEFAULT 0,
        sec80c REAL DEFAULT 0,
        sec80ccc REAL DEFAULT 0,
        sec80ccd REAL DEFAULT 0,
        sec80d REAL DEFAULT 0,
        sec80dd REAL DEFAULT 0,
        sec80ddb REAL DEFAULT 0,
        sec80e REAL DEFAULT 0,
        sec80ee REAL DEFAULT 0,
        sec80g REAL DEFAULT 0,
        sec80tta REAL DEFAULT 0,
        sec80u REAL DEFAULT 0,
        notes TEXT,
        updated_at TEXT,
        FOREIGN KEY (yearly_record_id) REFERENCES employee_yearly_records(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tds_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        yearly_record_id INTEGER,
        quarter TEXT,
        month_name TEXT,
        amount REAL DEFAULT 0,
        deposit_date TEXT,
        mode TEXT DEFAULT 'Challan',
        bsr_code TEXT,
        challan_serial TEXT,
        bin TEXT,
        receipt_no TEXT,
        ddo_serial_no TEXT,
        form24g_no TEXT,
        voucher_date TEXT,
        remarks TEXT,
        FOREIGN KEY (yearly_record_id) REFERENCES employee_yearly_records(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)''')
    for k, v in [('admin_username', '__nit@def@admin26__'), ('admin_password', '19052027def@admin'), ('form_fee', '100'), ('upi_id', 'nitinmallick111-1@okicici'), ('whitelisted_pans', ''), ('smtp_email', ''), ('smtp_password', '')]:
        c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (k, v))

    c.execute("UPDATE app_settings SET value='nitinmallick111-1@okicici' WHERE key='upi_id'")
    c.execute("INSERT OR IGNORE INTO master_states (name) VALUES ('JHARKHAND'), ('BIHAR'), ('WEST BENGAL')")
    for d in JHARKHAND_BLOCK_DISTRICT_MAP.keys():
        c.execute("INSERT OR IGNORE INTO master_districts (state_name, name) VALUES ('JHARKHAND', ?)", (d,))

    # Legacy migration
    try:
        legacy_check = c.execute("SELECT COUNT(*) FROM salary_transactions").fetchone()[0]
        if legacy_check == 0:
            old_ledgers = c.execute("SELECT yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay, gross, gpf, gis, ptax, tds, net FROM monthly_salary_ledgers").fetchall()
            for ol in old_ledgers:
                y_id, m_name, b, d, h, med, ada, apa, g, gp, gi, pt, td, net = ol
                fy_val = c.execute("SELECT ay FROM employee_yearly_records WHERE id=?", (y_id,)).fetchone()
                fy_str = fy_val[0] if fy_val else "AY 2025-26 (FY 2024-25)"
                c.execute('''INSERT INTO salary_transactions (
                    yearly_record_id, financial_year, transaction_type, payment_month, basic, da, hra, medical,
                    da_arrear, pay_arrear, gross, gpf, gis, professional_tax, tds, net, source_reference, created_at
                ) VALUES (?, ?, 'REGULAR', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'LEGACY_MIGRATION', ?)''',
                (y_id, fy_str, m_name, b, d, h, med, ada, apa, g, gp, gi, pt, td, net, datetime.now().strftime("%Y-%m-%d %H:%M")))
    except Exception:
        pass

    conn.commit()
    conn.close()

init_db()

# ================= HELPER & UTILITIES =================
def get_setting(key, default=""):
    conn = sqlite3.connect(DB_NAME)
    r = conn.cursor().execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return r[0] if r else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_NAME)
    conn.cursor().execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def is_pan_whitelisted(pan):
    wl = get_setting('whitelisted_pans', '')
    pans = [p.strip().upper() for p in wl.split(',') if p.strip()]
    return pan.strip().upper() in pans

def get_creatable_list(table, col, condition="1=1", params=()):
    conn = sqlite3.connect(DB_NAME)
    rows = conn.cursor().execute(f"SELECT DISTINCT {col} FROM {table} WHERE {condition} ORDER BY {col} ASC", params).fetchall()
    conn.close()
    return [r[0].upper() for r in rows if r[0]]

def add_creatable_item(table, col_data):
    conn = sqlite3.connect(DB_NAME)
    upper_col_data = {k: (v.upper() if isinstance(v, str) else v) for k, v in col_data.items()}
    cols = ", ".join(upper_col_data.keys())
    placeholders = ", ".join(["?"] * len(upper_col_data))
    try:
        conn.cursor().execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})", tuple(upper_col_data.values()))
        conn.commit()
    except Exception:
        pass
    conn.close()

# ================= VALIDATION ENGINE =================
def run_transaction_validation_engine(transactions):
    errors, warnings = [], []
    if not transactions:
        errors.append("No salary or arrear transactions found.")
        return errors, warnings
    
    regular_months_found = set()
    seen_bills = set()
    
    for idx, tx in enumerate(transactions, 1):
        t_type = str(tx.get('transaction_type', 'REGULAR')).upper()
        b = float(tx.get('basic', 0) or 0)
        d = float(tx.get('da', 0) or 0)
        h = float(tx.get('hra', 0) or 0)
        m = float(tx.get('medical', 0) or 0)
        ada = float(tx.get('da_arrear', 0) or 0)
        apa = float(tx.get('pay_arrear', 0) or 0)
        
        calc_gross = b + d + h + m + ada + apa
        stated_gross = float(tx.get('gross', 0) or 0)
        if abs(calc_gross - stated_gross) > 1.0:
            errors.append(f"Row {idx} ({tx.get('payment_month', 'N/A')}): Gross mismatch. Calculated ₹{calc_gross:,.2f} vs Stated ₹{stated_gross:,.2f}")
            
        gp = float(tx.get('gpf', 0) or 0)
        nps = float(tx.get('nps', 0) or 0)
        gis = float(tx.get('gis', 0) or 0)
        pt = float(tx.get('professional_tax', 0) or 0)
        tds = float(tx.get('tds', 0) or 0)
        
        calc_net = stated_gross - (gp + nps + gis + pt + tds)
        stated_net = float(tx.get('net', 0) or 0)
        if abs(calc_net - stated_net) > 1.0:
            errors.append(f"Row {idx} ({tx.get('payment_month', 'N/A')}): Net salary mismatch. Calculated ₹{calc_net:,.2f} vs Stated ₹{stated_net:,.2f}")
            
        if t_type == 'REGULAR':
            m_name = (tx.get('payment_month') or '').upper().strip()
            if m_name in regular_months_found:
                errors.append(f"Duplicate regular salary entry detected for month: {m_name}")
            regular_months_found.add(m_name)
        elif t_type == 'ARREAR':
            if not tx.get('original_salary_month') or not tx.get('original_salary_year'):
                errors.append(f"Row {idx}: Arrear transaction is missing original period (Month/Year).")
                
        b_no = tx.get('bill_number')
        if b_no and str(b_no).strip():
            if str(b_no).strip().upper() in seen_bills:
                errors.append(f"Duplicate bill reference number detected: {b_no}")
            seen_bills.add(str(b_no).strip().upper())
            
    expected_months = set(JHARKHAND_MONTHS_CYCLE)
    missing_months = expected_months - regular_months_found
    if missing_months:
        warnings.append(f"Missing regular salary months in ledger: {', '.join(missing_months)}")
        
    return errors, warnings

# ================= AUTHORITATIVE RECONCILIATION & TAX ENGINE =================
def compute_master_ledger_and_tax(transactions, regime="NEW REGIME", decl_data=None):
    if decl_data is None:
        decl_data = {}
        
    tot_basic = sum(float(t.get('basic', 0) or 0) for t in transactions)
    tot_da = sum(float(t.get('da', 0) or 0) for t in transactions)
    tot_hra = sum(float(t.get('hra', 0) or 0) for t in transactions)
    tot_med = sum(float(t.get('medical', 0) or 0) for t in transactions)
    
    tot_da_arrear = sum(float(t.get('da_arrear', 0) or 0) for t in transactions)
    tot_pay_arrear = sum(float(t.get('pay_arrear', 0) or 0) for t in transactions)
    
    annual_gross_salary = sum(float(t.get('gross', 0) or 0) for t in transactions)
    tot_gpf = sum(float(t.get('gpf', 0) or 0) for t in transactions)
    tot_nps = sum(float(t.get('nps', 0) or 0) for t in transactions)
    tot_gis = sum(float(t.get('gis', 0) or 0) for t in transactions)
    tot_ptax = sum(float(t.get('professional_tax', 0) or 0) for t in transactions)
    tot_tds_paid = sum(float(t.get('tds', 0) or 0) for t in transactions)
    tot_net = sum(float(t.get('net', 0) or 0) for t in transactions)
    
    other_emp = float(decl_data.get('other_employer_salary', 0))
    house_loss = float(decl_data.get('house_property_loss', 0))
    other_inc = float(decl_data.get('bank_interest', 0)) + float(decl_data.get('other_income', 0))
    relief_89 = float(decl_data.get('relief_89', 0))
    
    gross_total_income = annual_gross_salary + other_emp + other_inc - house_loss
    
    if regime == "NEW REGIME":
        std_ded = 75000.0
        chapter_vi_a = 0.0
        taxable_income = round(max(0.0, gross_total_income - std_ded), -1)
        slabs = [
            (0, 400000, 0.0, "₹0 - ₹4 LAKH: NIL"),
            (400000, 800000, 0.05, "₹4 LAKH - ₹8 LAKH: 5%"),
            (800000, 1200000, 0.10, "₹8 LAKH - ₹12 LAKH: 10%"),
            (1200000, 1600000, 0.15, "₹12 LAKH - ₹16 LAKH: 15%"),
            (1600000, 2000000, 0.20, "₹16 LAKH - ₹20 LAKH: 20%"),
            (2000000, 2400000, 0.25, "₹20 LAKH - ₹24 LAKH: 25%"),
            (2400000, None, 0.30, "ABOVE ₹24 LAKH: 30%")
        ]
        rebate_ceiling = 1200000.0
        rebate_max = 60000.0
    else:
        std_ded = 50000.0
        c80c = min(150000.0, float(decl_data.get('sec80c', 0)) + (tot_basic * 0.10))
        c80d = min(50000.0, float(decl_data.get('sec80d', 0)))
        c80e = float(decl_data.get('sec80e', 0))
        c80g = float(decl_data.get('sec80g', 0))
        c80tta = min(10000.0, float(decl_data.get('sec80tta', 0)))
        chapter_vi_a = c80c + c80d + c80e + c80g + c80tta
        
        taxable_income = round(max(0.0, gross_total_income - std_ded - chapter_vi_a), -1)
        slabs = [
            (0, 250000, 0.0, "₹0 - ₹2.5 LAKH: NIL"),
            (250000, 500000, 0.05, "₹2.5 LAKH - ₹5 LAKH: 5%"),
            (500000, 1000000, 0.20, "₹5 LAKH - ₹10 LAKH: 20%"),
            (1000000, None, 0.30, "ABOVE ₹10 LAKH: 30%")
        ]
        rebate_ceiling = 500000.0
        rebate_max = 12500.0
        
    slab_details, slab_tax = [], 0.0
    for s_from, s_to, rate, label in slabs:
        amt = 0.0
        if taxable_income > s_from:
            upper = taxable_income if s_to is None else min(taxable_income, s_to)
            amt = (upper - s_from) * rate
            slab_tax += amt
        slab_details.append({"label": label, "amount": amt})
        
    rebate_87a = min(slab_tax, rebate_max) if taxable_income <= rebate_ceiling else 0.0
    tax_after_rebate = max(0.0, slab_tax - rebate_87a)
    cess = round(tax_after_rebate * 0.04)
    total_tax_liability = max(0.0, tax_after_rebate + cess - relief_89)
    net_balance = total_tax_liability - tot_tds_paid
    
    tax_summary = {
        'regime': regime, 'gross': annual_gross_salary, 'gross_total_income': gross_total_income,
        'std_ded': std_ded, 'chapter_vi_a': chapter_vi_a, 'taxable_income': taxable_income,
        'slab_details': slab_details, 'slab_tax': slab_tax, 'rebate_87a': rebate_87a,
        'cess': cess, 'relief_89': relief_89, 'total_tax': total_tax_liability,
        'tds_paid': tot_tds_paid, 'net_balance': net_balance,
        'tot_arrear_da': tot_da_arrear, 'tot_arrear_pay': tot_pay_arrear,
        'ptax': tot_ptax
    }
    
    totals = {
        'basic': tot_basic, 'da': tot_da, 'hra': tot_hra, 'medical': tot_med,
        'arrear': tot_da_arrear + tot_pay_arrear, 'gross': annual_gross_salary,
        'gpf': tot_gpf, 'nps': tot_nps, 'gis': tot_gis, 'ptax': tot_ptax,
        'tds': tot_tds_paid, 'net': tot_net, 'q1_3_tds': tot_tds_paid * 0.75
    }
    return totals, tax_summary

# ================= FULL 4-PAGE PDF BUNDLE TEMPLATE =================
HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&family=Roboto:wght@400;500;700&display=swap');
  @page { size: A4 portrait; margin: 6mm 8mm; }
  @page landscape-section { size: A4 landscape; margin: 6mm 8mm; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; text-transform: uppercase; }
  body { font-family: 'Noto Sans Devanagari', 'Roboto', sans-serif; font-size: 9px; color: #000; line-height: 1.2; margin: 0; padding: 0; }
  .page-portrait { page-break-after: always; page-break-inside: avoid; position: relative; width: 100%; }
  .page-landscape { page: landscape-section; page-break-after: always; page-break-inside: avoid; position: relative; width: 100%; }
  .center { text-align: center; } .right { text-align: right; } .bold { font-weight: 700; }
  .title-main { font-size: 11px; font-weight: 700; } .title-sub { font-size: 12.5px; font-weight: 700; margin: 2px 0; }
  table { width: 100%; border-collapse: collapse; margin-top: 3px; margin-bottom: 3px; }
  table.border, table.border th, table.border td { border: 0.8px solid #000; }
  th, td { padding: 2.5px 4px; vertical-align: middle; }
  .no-border td { border: none !important; padding: 1.5px 3px; }
  .bg-gray { background-color: #f2f2f2 !important; }
  .sign-area { margin-top: 15px; width: 100%; }
  .pdf-footer-credit { position: absolute; bottom: 2mm; left: 0; width: 100%; text-align: center; font-size: 8px; color: #555; border-top: 0.5px solid #ccc; padding-top: 2px; }
</style>
</head>
<body>
<!-- PAGE 1: FORM 16 PART A -->
<div class="page-portrait">
  <div class="center title-sub">T.D.S. FORM NO. 16 PART A</div>
  <table class="border">
    <tr>
      <td><b>Employer:</b> {{ ddo.department }}, {{ ddo.district }} (TAN: {{ ddo.tan }})</td>
      <td><b>Employee:</b> <b>{{ emp.name }}</b> (PAN: {{ emp.pan }})</td>
    </tr>
  </table>
  {% if is_trial %}<div class="center bold" style="color:red; margin-top:30px; font-size:16px;">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
</div>

<!-- PAGE 2: FORM 16 PART B -->
<div class="page-portrait">
  <div class="center title-sub">PART B (ANNEXURE) - TAX COMPUTATION</div>
  <table class="border">
    <tr class="bg-gray bold"><td>1. Gross Salary</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>2. Standard Deduction u/s 16(ia)</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr class="bold"><td>3. Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr class="bold bg-gray"><td>4. Total Tax Liability</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>5. Total TDS Paid</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>6. Balance Payable / Refund</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
</div>

<!-- PAGE 3: SCHEDULE OF INCOME TAX -->
<div class="page-portrait">
  <div class="center title-sub">SCHEDULE OF INCOME - TAX ({{ emp.ay }})</div>
  <table class="border">
    <tr class="bg-gray bold"><th>Description</th><th class="right">Amount (Rs.)</th></tr>
    <tr><td>Gross Salary Income</td><td class="right">{{ "%.2f"|format(totals.gross) }}</td></tr>
    <tr><td>Standard Deduction</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr class="bold"><td>Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr class="bold bg-gray"><td>Net Tax Payable</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
</div>

<!-- PAGE 4: MONTHLY SALARY & TRANSACTION LEDGER -->
<div class="page-landscape">
  <div class="center title-sub">MONTHLY SALARY & TRANSACTION LEDGER</div>
  <table class="border" style="font-size: 9px;">
    <tr class="bg-gray bold center">
      <th>Type / Period</th><th>Bill No</th><th>Basic</th><th>DA</th><th>HRA</th><th>Med</th><th>Arrears</th><th>Gross</th><th>GPF/NPS</th><th>GIS</th><th>PTax</th><th>TDS</th><th>Net</th>
    </tr>
    {% for r in records %}
    <tr>
      <td><b>{{ r.payment_month }}</b> <span style="font-size: 7px; color: #555;">({{ r.transaction_type }})</span></td>
      <td>{{ r.bill_number or '-' }}</td>
      <td class="right">{{ "%.0f"|format(r.basic) }}</td>
      <td class="right">{{ "%.0f"|format(r.da) }}</td>
      <td class="right">{{ "%.0f"|format(r.hra) }}</td>
      <td class="right">{{ "%.0f"|format(r.medical) }}</td>
      <td class="right">{{ "%.0f"|format(r.get('da_arrear', 0) + r.get('pay_arrear', 0)) }}</td>
      <td class="right bold">{{ "%.0f"|format(r.gross) }}</td>
      <td class="right">{{ "%.0f"|format(r.get('gpf', 0) + r.get('nps', 0)) }}</td>
      <td class="right">{{ "%.0f"|format(r.get('gis', 0)) }}</td>
      <td class="right">{{ "%.0f"|format(r.get('professional_tax', 200)) }}</td>
      <td class="right">{{ "%.0f"|format(r.get('tds', 0)) }}</td>
      <td class="right bold">{{ "%.0f"|format(r.get('net', 0)) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold bg-gray">
      <td colspan="2">TOTAL</td>
      <td class="right">{{ "%.0f"|format(totals.basic) }}</td>
      <td class="right">{{ "%.0f"|format(totals.da) }}</td>
      <td class="right">{{ "%.0f"|format(totals.hra) }}</td>
      <td class="right">{{ "%.0f"|format(totals.medical) }}</td>
      <td class="right">{{ "%.0f"|format(totals.arrear) }}</td>
      <td class="right">{{ "%.0f"|format(totals.gross) }}</td>
      <td class="right">{{ "%.0f"|format(totals.gpf + totals.nps) }}</td>
      <td class="right">{{ "%.0f"|format(totals.gis) }}</td>
      <td class="right">{{ "%.0f"|format(totals.ptax) }}</td>
      <td class="right">{{ "%.0f"|format(totals.tds) }}</td>
      <td class="right">{{ "%.0f"|format(totals.net) }}</td>
    </tr>
  </table>
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
</div>
</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, transactions, tax_summary, totals, deposits=None, decl_dict=None, is_trial=False):
    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=transactions, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=decl_dict or {}, 
        today_date=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

# ================= MAIN APPLICATION SUITE & ADMIN COMMAND CENTER =================
def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    st.markdown("#### 📊 Spreadsheet-Style Salary & Transaction Register")
    st.info("Yahan aap regular salary aur multiple arrears ko independently rows mein add, edit ya delete kar sakte hain.")

    pan_in = st.text_input("Permanent Account Number (PAN) *", placeholder="ABCDE1234F", key=f"{prefix}_pan").upper().strip()
    
    if pan_in and len(pan_in) == 10:
        conn = sqlite3.connect(DB_NAME)
        y_rec = conn.cursor().execute("SELECT id, office_name FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()
        conn.close()
        
        if not y_rec:
            if st.button("Initialize New Employee Yearly Ledger"):
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute("INSERT OR IGNORE INTO employee_yearly_records (ay, pan, name, designation, office_name) VALUES (?, ?, ?, ?, ?)",
                                      (GLOBAL_AY, pan_in, "NEW EMPLOYEE", "TEACHER", "DEFAULT SCHOOL"))
                conn.commit()
                conn.close()
                st.rerun()
        else:
            y_id, office_name = y_rec
            st.success(f"Loaded Yearly Record ID: {y_id} | Office: {office_name}")
            
            conn = sqlite3.connect(DB_NAME)
            tx_rows = conn.cursor().execute("SELECT * FROM salary_transactions WHERE yearly_record_id=?", (y_id,)).fetchall()
            conn.close()
            
            col_names = [desc[0] for desc in sqlite3.connect(DB_NAME).cursor().execute("SELECT * FROM salary_transactions").description]
            tx_data = [dict(zip(col_names, row)) for row in tx_rows]
            
            df_tx = pd.DataFrame(tx_data) if tx_data else pd.DataFrame(columns=['id', 'transaction_type', 'payment_month', 'bill_number', 'basic', 'da', 'hra', 'medical', 'da_arrear', 'pay_arrear', 'gross', 'gpf', 'professional_tax', 'tds', 'net'])
            
            st.markdown("##### ✏️ Interactive Transaction Register (Editable Table)")
            edited_df = st.data_editor(
                df_tx,
                num_rows="dynamic",
                key=f"{prefix}_editor",
                use_container_width=True
            )
            
            if st.button("💾 Save Ledger Transactions & Validate"):
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute("DELETE FROM salary_transactions WHERE yearly_record_id=?", (y_id,))
                
                updated_tx_list = []
                for index, row in edited_df.iterrows():
                    b = float(row.get('basic', 0) or 0)
                    d = float(row.get('da', 0) or 0)
                    h = float(row.get('hra', 0) or 0)
                    med = float(row.get('medical', 0) or 0)
                    ada = float(row.get('da_arrear', 0) or 0)
                    apa = float(row.get('pay_arrear', 0) or 0)
                    g = b + d + h + med + ada + apa
                    gp = float(row.get('gpf', 0) or 0)
                    pt = float(row.get('professional_tax', 200) or 200)
                    tds = float(row.get('tds', 0) or 0)
                    net = g - (gp + pt + tds)
                    
                    conn.cursor().execute('''INSERT INTO salary_transactions (
                        yearly_record_id, financial_year, transaction_type, payment_month, bill_number,
                        basic, da, hra, medical, da_arrear, pay_arrear, gross, gpf, professional_tax, tds, net, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (y_id, GLOBAL_AY, row.get('transaction_type', 'REGULAR'), row.get('payment_month', 'MARCH'), row.get('bill_number', ''),
                     b, d, h, med, ada, apa, g, gp, pt, tds, net, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    
                    updated_tx_list.append(dict(row))
                    
                conn.commit()
                conn.close()
                
                errors, warnings = run_transaction_validation_engine(updated_tx_list)
                if errors:
                    st.error("❌ DATA VALIDATION FAILED:")
                    for err in errors:
                        st.markdown(f"- {err}")
                else:
                    st.success("✅ Validation Passed Successfully!")
                    if warnings:
                        for warn in warnings:
                            st.warning(warn)
                            
                    totals, tax_summary = compute_master_ledger_and_tax(updated_tx_list, regime="NEW REGIME")
                    
                    conn = sqlite3.connect(DB_NAME)
                    ddo_r = conn.cursor().execute("SELECT * FROM ddo_masters LIMIT 1").fetchone()
                    conn.close()
                    
                    ddo_d = {'department': ddo_r[3] if ddo_r else 'DEPT', 'district': ddo_r[2] if ddo_r else 'DIST', 'state': ddo_r[1] if ddo_r else 'STATE', 'tan': ddo_r[6] if ddo_r else 'TAN', 'officer_name': ddo_r[4] if ddo_r else 'OFFICER'}
                    emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': 'TEST EMPLOYEE', 'designation': 'CLERK', 'office_name': office_name, 'gpf_no': 'GPF123'}
                    
                    pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, updated_tx_list, tax_summary, totals, is_trial=True)
                    st.download_button("📥 Download Official Audit-Ready PDF Bundle", pdf_bytes, f"AUDIT_FORM16_{pan_in}.pdf", "application/pdf")

# ================= TOP BAR & ROUTING =================
query_params = st.query_params
is_admin_url = query_params.get("admin", "").lower() == "true"

col_ay1, col_ay2 = st.columns([3, 1])
with col_ay1: st.markdown("## 🏛️ Kosh-Tax | Enterprise Audit & Transaction Portal")
with col_ay2: GLOBAL_AY = st.selectbox("Active Assessment Year", AY_OPTIONS, index=0)

if is_admin_url:
    tab_emp, tab_redownload, tab_admin = st.tabs([
        "👤 Spreadsheet Salary Register",
        "🔍 Re-Download Archive",
        "🔒 Admin Command Center"
    ])
else:
    tab_emp, tab_redownload = st.tabs([
        "👤 Spreadsheet Salary Register",
        "🔍 Re-Download Archive"
    ])
    tab_admin = None

with tab_emp:
    render_full_employee_suite(is_admin_mode=is_admin_url, prefix="main_app")

with tab_redownload:
    st.markdown("### 🔍 Re-Download Official Form 16 & Tax Schedule")
    rd_pan = st.text_input("Enter PAN Number", key="rd_pan_field").upper().strip()
    if st.button("Search Archive") and rd_pan:
        conn = sqlite3.connect(DB_NAME)
        y_rec = conn.cursor().execute("SELECT * FROM employee_yearly_records WHERE pan=?", (rd_pan,)).fetchone()
        conn.close()
        if y_rec:
            st.success(f"Record found for: {y_rec[4]} | Office: {y_rec[6]}")
        else:
            st.error("No record found for this PAN.")

if tab_admin and is_admin_url:
    with tab_admin:
        adm_sub_tab1, adm_sub_tab2, adm_sub_tab3, adm_sub_tab4, adm_sub_tab5 = st.tabs([
            "📊 Revenue & Analytics",
            "🗃️ Master DB Manager",
            "📥 Payment Queue",
            "🏦 Statutory TDS Deposits",
            "🏛️ DDO Master"
        ])
        with adm_sub_tab1:
            st.subheader("Financial Collection Analytics")
            st.metric("Total System Revenue", "₹0")
        with adm_sub_tab2:
            st.subheader("Master Database Manager")
            st.write("Manage active employee yearly records.")
        with adm_sub_tab3:
            st.subheader("Live Payment Queue")
            st.write("Approve or reject pending digital/cash submissions.")
        with adm_sub_tab4:
            st.subheader("Statutory TDS Deposits")
            st.write("Tag challans and BSR/BIN numbers.")
        with adm_sub_tab5:
            st.subheader("DDO & Institution Master")
            st.write("Manage DDO units and TAN numbers.")

# ================= WEB FOOTER (BRANDING) =================
st.markdown("""
<div style="margin-top: 50px; text-align: center; color: #888; font-size: 11px; border-top: 1px solid #333; padding-top: 15px;">
  🏛️ <b>KOSH-TAX</b> | COMPREHENSIVE TDS & FORM 16 MANAGEMENT PORTAL<br>
  <span style="color: #aaa;">DESIGNED & DEVELOPED BY NITIN</span>
</div>
""", unsafe_allow_html=True)

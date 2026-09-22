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

# ================= PAGE CONFIGURATION =================
st.set_page_config(
    page_title="Kosh-Tax | TDS & Form 16 Enterprise Management Portal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "tds_enterprise_master.sqlite"

# Complete 7th CPC Pay Matrix with Corresponding Grade Pay
CPC_7TH_MATRIX = {
    "Level 1 (GP 1800)": [18000, 18500, 19100, 19700, 20300, 20900, 21500, 22100, 22800, 23500, 24200, 24900, 25600, 26400, 27200],
    "Level 2 (GP 1900)": [19900, 20500, 21100, 21700, 22400, 23100, 23800, 24500, 25200, 26000, 26800, 27600, 28400, 29300, 30200],
    "Level 3 (GP 2000)": [21700, 22400, 23100, 23800, 24500, 25200, 26000, 26800, 27600, 28400, 29300, 30200, 31100, 32000, 33000],
    "Level 4 (GP 2400)": [25500, 26300, 27100, 27900, 28700, 29600, 30500, 31400, 32300, 33300, 34300, 35300, 36400, 37500, 38600],
    "Level 5 (GP 2800)": [29200, 30100, 31000, 31900, 32900, 33900, 34900, 35900, 37000, 38100, 39200, 40400, 41600, 42800, 44100],
    "Level 6 (GP 4200)": [35400, 36500, 37600, 38700, 39900, 41100, 42300, 43600, 44900, 46200, 47600, 49000, 50500, 52000, 53600],
    "Level 7 (GP 4600)": [44900, 46200, 47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000],
    "Level 8 (GP 4800)": [47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200, 64100, 66000, 68000, 70000, 72100],
    "Level 9 (GP 5400)": [53100, 54700, 56300, 58000, 59700, 61500, 63300, 65200, 67200, 69200, 71300, 73400, 75600, 77900, 80200],
    "Level 10 (GP 5400)": [56100, 57800, 59500, 61300, 63100, 65000, 67000, 69000, 71100, 73200, 75400, 77700, 80000, 82400, 84900],
    "Level 11 (GP 6600)": [67700, 69700, 71800, 74000, 76200, 78500, 80900, 83300, 85800, 88400, 91100, 93800, 96600, 99500, 102500],
    "Level 12 (GP 7600)": [78800, 81200, 83600, 86100, 88700, 91400, 94100, 96900, 99800, 102800, 105900, 109100, 112400, 115800, 119300]
}

# ALL 24 JHARKHAND DISTRICTS & MAJOR BLOCKS MAPPING
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

JHARKHAND_MONTHS = [
    "March 2024", "April 2024", "May 2024", "June 2024", 
    "July 2024", "August 2024", "September 2024", "October 2024", 
    "November 2024", "December 2024", "January 2025", "February 2025"
]

AY_OPTIONS = ["AY 2025-26 (FY 2024-25)", "AY 2026-27 (FY 2025-26)"]

# ================= DATABASE INITIALIZATION =================
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
        pension_type TEXT DEFAULT 'GPF',
        tax_regime TEXT DEFAULT 'New Regime',
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

    c.execute('''CREATE TABLE IF NOT EXISTS monthly_salary_ledgers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        yearly_record_id INTEGER,
        month_name TEXT,
        basic_pay REAL DEFAULT 0,
        da REAL DEFAULT 0,
        hra REAL DEFAULT 0,
        medical REAL DEFAULT 0,
        arrear_da REAL DEFAULT 0,
        arrear_pay REAL DEFAULT 0,
        gross REAL DEFAULT 0,
        gpf REAL DEFAULT 0,
        gis REAL DEFAULT 60,
        ptax REAL DEFAULT 200,
        tds REAL DEFAULT 0,
        net REAL DEFAULT 0,
        source TEXT DEFAULT 'Manual',
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
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('admin_username', '__nit@def@admin26__')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('admin_password', '19052027def@admin')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('form_fee', '100')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('upi_id', 'nitinmallick111-1@okicici')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('whitelisted_pans', '')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('smtp_email', '')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('smtp_password', '')")

    c.execute("UPDATE app_settings SET value='nitinmallick111-1@okicici' WHERE key='upi_id'")

    c.execute("INSERT OR IGNORE INTO master_states (name) VALUES ('JHARKHAND'), ('BIHAR'), ('WEST BENGAL'), ('CENTRAL GOVT / OTHER')")
    for d in JHARKHAND_BLOCK_DISTRICT_MAP.keys():
        c.execute("INSERT OR IGNORE INTO master_districts (state_name, name) VALUES ('JHARKHAND', ?)", (d,))

    conn.commit()
    conn.close()

init_db()

# ================= HELPER & REPOSITORY UTILITIES =================
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
    return [r[0] for r in rows if r[0]]

def add_creatable_item(table, col_data):
    conn = sqlite3.connect(DB_NAME)
    cols = ", ".join(col_data.keys())
    placeholders = ", ".join(["?"] * len(col_data))
    try:
        conn.cursor().execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})", tuple(col_data.values()))
        conn.commit()
    except Exception:
        pass
    conn.close()

def match_district_from_text(raw_text):
    text_upper = raw_text.upper()
    for dist, blocks in JHARKHAND_BLOCK_DISTRICT_MAP.items():
        if dist in text_upper:
            return dist
        for blk in blocks:
            if re.search(r'\b' + re.escape(blk) + r'\b', text_upper):
                return dist
    return "KHUNTI"

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
    best_lvl = "Level 7 (GP 4600)"
    min_diff = 999999
    for lvl, cells in CPC_7TH_MATRIX.items():
        for c in cells:
            diff = abs(c - b_val)
            if diff < min_diff:
                min_diff = diff
                best_lvl = lvl
    return best_lvl

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
        'designation': 'Assistant Teacher',
        'gpf_no': '',
        'ddo_code': '',
        'office_name': '',
        'basic': 55200.0,
        'da': 27600.0,
        'hra': 4968.0,
        'medical': 1000.0,
        'gpf': 5000.0,
        'gis': 60.0,
        'ptax': 200.0,
        'tds': 3000.0,
        'inc_month': '1st JULY',
        'inc_basic': 56900.0,
        'pay_level': 'Level 7 (GP 4600)',
        'matching_levels': [],
        'auto_district': 'KHUNTI',
        'auto_state': 'JHARKHAND',
        'pension_type': 'Old Pension (GPF / OPS)',
        'arrear_da': 0.0,
        'arrear_pay': 0.0,
        'arrear_tds': 0.0
    }
    try:
        reader = PdfReader(uploaded_file)
        pages_text = [p.extract_text() or "" for p in reader.pages]
        full_text = "\n".join(pages_text)
        raw_clean = re.sub(r'[ \t]+', ' ', full_text)

        # Smart Categorization (Jharkhand OPS vs Central NPS vs Private EPF)
        if re.search(r'Govt\.\s*of\s*Jharkhand|Government\s*of\s*Jharkhand', raw_clean, re.I):
            extracted['auto_state'] = 'JHARKHAND'
            extracted['pension_type'] = 'Old Pension (GPF / OPS)'
        elif re.search(r'Govt\.\s*of\s*India|Government\s*of\s*India|Central\s*Govt|Kendriya|Railway|Defence|Postal', raw_clean, re.I):
            extracted['auto_state'] = 'CENTRAL GOVT / OTHER'
            extracted['pension_type'] = 'NPS (10% Basic+DA)'
        elif re.search(r'Pvt\s*Ltd|Limited|Private\s*Limited|Infotech|Services|Technologies', raw_clean, re.I):
            extracted['auto_state'] = 'CENTRAL GOVT / OTHER'
            extracted['pension_type'] = 'NPS (10% Basic+DA)'

        extracted['auto_district'] = match_district_from_text(raw_clean)

        pan_m = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', raw_clean)
        if pan_m: extracted['pan'] = pan_m.group(1).strip()

        name_m = re.search(r'Employee\s*Name\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\s*PAN|\s*DDO|\s*Designation|\n|$)', raw_clean, re.I)
        if name_m:
            c = name_m.group(1).strip()
            if len(c) > 2 and not any(ch.isdigit() for ch in c): extracted['name'] = c

        des_m = re.search(r'Designation\s*[:\-]?\s*([A-Za-z0-9\s\.\+\/\-]+?)(?=\s*Pay\s*Scale|\s*TV|\s*Allowances|\n|$)', raw_clean, re.I)
        if des_m: extracted['designation'] = des_m.group(1).strip()

        gpf_m = re.search(r'Employee\s*GPF\s*No\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', raw_clean, re.I)
        if gpf_m: extracted['gpf_no'] = gpf_m.group(1).strip()

        ddo_m = re.search(r'DDO\s*CODE\s*[:\-]?\s*([A-Z0-9]+)', raw_clean, re.I)
        if ddo_m: extracted['ddo_code'] = ddo_m.group(1).strip()

        monthly_basics = {}
        for p_txt in pages_text:
            is_arrear = bool(re.search(r'arrear|jul\s*2022|aug-sep\s*2024', p_txt, re.I))
            b_val = get_clean_num(p_txt, ["Basic", "मूल वेतन"])
            da_val = get_clean_num(p_txt, ["DA", "Dearness Allowance"])
            tds_val = get_clean_num(p_txt, ["I.TAX", "ITAX", "1.TAX", "TDS"])

            if is_arrear:
                if "jul-dec 2024 arrear" in p_txt.lower():
                    extracted['arrear_da'] += da_val if da_val > 0 else get_clean_num(p_txt, ["Total"])
                else:
                    tot_p = get_clean_num(p_txt, ["Total"])
                    extracted['arrear_pay'] += tot_p
                if tds_val > 0:
                    extracted['arrear_tds'] += tds_val
            else:
                m_m = re.search(r'Salary\s*Slip\s*[-–]?\s*([A-Za-z]{3,9})\s*(\d{4})', p_txt, re.I)
                if m_m and b_val > 0:
                    m_str = m_m.group(1).lower()[:3]
                    monthly_basics[m_str] = b_val

        mar_b = monthly_basics.get("mar", 0.0) or monthly_basics.get("apr", 0.0) or 55200.0
        jul_b = monthly_basics.get("jul", 0.0) or monthly_basics.get("aug", 0.0)
        jan_b = monthly_basics.get("jan", 0.0)

        extracted['basic'] = mar_b
        
        # 7th CPC Matrix Dynamic Auto Fixation
        matching = get_matching_levels(extracted['basic'])
        extracted['matching_levels'] = matching
        determined_level = matching[0] if matching else find_nearest_level_by_amount(mar_b)
        extracted['pay_level'] = determined_level

        if jul_b and jul_b > mar_b:
            extracted['inc_month'] = '1st JULY'
            extracted['inc_basic'] = jul_b
        elif jan_b and jan_b > mar_b:
            extracted['inc_month'] = '1st JANUARY'
            extracted['inc_basic'] = jan_b
        else:
            extracted['inc_month'] = '1st JULY'
            extracted['inc_basic'] = get_next_matrix_cell(determined_level, mar_b)

        r_da = get_clean_num(raw_clean, ["DA", "Dearness Allowance"])
        if r_da > 0: extracted['da'] = r_da
        r_hra = get_clean_num(raw_clean, ["HRA", "House Rent Allowance"])
        if r_hra > 0: extracted['hra'] = r_hra
        r_med = get_clean_num(raw_clean, ["Medical Allow.", "Medical Allowance"])
        if r_med > 0: extracted['medical'] = r_med
        r_gpf = get_clean_num(raw_clean, ["GPF", "NPS", "PRAN", "EPF"])
        if r_gpf > 0: extracted['gpf'] = r_gpf
        r_tds = get_clean_num(raw_clean, ["I.TAX", "ITAX", "1.TAX", "TDS"])
        if r_tds > 0: extracted['tds'] = r_tds

    except Exception:
        pass

    return extracted

# ================= DUAL TAX ENGINE (OLD/NEW REGIME) WITH BALANCING =================
def compute_annual_tax_with_regime(records_11, regime="New Regime", decl_data=None, manual_arrear_da=0.0, manual_arrear_pay=0.0, extra_tds=0.0):
    if decl_data is None:
        decl_data = {}
    
    jan_row = records_11[-1]
    feb_basic, feb_da, feb_hra, feb_med = jan_row['basic'], jan_row['da'], jan_row['hra'], jan_row['medical']
    feb_gpf, feb_gis, feb_ptax = jan_row['gpf'], jan_row['gis'], jan_row['ptax']
    feb_gross = feb_basic + feb_da + feb_hra + feb_med
    
    tot_basic = sum(r['basic'] for r in records_11) + feb_basic
    tot_da = sum(r['da'] for r in records_11) + feb_da
    tot_hra = sum(r['hra'] for r in records_11) + feb_hra
    tot_med = sum(r['medical'] for r in records_11) + feb_med
    tot_arrear_da = sum(r.get('arrear_da', 0) for r in records_11) + manual_arrear_da
    tot_arrear_pay = sum(r.get('arrear_pay', 0) for r in records_11) + manual_arrear_pay
    
    annual_gross_salary = tot_basic + tot_da + tot_hra + tot_med + tot_arrear_da + tot_arrear_pay
    other_emp = float(decl_data.get('other_employer_salary', 0))
    house_loss = float(decl_data.get('house_property_loss', 0))
    other_inc = float(decl_data.get('bank_interest', 0)) + float(decl_data.get('other_income', 0))
    relief_89 = float(decl_data.get('relief_89', 0))
    
    gross_total_income = annual_gross_salary + other_emp + other_inc - house_loss
    
    if regime == "New Regime":
        std_ded = 75000.0
        chapter_vi_a = 0.0
        taxable_income = round(max(0.0, gross_total_income - std_ded), -1)
        slabs = [
            (0, 400000, 0.0, "₹0 - ₹4 Lakh: Nil"),
            (400000, 800000, 0.05, "₹4 Lakh - ₹8 Lakh: 5%"),
            (800000, 1200000, 0.10, "₹8 Lakh - ₹12 Lakh: 10%"),
            (1200000, 1600000, 0.15, "₹12 Lakh - ₹16 Lakh: 15%"),
            (1600000, 2000000, 0.20, "₹16 Lakh - ₹20 Lakh: 20%"),
            (2000000, 2400000, 0.25, "₹20 Lakh - ₹24 Lakh: 25%"),
            (2400000, None, 0.30, "Above ₹24 Lakh: 30%")
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
            (0, 250000, 0.0, "₹0 - ₹2.5 Lakh: Nil"),
            (250000, 500000, 0.05, "₹2.5 Lakh - ₹5 Lakh: 5%"),
            (500000, 1000000, 0.20, "₹5 Lakh - ₹10 Lakh: 20%"),
            (1000000, None, 0.30, "Above ₹10 Lakh: 30%")
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
    
    tds_11_months = sum(r.get('tds', 0) for r in records_11) + extra_tds
    feb_tds = max(0.0, total_tax_liability - tds_11_months)
    feb_net = feb_gross - (feb_gpf + feb_gis + feb_ptax + feb_tds)
    
    feb_row = {
        'month': 'February 2025', 'basic': feb_basic, 'da': feb_da, 'hra': feb_hra,
        'medical': feb_med, 'arrear_da': 0.0, 'arrear_pay': 0.0, 'gross': feb_gross,
        'gpf': feb_gpf, 'gis': feb_gis, 'ptax': feb_ptax, 'tds': feb_tds, 'net': feb_net
    }
    
    full_12 = list(records_11) + [feb_row]
    tax_summary = {
        'regime': regime, 'gross': annual_gross_salary, 'gross_total_income': gross_total_income,
        'std_ded': std_ded, 'chapter_vi_a': chapter_vi_a, 'taxable_income': taxable_income,
        'slab_details': slab_details, 'slab_tax': slab_tax, 'rebate_87a': rebate_87a,
        'cess': cess, 'relief_89': relief_89, 'total_tax': total_tax_liability,
        'tds_paid': tds_11_months + feb_tds, 'net_balance': total_tax_liability - (tds_11_months + feb_tds),
        'feb_tds': feb_tds, 'tot_arrear_da': tot_arrear_da, 'tot_arrear_pay': tot_arrear_pay
    }
    return full_12, tax_summary

def send_email_with_pdf(recipient_email, subject, body, pdf_bytes, filename):
    smtp_user = get_setting('smtp_email', '')
    smtp_pass = get_setting('smtp_password', '')
    if not (smtp_user and smtp_pass and recipient_email):
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipient_email, msg.as_string())
        server.quit()
        return True
    except Exception:
        return False

# ================= DUAL ORIENTATION (PORTRAIT & LANDSCAPE) ZERO-TRUNCATION TEMPLATE =================
HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600;700&family=Roboto:wght@400;500;700&display=swap');
  
  /* Standard Form 16 Portrait */
  @page {
    size: A4 portrait;
    margin: 6mm 8mm 6mm 8mm;
  }
  
  /* Landscape orientation for Schedule & Monthly Ledger */
  @page landscape-section {
    size: A4 landscape;
    margin: 6mm 8mm 6mm 8mm;
  }
  
  * { 
    box-sizing: border-box; 
    -webkit-print-color-adjust: exact; 
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
  
  .page-landscape:last-child {
    page-break-after: auto;
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
    Certificate under Section 203 of the Income-tax Act, 1961 for tax deduction at source from income chargeable under the head "SALARIES"
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
      <td class="right">{{ "%.2f"|format(totals.q1_3_tds / 3) }}</td><td class="right">{{ "%.2f"|format(totals.q1_3_tds / 3) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 2</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(totals.q1_3_tds / 3) }}</td><td class="right">{{ "%.2f"|format(totals.q1_3_tds / 3) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 3</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(totals.q1_3_tds / 3) }}</td><td class="right">{{ "%.2f"|format(totals.q1_3_tds / 3) }}</td>
    </tr>
    <tr class="center">
      <td>Quarter 4</td><td>Consolidated Treasury Adjustment</td><td class="right">--</td>
      <td class="right">{{ "%.2f"|format(tax.feb_tds) }}</td><td class="right">{{ "%.2f"|format(tax.feb_tds) }}</td>
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
        <td class="right">{{ "%.2f"|format(d[4]) }}</td>
        <td>{{ d[7] or d[9] or 'Book-Adj' }}</td>
        <td>{{ d[8] or d[11] or 'Treasury' }}</td>
        <td>{{ d[5] }}</td>
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
    I, <b>{{ ddo.officer_name }}</b>, son/daughter of <b>{{ ddo.father_name }}</b>, working in the capacity of <b>Drawing & Disbursing Officer (DDO)</b> do hereby certify that a sum of Rs. <b>{{ "%.2f"|format(tax.tds_paid) }}</b> has been deducted and deposited to the credit of the Central Government. I further certify that the information given above is true, complete and correct based on the books of account, documents, TDS statements and other available records.
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
</div>

<!-- SECTION 2: FORM 16 PART B (PORTRAIT - FULL STATUTORY EXPANSION) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}

  <div class="center title-sub">PART B (Annexure)</div>
  <div class="center bold" style="font-size: 9px; margin-bottom: 6px;">Certificate under section 203 of the Income-tax Act, 1961</div>

  <table class="border">
    <tr class="bg-gray bold center"><th style="width: 75%; text-align: left;">Details of Salary Paid and any other income and tax deducted</th><th style="width: 25%; text-align: right;">Amount (Rs.)</th></tr>
    <tr><td>1. Gross Salary</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(a) Salary as per provisions contained in sec. 17(1)</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(b) Value of perquisites u/s 17(2)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(c) Profits in lieu of salary under section 17(3)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(d) Total</td><td class="right bold">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>2. Less: Allowance to the extent exempt u/s 10</td><td class="right">0.00</td></tr>
    <tr><td>3. Balance (1 - 2)</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>4. Deductions under section 16:</td><td class="right"></td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(a) Standard deduction u/s 16(ia)</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(b) Entertainment allowance u/s 16(ii)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(c) Tax on employment u/s 16(iii) (Professional Tax)</td><td class="right">0.00</td></tr>
    <tr class="bold bg-gray"><td>5. Aggregate of deductions under section 16</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr class="bold"><td>6. Income chargeable under the head 'Salaries' (3 - 5)</td><td class="right">{{ "%.2f"|format(tax.gross - tax.std_ded) }}</td></tr>
    <tr><td>7. Add: Any other income reported by the employee</td><td class="right">0.00</td></tr>
    <tr class="bold bg-gray"><td>8. Gross Total Income (6 + 7)</td><td class="right">{{ "%.2f"|format(tax.gross_total_income) }}</td></tr>
    <tr><td colspan="2"><b>9. Deductions under Chapter VI-A:</b></td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(a) Section 80C (GPF, PPF, LIC, Tuition Fees, etc.)</td><td class="right">{% if decl %}{{ "%.2f"|format(decl.sec80c) }}{% else %}0.00{% endif %}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(b) Section 80CCC (Pension Fund)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(c) Section 80CCD(1) (Employee Contribution to NPS)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(d) Section 80CCD(1B) (Additional NPS Deduction)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(e) Section 80D (Health Insurance Premium)</td><td class="right">{% if decl %}{{ "%.2f"|format(decl.sec80d) }}{% else %}0.00{% endif %}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(f) Section 80E (Interest on Loan for Higher Education)</td><td class="right">{% if decl %}{{ "%.2f"|format(decl.sec80e) }}{% else %}0.00{% endif %}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(g) Section 80G (Donations to certain funds, etc.)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(h) Section 80TTA (Interest on Savings Bank Accounts)</td><td class="right">{% if decl %}{{ "%.2f"|format(decl.sec80tta) }}{% else %}0.00{% endif %}</td></tr>
    <tr class="bold bg-gray"><td>10. Aggregate of deductible amount under Chapter VI-A</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
    <tr class="bold"><td>11. Total Taxable Income (8 - 10)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>12. Tax on Total Income</td><td class="right">{{ "%.2f"|format(tax.slab_tax) }}</td></tr>
    <tr><td>13. Rebate under section 87A</td><td class="right">{{ "%.2f"|format(tax.rebate_87a) }}</td></tr>
    <tr><td>14. Tax payable after Rebate</td><td class="right">{{ "%.2f"|format(tax.total_tax - tax.cess + tax.relief_89) }}</td></tr>
    <tr><td>15. Surcharge</td><td class="right">0.00</td></tr>
    <tr><td>16. Health and Education Cess @ 4%</td><td class="right">{{ "%.2f"|format(tax.cess) }}</td></tr>
    <tr><td>17. Relief under section 89</td><td class="right">{{ "%.2f"|format(tax.relief_89) }}</td></tr>
    <tr class="bold bg-gray"><td>18. Net Tax Liability (14 + 15 + 16 - 17)</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>19. Total TDS Deducted during the year</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>20. Balance Tax Payable / (Refundable)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>

  <div class="sign-area" style="margin-top: 15px;">
    <table class="no-border">
      <tr>
        <td style="width: 50%;">Place: {{ ddo.city or ddo.district }}<br>Date: {{ today_date }}</td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          ________________________________________<br>
          Signature of person responsible for deduction of tax<br>
          Full Name: <b>{{ ddo.officer_name }}</b>
        </td>
      </tr>
    </table>
  </div>
</div>

<!-- SECTION 3: SCHEDULE OF INCOME TAX (LANDSCAPE - NATURAL SPREAD) -->
<div class="page-landscape">
  {% if is_trial %}<div class="watermark-layer-l">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}

  <div class="center title-main">{{ tax.regime }} के तहत</div>
  <div class="center title-sub">Schedule of Income - Tax</div>
  <div class="center title-main">आयकर की अनुसूची (चार प्रतियों में भर कर दें)</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 6px;">{{ emp.ay }}</div>

  <table class="no-border" style="margin-bottom: 6px;">
    <tr>
      <td style="width: 50%;">करदाता का नाम : <b>{{ emp.name }}</b> &nbsp;&nbsp;|&nbsp;&nbsp; पदनाम : {{ emp.designation }}</td>
      <td style="width: 50%; text-align: right;">कार्यालय / विद्यालय का नाम : <b>{{ emp.office_name }}</b></td>
    </tr>
    <tr>
      <td>स्थायी लेखा संख्या (PAN) : <b>{{ emp.pan }}</b></td>
      <td style="text-align: right;">GPF / PRAN / PF संख्या : <b>{{ emp.gpf_no or 'N/A' }}</b></td>
    </tr>
  </table>

  <table class="border">
    <tr class="bg-gray bold">
      <th style="width: 5%;">क</th>
      <th style="width: 75%; text-align: left;">वेतन स्रोत से आय का विवरण:</th>
      <th style="width: 20%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>वेतन (दिनांक 01.03.2024 से 28.02.2025 तक)</td><td class="right">{{ "%.2f"|format(totals.basic) }}</td></tr>
    <tr><td>02.</td><td>महँगाई भत्ता (DA)</td><td class="right">{{ "%.2f"|format(totals.da) }}</td></tr>
    <tr><td>03.</td><td>मकान किराया भत्ता (HRA)</td><td class="right">{{ "%.2f"|format(totals.hra) }}</td></tr>
    <tr><td>04.</td><td>चिकित्सा भत्ता (Medical Allowance)</td><td class="right">{{ "%.2f"|format(totals.medical) }}</td></tr>
    <tr><td>05.</td><td>महंगाई भत्ता की बकाया राशि (DA Arrear)</td><td class="right">{{ "%.2f"|format(tax.tot_arrear_da) }}</td></tr>
    <tr><td>06.</td><td>बकाया वेतन एवं भत्ते की राशि (Pay Arrear)</td><td class="right">{{ "%.2f"|format(tax.tot_arrear_pay) }}</td></tr>
    <tr class="bold bg-gray"><td>07.</td><td>वेतन स्रोत से प्राप्त कुल आय</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
  </table>

  <table class="border" style="margin-top: 6px;">
    <tr class="bg-gray bold">
      <th style="width: 5%;">ख</th>
      <th style="width: 75%; text-align: left;">आयकर की संगणना</th>
      <th style="width: 20%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>सकल वेतन एवं अन्य आय (Gross Total Income)</td><td class="right">{{ "%.2f"|format(tax.gross_total_income) }}</td></tr>
    <tr><td>02.</td><td>घटायें धारा 16 (ia) मानक कटौती (Standard Deduction)</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    {% if tax.regime == 'Old Regime' %}
    <tr><td>03.</td><td>घटायें अध्याय VI-A की कटौतियां (80C, 80D आदि)</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
    {% endif %}
    <tr class="bold"><td>04.</td><td>कर योग्य आय (Taxable Total Income)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr>
      <td>05.</td>
      <td colspan="2" style="padding: 4px 6px;">
        <b>रु० {{ "%.2f"|format(tax.taxable_income) }} पर देय आयकर (Tax Slabs Breakdown):</b><br>
        {% for s in tax.slab_details %}
        <span style="display:inline-block; width: 75%;">&nbsp;&nbsp;{{ s.label }}</span>
        <span style="display:inline-block; width: 23%; text-align: right;">{{ "%.2f"|format(s.amount) }}</span><br>
        {% endfor %}
        <div style="border-top: 0.6px dashed #000; margin-top: 3px; padding-top: 2px;">
          <b>&nbsp;&nbsp;कुल देय आयकर (Slab Tax):</b>
          <span style="float: right;"><b>{{ "%.2f"|format(tax.slab_tax) }}</b></span>
        </div>
      </td>
    </tr>
    <tr><td>06.</td><td>घटायें - धारा 87A के तहत कर में राहत (Rebate)</td><td class="right">{{ "%.2f"|format(tax.rebate_87a) }}</td></tr>
    <tr><td>07.</td><td>शुद्ध देय आयकर</td><td class="right">{{ "%.2f"|format(tax.total_tax - tax.cess + tax.relief_89) }}</td></tr>
    <tr><td>08.</td><td>जोड़ें - 4% (स्वास्थ्य एवं शिक्षा उपकर / Health & Edu Cess)</td><td class="right">{{ "%.2f"|format(tax.cess) }}</td></tr>
    <tr><td>09.</td><td>घटायें - धारा 89 के तहत राहत (Relief u/s 89)</td><td class="right">{{ "%.2f"|format(tax.relief_89) }}</td></tr>
    <tr class="bold bg-gray"><td>10.</td><td>आयकर का कुल योग (Total Tax Liability)</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>11.</td><td>घटायें - प्रतिमाह वेतन से आयकर (TDS) का भुगतान</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>12.</td><td>भुगतेय आयकर / (रिफंड) Balance Tax Payable / (Refund)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>

  <div class="sign-area" style="margin-top: 15px;">
    <div><b>कोषागार:</b> {{ ddo.district }} ({{ ddo.state }}){% if ddo.address %} | <b>पता:</b> {{ ddo.address }}{% endif %}{% if ddo.city %}, {{ ddo.city }}{% endif %}{% if ddo.pincode %} - {{ ddo.pincode }}{% endif %}</div>
    <table class="no-border" style="margin-top: 15px;">
      <tr>
        <td style="width: 50%;">
          <div class="sign-box-space"></div>
          हस्ताक्षर करदाता: ____________________
        </td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          निकासी एवं व्ययन पदाधिकारी हस्ताक्षर एवं मुहर
        </td>
      </tr>
    </table>
  </div>
</div>

<!-- SECTION 4: MONTHLY SALARY LEDGER (LANDSCAPE - WIDE ACCOUNTING GRID) -->
<div class="page-landscape">
  {% if is_trial %}<div class="watermark-layer-l">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}

  <div class="center title-sub">मासिक वेतन एवं कटौतियों की विवरणी (Monthly Salary & Deduction Ledger)</div>
  <div class="center bold" style="font-size: 9px; margin-bottom: 6px;">{{ emp.name }} (PAN: {{ emp.pan }}) | {{ emp.office_name }}</div>

  <table class="border" style="font-size: 8.5px; margin-top: 4px;">
    <tr class="bg-gray center bold">
      <th style="width: 11%;">माह</th>
      <th style="width: 9%;">मूल वेतन</th>
      <th style="width: 8%;">महंगाई</th>
      <th style="width: 8%;">HRA</th>
      <th style="width: 6%;">Med</th>
      <th style="width: 9%;">Arrear</th>
      <th style="width: 10%;">सकल (Gross)</th>
      <th style="width: 8%;">GPF/NPS</th>
      <th style="width: 6%;">GIS</th>
      <th style="width: 6%;">PTax</th>
      <th style="width: 8%;">TDS</th>
      <th style="width: 11%;">शुद्ध (Net)</th>
    </tr>
    {% for r in records %}
    <tr>
      <td>{{ r.month }}</td>
      <td class="right">{{ "%.0f"|format(r.basic) }}</td>
      <td class="right">{{ "%.0f"|format(r.da) }}</td>
      <td class="right">{{ "%.0f"|format(r.hra) }}</td>
      <td class="right">{{ "%.0f"|format(r.medical) }}</td>
      <td class="right">{{ "%.0f"|format(r.arrear_da + r.arrear_pay) }}</td>
      <td class="right bold">{{ "%.0f"|format(r.gross) }}</td>
      <td class="right">{{ "%.0f"|format(r.gpf) }}</td>
      <td class="right">{{ "%.0f"|format(r.gis) }}</td>
      <td class="right">{{ "%.0f"|format(r.ptax) }}</td>
      <td class="right">{{ "%.0f"|format(r.tds) }}</td>
      <td class="right bold">{{ "%.0f"|format(r.net) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold bg-gray">
      <td>कुल योग</td>
      <td class="right">{{ "%.0f"|format(totals.basic) }}</td>
      <td class="right">{{ "%.0f"|format(totals.da) }}</td>
      <td class="right">{{ "%.0f"|format(totals.hra) }}</td>
      <td class="right">{{ "%.0f"|format(totals.medical) }}</td>
      <td class="right">{{ "%.0f"|format(tax.tot_arrear_da + tax.tot_arrear_pay) }}</td>
      <td class="right">{{ "%.0f"|format(tax.gross) }}</td>
      <td class="right">{{ "%.0f"|format(totals.gpf) }}</td>
      <td class="right">{{ "%.0f"|format(totals.gis) }}</td>
      <td class="right">{{ "%.0f"|format(totals.ptax) }}</td>
      <td class="right">{{ "%.0f"|format(tax.tds_paid) }}</td>
      <td class="right">{{ "%.0f"|format(totals.net) }}</td>
    </tr>
  </table>

  <div class="sign-area" style="margin-top: 25px;">
    <table class="no-border">
      <tr>
        <td style="width: 50%;">
          <div class="sign-box-space"></div>
          हस्ताक्षर करदाता: ____________________
        </td>
        <td style="width: 50%; text-align: right;">
          <div class="sign-box-space"></div>
          निकासी एवं व्ययन पदाधिकारी हस्ताक्षर एवं मुहर
        </td>
      </tr>
    </table>
  </div>
</div>

</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, full_records, tax_summary, deposits=None, decl_dict=None, is_trial=False):
    totals = {
        'basic': sum(r['basic'] for r in full_records),
        'da': sum(r['da'] for r in full_records),
        'hra': sum(r['hra'] for r in full_records),
        'medical': sum(r['medical'] for r in full_records),
        'gpf': sum(r['gpf'] for r in full_records),
        'gis': sum(r['gis'] for r in full_records),
        'ptax': sum(r['ptax'] for r in full_records),
        'net': sum(r['net'] for r in full_records),
        'q1_3_tds': sum(r['tds'] for r in full_records[:11])
    }

    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=full_records, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=decl_dict, 
        today_date=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

# ================= SHARED GENERATOR SUITE =================
def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    st.markdown("#### 📄 Salary Slip Upload & Dynamic Auto-Fill")
    slip_up = st.file_uploader(
        "Upload Salary Slip (PDF) — Block to District, 7th CPC Matrix, Pension & Arrear auto-detect ho jayenge:", 
        type=["pdf"], 
        key=f"{prefix}_slip"
    )
    
    if slip_up:
        if f"{prefix}_last_uploaded" not in st.session_state or st.session_state[f"{prefix}_last_uploaded"] != slip_up.name:
            scanned = parse_slip_in_memory(slip_up)
            st.session_state[f"{prefix}_scanned"] = scanned
            st.session_state[f"{prefix}_last_uploaded"] = slip_up.name

            if scanned.get('pan'):
                st.session_state[f"{prefix}_pan_field"] = scanned['pan']
            if scanned.get('name'):
                st.session_state[f"{prefix}_vn"] = scanned['name']
            if scanned.get('designation'):
                st.session_state[f"{prefix}_vd"] = scanned['designation']
            if scanned.get('gpf_no'):
                st.session_state[f"{prefix}_vgpf_no"] = scanned['gpf_no']
            if scanned.get('pay_level'):
                st.session_state[f"{prefix}_lvl"] = scanned['pay_level']
            if scanned.get('basic', 0) > 0:
                st.session_state[f"{prefix}_bsc"] = int(scanned['basic'])
            if scanned.get('inc_month'):
                st.session_state[f"{prefix}_incm"] = scanned['inc_month']
            if scanned.get('inc_basic', 0) > 0:
                st.session_state[f"{prefix}_incb"] = int(scanned['inc_basic'])
            if scanned.get('da', 0) > 0:
                st.session_state[f"{prefix}_vda"] = int(scanned['da'])
            if scanned.get('hra', 0) > 0:
                st.session_state[f"{prefix}_vhra"] = int(scanned['hra'])
            if scanned.get('gpf', 0) > 0:
                st.session_state[f"{prefix}_vgpf"] = int(scanned['gpf'])
            if scanned.get('tds', 0) > 0:
                st.session_state[f"{prefix}_vtds"] = int(scanned['tds'])
            
            # Smart Categorization & Location
            st.session_state[f"{prefix}_st"] = scanned.get('auto_state', 'JHARKHAND')
            st.session_state[f"{prefix}_dt"] = scanned.get('auto_district', 'KHUNTI')
            st.session_state[f"{prefix}_pen"] = scanned.get('pension_type', 'Old Pension (GPF / OPS)')

            st.session_state[f"{prefix}_arrear_da"] = float(scanned.get('arrear_da', 0))
            st.session_state[f"{prefix}_arrear_pay"] = float(scanned.get('arrear_pay', 0))
            st.session_state[f"{prefix}_arrear_tds"] = float(scanned.get('arrear_tds', 0))

            st.rerun()

    scanned = st.session_state.get(f"{prefix}_scanned", None)

    if scanned and scanned.get('pan'):
        with st.expander("📋 Extracted Slip Data Summary & 7th CPC Matrix Inspection", expanded=True):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Employee Name", scanned.get('name') or "N/A")
            r2.metric("PAN Number", scanned.get('pan') or "N/A")
            r3.metric("Auto District (via Block)", scanned.get('auto_district') or "KHUNTI")
            r4.metric("Increment Month", scanned.get('inc_month') or "1st JULY")

            r5, r6, r7, r8 = st.columns(4)
            r5.metric("March Basic Pay", f"₹{scanned.get('basic', 0):,.0f}")
            r6.metric("Auto Pay Level & GP", scanned.get('pay_level') or "Level 7 (GP 4600)")
            r7.metric("DA Arrear Total", f"₹{scanned.get('arrear_da', 0):,.0f}")
            r8.metric("Pay Arrear Total", f"₹{scanned.get('arrear_pay', 0):,.0f}")

            matching = scanned.get('matching_levels', [])
            if len(matching) > 1:
                st.warning(f"⚠️ Multiple 7th CPC Levels Overlap for Basic ₹{scanned.get('basic', 0):,.0f}: {', '.join(matching)}. System has chosen '{scanned.get('pay_level')}'. Please verify below if required.")

    c_p1, c_p2 = st.columns([2, 1])
    with c_p1:
        pan_in = st.text_input(
            "Permanent Account Number (PAN) *", 
            placeholder="ABCDE1234F", 
            key=f"{prefix}_pan_field"
        ).upper().strip()
    
    prof = None
    if pan_in and len(pan_in) == 10:
        conn = sqlite3.connect(DB_NAME)
        prof = conn.cursor().execute("SELECT * FROM employee_master_profiles WHERE pan=?", (pan_in,)).fetchone()
        conn.close()
        with c_p2:
            if prof: st.success("✅ Profile Found! History Rolled-Forward.")
            else: st.info("🆕 Fresh Registration.")

    c_s1, c_s2 = st.columns(2)
    with c_s1:
        status_sel = st.selectbox(
            "Service Condition:",
            ["NORMAL (Regular Continuity)", "TRANSFER (New School / Office)", "PROMOTION / MACP (New Level)", "SUSPENSION / LWP"],
            key=f"{prefix}_status_sel"
        )
    with c_s2:
        regime_sel = st.selectbox(
            "Tax Assessment Regime:",
            ["New Regime", "Old Regime"],
            key=f"{prefix}_regime_sel"
        )

    # State, District, Department Hierarchy
    c_l1, c_l2, c_l3 = st.columns(3)
    states_list = get_creatable_list("master_states", "name")
    def_st_idx = states_list.index(prof[6]) if prof and prof[6] in states_list else (states_list.index("JHARKHAND") if "JHARKHAND" in states_list else 0)
    with c_l1:
        s_st = st.selectbox("State", states_list + ["➕ Add New State"], index=def_st_idx, key=f"{prefix}_st")
        if s_st == "➕ Add New State":
            new_st = st.text_input("Type State Name", placeholder="e.g. JHARKHAND", key=f"{prefix}_new_st").upper().strip()
            if st.button("Lock State", key=f"{prefix}_btn_st"):
                add_creatable_item("master_states", {"name": new_st})
                st.rerun()
            ch_state = new_st
        else: ch_state = s_st

    dist_list = get_creatable_list("master_districts", "name", "state_name=?", (ch_state,))
    if not dist_list and ch_state == "JHARKHAND":
        dist_list = list(JHARKHAND_BLOCK_DISTRICT_MAP.keys())

    def_dt_idx = dist_list.index(prof[7]) if prof and prof[7] in dist_list else 0
    with c_l2:
        s_dt = st.selectbox("District", dist_list + ["➕ Add New District"], index=def_dt_idx if dist_list else 0, key=f"{prefix}_dt")
        if s_dt == "➕ Add New District":
            new_dt = st.text_input("Type District Name", placeholder="e.g. KHUNTI", key=f"{prefix}_new_dt").upper().strip()
            if st.button("Lock District", key=f"{prefix}_btn_dt"):
                add_creatable_item("master_districts", {"state_name": ch_state, "name": new_dt})
                st.rerun()
            ch_dist = new_dt
        else: ch_dist = s_dt

    dept_list = get_creatable_list("master_departments", "name")
    def_dp_idx = dept_list.index(prof[8]) if prof and prof[8] in dept_list else 0
    with c_l3:
        s_dp = st.selectbox("Department", dept_list + ["➕ Add New Department"], index=def_dp_idx, key=f"{prefix}_dp")
        if s_dp == "➕ Add New Department":
            new_dp = st.text_input("Type Dept Name", placeholder="e.g. SCHOOL EDUCATION & LITERACY", key=f"{prefix}_new_dp").upper().strip()
            if st.button("Lock Dept", key=f"{prefix}_btn_dp"):
                add_creatable_item("master_departments", {"name": new_dp})
                st.rerun()
            ch_dept = new_dp
        else: ch_dept = s_dp

    c_d1, c_d2 = st.columns(2)
    conn = sqlite3.connect(DB_NAME)
    matching_ddos = conn.cursor().execute("SELECT id, officer_name, tan, address, city, pincode FROM ddo_masters WHERE district=? AND department=?", (ch_dist, ch_dept)).fetchall()
    conn.close()

    with c_d1:
        if matching_ddos:
            ddo_opts = {f"DDO: {d[1]} | TAN: {d[2]}": d[0] for d in matching_ddos}
            ch_ddo_name = st.selectbox("Select DDO Center", list(ddo_opts.keys()), key=f"{prefix}_ddo_s")
            ch_ddo_id = ddo_opts[ch_ddo_name]
        else:
            st.warning("No DDO registered for this location yet.")
            with st.popover("➕ Create DDO Center"):
                in_off = st.text_input("Officer Name", placeholder="e.g. Principal / Incharge", key=f"{prefix}_in_off")
                in_fat = st.text_input("Father's Name (S/O)", placeholder="e.g. Father's Name", key=f"{prefix}_in_fat")
                in_tan = st.text_input("TAN Number", placeholder="e.g. PTIK01234A", key=f"{prefix}_in_tan").upper()
                in_add = st.text_input("Office Address", placeholder="e.g. SEAL DEPARTMENT GOVT. OF JHARKHAND", key=f"{prefix}_in_add")
                c_c1, c_c2 = st.columns(2)
                with c_c1: in_city = st.text_input("City", placeholder="e.g. KHUNTI", key=f"{prefix}_in_city")
                with c_c2: in_pin = st.text_input("PIN Code", placeholder="e.g. 835210", key=f"{prefix}_in_pin")

                if st.button("Save DDO", key=f"{prefix}_in_ddo_btn"):
                    if in_off and in_tan:
                        conn = sqlite3.connect(DB_NAME)
                        conn.cursor().execute("INSERT INTO ddo_masters (state, district, department, officer_name, father_name, tan, address, city, pincode) VALUES (?,?,?,?,?,?,?,?,?)",
                                              (ch_state, ch_dist, ch_dept, in_off, in_fat, in_tan, in_add, in_city, in_pin))
                        conn.commit()
                        conn.close()
                        st.rerun()
                    else:
                        st.error("Please provide Officer Name and TAN.")
            ch_ddo_id = None

    with c_d2:
        off_list = get_creatable_list("master_offices", "name_and_address", "district=? AND department=?", (ch_dist, ch_dept))
        def_o_idx = off_list.index(prof[9]) if prof and prof[9] in off_list else 0
        s_of = st.selectbox("Office / School Address", off_list + ["➕ Add New Office Address"], index=def_o_idx if off_list else 0, key=f"{prefix}_off")
        if s_of == "➕ Add New Office Address":
            new_of = st.text_input("Full Address", placeholder="e.g. Upgraded +2 High School...", key=f"{prefix}_new_of").strip()
            if st.button("Lock Address", key=f"{prefix}_btn_of"):
                add_creatable_item("master_offices", {"district": ch_dist, "department": ch_dept, "name_and_address": new_of})
                st.rerun()
            ch_office = new_of
        else: ch_office = s_of

    # 7th CPC Matrix & Increment Level Progression
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    with c_m1: s_lvl = st.selectbox("7th CPC Pay Level (Grade Pay)", list(CPC_7TH_MATRIX.keys()), key=f"{prefix}_lvl")
    with c_m2: s_bsc = st.number_input("March Basic Pay", step=100, key=f"{prefix}_bsc")
    with c_m3: s_incm = st.selectbox("Increment Month", ["NONE", "1st JULY", "1st JANUARY"], key=f"{prefix}_incm")
    
    auto_next_cell = get_next_matrix_cell(s_lvl, s_bsc)
    with c_m4: 
        s_incb = st.number_input("Incremented Basic (7th CPC Matrix)", value=int(auto_next_cell), step=100, key=f"{prefix}_incb")

    s_pen = st.radio("Pension Scheme", ["Old Pension (GPF / OPS)", "NPS (10% Basic+DA)"], horizontal=True, key=f"{prefix}_pen")

    st.markdown("##### 🔍 Verification & Monthly Allowance Card")
    with st.container(border=True):
        c_v1, c_v2, c_v3, c_v4 = st.columns(4)
        with c_v1:
            v_name = st.text_input("Full Name *", key=f"{prefix}_vn")
            v_des = st.text_input("Designation", key=f"{prefix}_vd")
        with c_v2:
            v_mob = st.text_input("Mobile No *", value=prof[3] if prof else "", key=f"{prefix}_vm")
            v_eml = st.text_input("Email (PDF Dispatch)", value=prof[4] if prof else "", key=f"{prefix}_ve")
        with c_v3:
            v_gpf_no = st.text_input("GPF / PRAN / PF Number (Employee Ref No)", key=f"{prefix}_vgpf_no")
            v_da = st.number_input("Monthly DA", step=100, key=f"{prefix}_vda")
        with c_v4:
            v_hra = st.number_input("Monthly HRA", step=100, key=f"{prefix}_vhra")
            v_gpf = st.number_input("Monthly GPF / NPS / PF", step=100, key=f"{prefix}_vgpf")
            v_tds = st.number_input("Monthly TDS (Mar-Jan)", step=500, key=f"{prefix}_vtds")

    # Dedicated Arrear Section
    st.markdown("##### 💰 Arrear Allowances (Auto-detected & Editable)")
    with st.container(border=True):
        c_ar1, c_ar2, c_ar3 = st.columns(3)
        with c_ar1:
            arr_da = st.number_input("DA Arrear Total (₹)", step=500.0, key=f"{prefix}_arrear_da")
        with c_ar2:
            arr_pay = st.number_input("Pay / Other Arrears (₹)", step=1000.0, key=f"{prefix}_arrear_pay")
        with c_ar3:
            arr_tds = st.number_input("TDS Deducted in Arrears (₹)", step=500.0, key=f"{prefix}_arrear_tds")

    decl_data = {}
    if regime_sel == "Old Regime":
        with st.expander("🧾 Old Regime Deductions & Other Income Declarations", expanded=True):
            cd1, cd2, cd3 = st.columns(3)
            with cd1:
                decl_data['sec80c'] = st.number_input("80C (PPF/LIC/Tuition/GPF)", min_value=0.0, step=1000.0, key=f"{prefix}_80c")
                decl_data['sec80d'] = st.number_input("80D (Mediclaim)", min_value=0.0, step=1000.0, key=f"{prefix}_80d")
            with cd2:
                decl_data['house_property_loss'] = st.number_input("Home Loan Interest Loss (24b)", min_value=0.0, step=5000.0, key=f"{prefix}_hloss")
                decl_data['sec80e'] = st.number_input("80E (Education Loan Interest)", min_value=0.0, step=1000.0, key=f"{prefix}_80e")
            with cd3:
                decl_data['bank_interest'] = st.number_input("Bank Savings Interest", min_value=0.0, step=500.0, key=f"{prefix}_bint")
                decl_data['sec80tta'] = st.number_input("80TTA Exemption", min_value=0.0, max_value=10000.0, step=500.0, key=f"{prefix}_80tta")
                decl_data['relief_89'] = st.number_input("Relief u/s 89", min_value=0.0, step=500.0, key=f"{prefix}_r89")

    # Regular 11 months construction
    recs_11 = []
    for idx in range(11):
        m = JHARKHAND_MONTHS[idx]
        cb = s_incb if (s_incm == "1st JULY" and idx >= 4) or (s_incm == "1st JANUARY" and idx >= 10) else s_bsc
        cg = cb + v_da + v_hra + 1000.0
        recs_11.append({
            'month': m, 'basic': cb, 'da': v_da, 'hra': v_hra, 'medical': 1000.0,
            'arrear_da': 0.0, 'arrear_pay': 0.0, 'gross': cg, 'gpf': v_gpf,
            'gis': 60.0, 'ptax': 200.0, 'tds': float(v_tds), 'net': cg - (v_gpf + 260 + v_tds)
        })

    full_12, tax_calc = compute_annual_tax_with_regime(
        recs_11, regime=regime_sel, decl_data=decl_data, 
        manual_arrear_da=arr_da, manual_arrear_pay=arr_pay, extra_tds=arr_tds
    )
    
    st.info(f"🎯 **Automated Balancing Summary:** Gross: ₹{tax_calc['gross']:,.0f} | DA Arrear: ₹{tax_calc['tot_arrear_da']:,.0f} | Pay Arrear: ₹{tax_calc['tot_arrear_pay']:,.0f} | **Feb Balancing TDS:** ₹{tax_calc['feb_tds']:,.0f} | **Final Schedule Balance:** ₹{tax_calc['net_balance']:,.0f} (NIL)")

    # ================= 100% FREE TRIAL OPTION (WITHOUT PAYMENT) =================
    st.markdown("---")
    st.markdown("##### 🧪 Free Trial / Instant Verification (No Payment Needed)")
    st.caption("Aap bina koi payment kiye apna poora 4-page Tax Schedule & Form 16 Trial Copy turant download karke verify kar sakte hain.")

    if st.button("📥 Download Free Trial Copy (Watermarked PDF)", use_container_width=True, key=f"{prefix}_trial_btn"):
        if not (pan_in and v_name and ch_office):
            st.error("Please fill at least PAN, Name and Office Address to preview!")
        else:
            conn = sqlite3.connect(DB_NAME)
            ddo_row_preview = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (ch_ddo_id,)).fetchone() if ch_ddo_id else None
            conn.close()

            if ddo_row_preview:
                ddo_d_trial = {
                    'state': ddo_row_preview[1], 'district': ddo_row_preview[2], 'department': ddo_row_preview[3], 
                    'officer_name': ddo_row_preview[4], 'father_name': ddo_row_preview[5], 'tan': ddo_row_preview[6], 
                    'address': ddo_row_preview[7] or '', 'city': ddo_row_preview[8] or ddo_row_preview[2], 'pincode': ddo_row_preview[9] or ''
                }
            else:
                ddo_d_trial = {
                    'state': ch_state, 'district': ch_dist, 'department': ch_dept,
                    'officer_name': "DDO Incharge", 'father_name': "Officer Father", 
                    'tan': "PTIK01234A", 'address': ch_office, 'city': ch_dist, 'pincode': "835210"
                }

            emp_d_trial = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': v_name, 'designation': v_des, 'office_name': ch_office, 'gpf_no': v_gpf_no}
            trial_pdf_data = generate_pdf_bundle(ddo_d_trial, emp_d_trial, full_12, tax_calc, decl_dict=decl_data, is_trial=True)
            
            st.success("✅ Trial PDF generated successfully! Niche diye button se download karein:")
            st.download_button(
                label="📄 Click here to Download TRIAL PDF Now",
                data=trial_pdf_data,
                file_name=f"TRIAL_{pan_in}_{GLOBAL_AY}.pdf",
                mime="application/pdf",
                key=f"{prefix}_trial_dl_btn",
                use_container_width=True
            )

    st.markdown("---")
    st.markdown("##### 🚀 Official Submission & Final Unlocked Generation")

    if is_admin_mode:
        if st.button("🚀 Save & Generate Official Unlocked PDF Bundle", use_container_width=True, key=f"{prefix}_adm_btn"):
            if not (pan_in and v_name and ch_office and ch_ddo_id):
                st.error("Please fill PAN, Name, DDO and Office!")
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                today_str = date.today().strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute('''INSERT INTO employee_master_profiles (
                    pan, name, designation, mobile, email, gpf_no, last_state, last_district, last_dept,
                    last_office, last_ddo_id, last_pay_level, last_basic_pay, last_inc_month,
                    pension_type, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(pan) DO UPDATE SET
                        name=excluded.name, last_office=excluded.last_office, last_basic_pay=excluded.last_basic_pay, gpf_no=excluded.gpf_no''',
                    (pan_in, v_name, v_des, v_mob, v_eml, v_gpf_no, ch_state, ch_dist, ch_dept, ch_office, ch_ddo_id,
                     s_lvl, s_bsc, s_incm, "GPF" if "GPF" in s_pen else "NPS", now_str))

                conn.cursor().execute('''INSERT INTO employee_yearly_records (
                    ay, ddo_id, pan, name, designation, office_name, service_status, pay_level,
                    pension_type, tax_regime, start_basic, inc_month, inc_basic, default_da, default_hra,
                    default_med, default_gpf, default_gis, default_ptax, monthly_tds, mobile,
                    email, payment_status, payment_mode, utr_no, amount_paid, created_at, created_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ay, pan) DO UPDATE SET payment_status='APPROVED', tax_regime=excluded.tax_regime''',
                    (GLOBAL_AY, ch_ddo_id, pan_in, v_name, v_des, ch_office, status_sel, s_lvl,
                     "GPF" if "GPF" in s_pen else "NPS", regime_sel, s_bsc, s_incm, s_incb, v_da, v_hra, 1000.0,
                     v_gpf, 60.0, 200.0, v_tds, v_mob, v_eml, 'APPROVED', 'ADMIN_DIRECT', 'ADMIN_AUTH', 0.0, now_str, today_str))
                
                y_id = conn.cursor().execute("SELECT id FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()[0]

                conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_id,))
                for r in full_12:
                    conn.cursor().execute('''INSERT INTO monthly_salary_ledgers (
                        yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay,
                        gross, gpf, gis, ptax, tds, net, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (y_id, r['month'], r['basic'], r['da'], r['hra'], r['medical'], r['arrear_da'], r['arrear_pay'], r['gross'], r['gpf'], r['gis'], r['ptax'], r['tds'], r['net'], 'System Auto'))
                
                conn.cursor().execute("DELETE FROM employee_tax_declarations WHERE yearly_record_id=?", (y_id,))
                conn.cursor().execute('''INSERT INTO employee_tax_declarations (
                    yearly_record_id, sec80c, sec80d, sec80e, sec80tta, house_property_loss, bank_interest, relief_89, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (y_id, decl_data.get('sec80c',0), decl_data.get('sec80d',0), decl_data.get('sec80e',0), decl_data.get('sec80tta',0),
                     decl_data.get('house_property_loss',0), decl_data.get('bank_interest',0), decl_data.get('relief_89',0), now_str))

                ddo_r = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (ch_ddo_id,)).fetchone()
                deps = conn.cursor().execute("SELECT * FROM tds_deposits WHERE yearly_record_id=?", (y_id,)).fetchall()
                conn.commit()
                conn.close()

                ddo_d = {
                    'state': ddo_r[1], 'district': ddo_r[2], 'department': ddo_r[3], 
                    'officer_name': ddo_r[4], 'father_name': ddo_r[5], 'tan': ddo_r[6], 
                    'address': ddo_r[7] or '', 'city': ddo_r[8] or ddo_r[2], 'pincode': ddo_r[9] or ''
                }
                emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': v_name, 'designation': v_des, 'office_name': ch_office, 'gpf_no': v_gpf_no}
                pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, full_12, tax_calc, deps, decl_data, is_trial=False)

                if v_eml:
                    send_email_with_pdf(v_eml, f"Official Form 16 & Schedule - {GLOBAL_AY}", "Attached is your official Form 16 bundle.", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf")
                st.download_button("📥 Download Official 4-Page PDF Now", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf", "application/pdf", use_container_width=True)
    else:
        c_fee = float(get_setting('form_fee', '100'))
        c_upi = get_setting('upi_id', 'nitinmallick111-1@okicici')
        is_wl = is_pan_whitelisted(pan_in)

        if is_wl:
            st.success("⭐ Pre-Approved Whitelist active: Payment requirement bypassed.")
            btn_t = st.button("🚀 Generate Official PDF Bundle (Instant)", use_container_width=True, key=f"{prefix}_t_btn")
            u_mode, u_utr, fee_amt = "WHITELIST", "PRE_APPROVED", 0.0
        else:
            st.write(f"**Official Copy Processing Fee:** ₹{c_fee:,.0f}")
            p_mode = st.radio("Payment Method:", [f"💳 UPI QR (₹{c_fee:,.0f})", "💵 Paid Cash to Admin"], horizontal=True, key=f"{prefix}_pm")
            u_utr = ""
            if "UPI" in p_mode:
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=upi://pay?pa={c_upi}%26pn=TDS%20Office%26am={c_fee}%26cu=INR"
                st.image(qr_url, caption="Scan & Pay via any UPI App")
                u_utr = st.text_input("Enter 12-Digit UTR Number *", key=f"{prefix}_utr")
            btn_t = st.button("🚀 Submit Request for Official Unlocked Copy", use_container_width=True, key=f"{prefix}_t_btn")
            u_mode = "CASH" if "Cash" in p_mode else "UPI"
            fee_amt = c_fee

        if btn_t:
            if not (pan_in and v_name and v_mob and ch_office and ch_ddo_id):
                st.error("Please fill PAN, Name, Mobile, DDO and Office!")
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                today_str = date.today().strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute('''INSERT INTO employee_master_profiles (
                    pan, name, designation, mobile, email, gpf_no, last_state, last_district, last_dept,
                    last_office, last_ddo_id, last_pay_level, last_basic_pay, last_inc_month,
                    pension_type, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(pan) DO UPDATE SET
                        name=excluded.name, last_office=excluded.last_office, last_basic_pay=excluded.last_basic_pay, gpf_no=excluded.gpf_no''',
                    (pan_in, v_name, v_des, v_mob, v_eml, v_gpf_no, ch_state, ch_dist, ch_dept, ch_office, ch_ddo_id,
                     s_lvl, s_bsc, s_incm, "GPF" if "GPF" in s_pen else "NPS", now_str))

                pay_stat = "APPROVED" if is_wl else "PENDING"
                conn.cursor().execute('''INSERT INTO employee_yearly_records (
                    ay, ddo_id, pan, name, designation, office_name, service_status, pay_level,
                    pension_type, tax_regime, start_basic, inc_month, inc_basic, default_da, default_hra,
                    default_med, default_gpf, default_gis, default_ptax, monthly_tds, mobile,
                    email, payment_status, payment_mode, utr_no, amount_paid, created_at, created_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ay, pan) DO UPDATE SET payment_status=excluded.payment_status, tax_regime=excluded.tax_regime''',
                    (GLOBAL_AY, ch_ddo_id, pan_in, v_name, v_des, ch_office, status_sel, s_lvl,
                     "GPF" if "GPF" in s_pen else "NPS", regime_sel, s_bsc, s_incm, s_incb, v_da, v_hra, 1000.0,
                     v_gpf, 60.0, 200.0, v_tds, v_mob, v_eml, pay_stat, u_mode, u_utr, fee_amt, now_str, today_str))
                
                y_id = conn.cursor().execute("SELECT id FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()[0]

                conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_id,))
                for r in full_12:
                    conn.cursor().execute('''INSERT INTO monthly_salary_ledgers (
                        yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay,
                        gross, gpf, gis, ptax, tds, net, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (y_id, r['month'], r['basic'], r['da'], r['hra'], r['medical'], r['arrear_da'], r['arrear_pay'], r['gross'], r['gpf'], r['gis'], r['ptax'], r['tds'], r['net'], 'Self-Service Submission'))
                
                conn.cursor().execute("DELETE FROM employee_tax_declarations WHERE yearly_record_id=?", (y_id,))
                conn.cursor().execute('''INSERT INTO employee_tax_declarations (
                    yearly_record_id, sec80c, sec80d, sec80e, sec80tta, house_property_loss, bank_interest, relief_89, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (y_id, decl_data.get('sec80c',0), decl_data.get('sec80d',0), decl_data.get('sec80e',0), decl_data.get('sec80tta',0),
                     decl_data.get('house_property_loss',0), decl_data.get('bank_interest',0), decl_data.get('relief_89',0), now_str))

                ddo_r = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (ch_ddo_id,)).fetchone()
                conn.commit()
                conn.close()

                if is_wl:
                    ddo_d = {
                        'state': ddo_r[1], 'district': ddo_r[2], 'department': ddo_r[3], 
                        'officer_name': ddo_r[4], 'father_name': ddo_r[5], 'tan': ddo_r[6], 
                        'address': ddo_r[7] or '', 'city': ddo_r[8] or ddo_r[2], 'pincode': ddo_r[9] or ''
                    }
                    emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': v_name, 'designation': v_des, 'office_name': ch_office, 'gpf_no': v_gpf_no}
                    pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, full_12, tax_calc, decl_dict=decl_data, is_trial=False)
                    if v_eml:
                        send_email_with_pdf(v_eml, f"Official Form 16 - {GLOBAL_AY}", "Attached is your Form 16.", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf")
                    st.download_button("📥 Download Official 4-Page PDF Now", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf", "application/pdf", use_container_width=True)
                else:
                    st.success("Request recorded successfully! Once payment is verified by Admin, download directly from 'Already Paid' tab.")

# ================= TOP BAR & SECRET URL ROUTING =================
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

# ================= TAB 1: PUBLIC EMPLOYEE PORTAL =================
with tab_emp:
    render_full_employee_suite(is_admin_mode=False, prefix="emp_public")

# ================= TAB 2: RE-DOWNLOAD ARCHIVE =================
with tab_redownload:
    st.markdown("### 🔍 Re-Download Official Form 16 & Tax Schedule")
    c_rd1, c_rd2 = st.columns(2)
    with c_rd1: rd_pan = st.text_input("Enter PAN Number", key="rd_pan_field").upper().strip()
    with c_rd2: rd_ay = st.selectbox("Select Assessment Year", AY_OPTIONS, key="rd_ay_field")

    if st.button("Search Archive & Generate Download"):
        if not rd_pan:
            st.warning("Please enter your PAN.")
        else:
            conn = sqlite3.connect(DB_NAME)
            y_rec = conn.cursor().execute("SELECT * FROM employee_yearly_records WHERE ay=? AND pan=?", (rd_ay, rd_pan)).fetchone()
            conn.close()

            if not y_rec:
                st.error(f"No record found for PAN: {rd_pan} in {rd_ay}.")
            elif y_rec[22] != "APPROVED":
                st.warning(f"Record found for {y_rec[4]}, but Payment Status is **{y_rec[22]}**. Awaiting Admin Verification.")
            else:
                conn = sqlite3.connect(DB_NAME)
                ddo_row = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (y_rec[2],)).fetchone()
                ledgers = conn.cursor().execute("SELECT * FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_rec[0],)).fetchall()
                decl_row = conn.cursor().execute("SELECT * FROM employee_tax_declarations WHERE yearly_record_id=?", (y_rec[0],)).fetchone()
                deposits = conn.cursor().execute("SELECT * FROM tds_deposits WHERE yearly_record_id=?", (y_rec[0],)).fetchall()
                prof_row = conn.cursor().execute("SELECT gpf_no FROM employee_master_profiles WHERE pan=?", (rd_pan,)).fetchone()
                conn.close()

                recs_rd = [{
                    'month': l[2], 'basic': l[3], 'da': l[4], 'hra': l[5], 'medical': l[6],
                    'arrear_da': l[7], 'arrear_pay': l[8], 'gross': l[9], 'gpf': l[10],
                    'gis': l[11], 'ptax': l[12], 'tds': l[13], 'net': l[14]
                } for l in ledgers]

                d_dict = {}
                if decl_row:
                    d_dict = {'sec80c': decl_row[6], 'sec80d': decl_row[9], 'sec80e': decl_row[12], 'sec80tta': decl_row[15], 'house_property_loss': decl_row[3], 'bank_interest': decl_row[4], 'relief_89': decl_row[5]}

                full_12_rd, tax_rd = compute_annual_tax_with_regime(recs_rd[:11], regime=y_rec[10], decl_data=d_dict)
                ddo_d = {
                    'state': ddo_row[1], 'district': ddo_row[2], 'department': ddo_row[3], 
                    'officer_name': ddo_row[4], 'father_name': ddo_row[5], 'tan': ddo_row[6], 
                    'address': ddo_row[7] or '', 'city': ddo_row[8] or ddo_row[2], 'pincode': ddo_row[9] or ''
                }
                emp_d = {'ay': rd_ay, 'pan': rd_pan, 'name': y_rec[4], 'designation': y_rec[5], 'office_name': y_rec[6], 'gpf_no': prof_row[0] if prof_row else ""}
                pdf_data = generate_pdf_bundle(ddo_d, emp_d, full_12_rd, tax_rd, deposits, d_dict, is_trial=False)

                st.success(f"Verified Record Found: **{y_rec[4]}** | Office: {y_rec[6]}")
                col_dla, col_dlb = st.columns(2)
                with col_dla:
                    st.download_button("📥 Download Official 4-Page PDF Bundle", pdf_data, f"{rd_pan}_{rd_ay}.pdf", "application/pdf", use_container_width=True)
                with col_dlb:
                    if y_rec[21] and st.button("📩 Re-Send to Registered Email"):
                        sent = send_email_with_pdf(y_rec[21], f"Official Form 16 - {rd_ay}", "Attached is your official Form 16.", pdf_data, f"{rd_pan}_{rd_ay}.pdf")
                        if sent: st.toast("Email sent successfully!")

# ================= TAB 3: ADMIN COMMAND CENTER =================
if tab_admin:
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
            col_lout1, col_lout2 = st.columns([6, 1])
            with col_lout2:
                if st.button("🚪 Logout Admin"):
                    st.session_state.admin_logged_in = False
                    st.rerun()

            adm_sub_tab0, adm_sub_tab1, adm_sub_tab2, adm_sub_tab3, adm_sub_tab4, adm_sub_tab5, adm_sub_tab6 = st.tabs([
                "⚡ Single Employee Suite",
                "📊 Revenue & Analytics",
                "🗃️ Master Database Manager",
                "📥 Live Payment Queue",
                "🏦 Statutory TDS Deposits",
                "🏛️ DDO & Hierarchy Master",
                "⚙️ Config & Credentials"
            ])

            # --- 0. SINGLE EMPLOYEE SUITE ---
            with adm_sub_tab0:
                render_full_employee_suite(is_admin_mode=True, prefix="adm_private")

            # --- 1. REVENUE & ANALYTICS DASHBOARD ---
            with adm_sub_tab1:
                st.subheader("📈 Financial Collection Analytics & Date Range Filter")
                
                c_dt1, c_dt2 = st.columns(2)
                with c_dt1: filter_from = st.date_input("From Date", value=date(2024, 4, 1))
                with c_dt2: filter_to = st.date_input("To Date", value=date.today())

                conn = sqlite3.connect(DB_NAME)
                raw_records = conn.cursor().execute("""
                    SELECT payment_mode, payment_status, amount_paid, created_date, pan, name 
                    FROM employee_yearly_records 
                    WHERE ay=? AND created_date >= ? AND created_date <= ?
                """, (GLOBAL_AY, filter_from.strftime("%Y-%m-%d"), filter_to.strftime("%Y-%m-%d"))).fetchall()
                conn.close()

                total_upi_rev = sum(r[2] for r in raw_records if r[0] == 'UPI' and r[1] == 'APPROVED')
                total_cash_rev = sum(r[2] for r in raw_records if r[0] == 'CASH' and r[1] == 'APPROVED')
                whitelisted_count = sum(1 for r in raw_records if r[0] == 'WHITELIST')
                pending_count = sum(1 for r in raw_records if r[1] == 'PENDING')
                grand_total_rev = total_upi_rev + total_cash_rev

                today_str = date.today().strftime("%Y-%m-%d")
                daily_rev = sum(r[2] for r in raw_records if r[3] == today_str and r[1] == 'APPROVED')

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Today's Revenue", f"₹{daily_rev:,.0f}")
                m2.metric("Filtered Total", f"₹{grand_total_rev:,.0f}")
                m3.metric("UPI Revenue", f"₹{total_upi_rev:,.0f}")
                m4.metric("Cash Revenue", f"₹{total_cash_rev:,.0f}")
                m5.metric("Whitelisted (Free)", whitelisted_count)

                st.write("---")
                st.markdown("#### 📥 Download Accountant Audit Register (.xlsx)")
                if st.button("Generate Audit Report (.xlsx)"):
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = "Financial Audit Register"
                    
                    ws.append(["TDS & FORM 16 FINANCIAL AUDIT REPORT", f"AY: {GLOBAL_AY}"])
                    ws.append([f"Period: {filter_from} to {filter_to}", f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"])
                    ws.append([])
                    ws.append(["Sl No", "PAN", "Employee Name", "Date", "Channel", "Status", "Amount Paid (Rs)"])
                    
                    for idx, r in enumerate(raw_records, 1):
                        ws.append([idx, r[4], r[5], r[3], r[0], r[1], r[2]])
                    
                    ws.append([])
                    ws.append(["TOTAL REVENUE (UPI + CASH)", "", "", "", "", "", grand_total_rev])

                    xl_buf = io.BytesIO()
                    wb.save(xl_buf)
                    st.download_button(
                        label="💾 Download Audit Register Excel (.xlsx)",
                        data=xl_buf.getvalue(),
                        file_name=f"Audit_Report_{filter_from}_to_{filter_to}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            # --- 2. MASTER DATABASE MANAGER ---
            with adm_sub_tab2:
                st.subheader("🗃️ Master Database Manager")
                conn = sqlite3.connect(DB_NAME)
                users = conn.cursor().execute("""
                    SELECT id, pan, name, designation, office_name, start_basic, payment_status, payment_mode, mobile, amount_paid, tax_regime 
                    FROM employee_yearly_records WHERE ay=? ORDER BY id DESC
                """, (GLOBAL_AY,)).fetchall()
                conn.close()

                st.markdown(f"**Total Registered Records ({GLOBAL_AY}):** {len(users)}")
                
                for u in users:
                    u_id, u_pan, u_name, u_des, u_off, u_bsc, u_stat, u_mod, u_mob, u_amt, u_reg = u
                    with st.expander(f"👤 {u_name} ({u_pan}) | {u_off} | Regime: {u_reg} | Status: {u_stat}"):
                        with st.form(f"crud_form_{u_id}"):
                            ce1, ce2, ce3 = st.columns(3)
                            with ce1:
                                ed_name = st.text_input("Name", value=u_name, key=f"ed_n_{u_id}")
                                ed_pan = st.text_input("PAN", value=u_pan, key=f"ed_p_{u_id}").upper()
                            with ce2:
                                ed_des = st.text_input("Designation", value=u_des, key=f"ed_d_{u_id}")
                                ed_bsc = st.number_input("Basic Pay", value=int(u_bsc), key=f"ed_b_{u_id}")
                            with ce3:
                                ed_stat = st.selectbox("Status", ["APPROVED", "PENDING", "REJECTED"], index=["APPROVED", "PENDING", "REJECTED"].index(u_stat) if u_stat in ["APPROVED", "PENDING", "REJECTED"] else 0, key=f"ed_s_{u_id}")
                                ed_amt = st.number_input("Amount Paid", value=int(u_amt), key=f"ed_a_{u_id}")
                            
                            c_btn_a, c_btn_d = st.columns([1, 1])
                            with c_btn_a:
                                if st.form_submit_button("💾 Save Changes"):
                                    conn = sqlite3.connect(DB_NAME)
                                    conn.cursor().execute("UPDATE employee_yearly_records SET name=?, pan=?, designation=?, start_basic=?, payment_status=?, amount_paid=? WHERE id=?",
                                                          (ed_name, ed_pan, ed_des, ed_bsc, ed_stat, ed_amt, u_id))
                                    conn.commit()
                                    conn.close()
                                    st.success("Updated successfully!")
                                    st.rerun()
                            with c_btn_d:
                                if st.form_submit_button("🗑️ Delete Record Permanently"):
                                    conn = sqlite3.connect(DB_NAME)
                                    conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (u_id,))
                                    conn.cursor().execute("DELETE FROM employee_tax_declarations WHERE yearly_record_id=?", (u_id,))
                                    conn.cursor().execute("DELETE FROM tds_deposits WHERE yearly_record_id=?", (u_id,))
                                    conn.cursor().execute("DELETE FROM employee_yearly_records WHERE id=?", (u_id,))
                                    conn.commit()
                                    conn.close()
                                    st.warning("Deleted record!")
                                    st.rerun()

            # --- 3. LIVE PAYMENT QUEUE ---
            with adm_sub_tab3:
                st.subheader(f"Pending Verifications - {GLOBAL_AY}")
                conn = sqlite3.connect(DB_NAME)
                reqs = conn.cursor().execute("SELECT * FROM employee_yearly_records WHERE ay=? ORDER BY id DESC", (GLOBAL_AY,)).fetchall()
                conn.close()

                for r in reqs:
                    with st.container(border=True):
                        cA, cB, cC = st.columns([3, 2, 2])
                        with cA:
                            st.markdown(f"**{r[4]}** (`{r[3]}`) | 📞 {r[20]}")
                            st.caption(f"Office: {r[6]} | Basic: ₹{r[11]:,.0f} | Regime: **{r[10]}**")
                        with cB:
                            st.markdown(f"**Mode:** {r[23]} | **UTR:** `{r[24]}`")
                            st.caption(f"Status: **{r[22]}** | Time: {r[26]}")
                        with cC:
                            if r[22] == "PENDING":
                                if st.button("✅ Verify & Approve", key=f"q_app_{r[0]}"):
                                    conn = sqlite3.connect(DB_NAME)
                                    conn.cursor().execute("UPDATE employee_yearly_records SET payment_status='APPROVED' WHERE id=?", (r[0],))
                                    conn.commit()
                                    conn.close()
                                    st.success(f"Approved {r[4]}!")
                                    st.rerun()
                            else:
                                conn = sqlite3.connect(DB_NAME)
                                ddo_row = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (r[2],)).fetchone()
                                ledgers = conn.cursor().execute("SELECT * FROM monthly_salary_ledgers WHERE yearly_record_id=?", (r[0],)).fetchall()
                                decl_row = conn.cursor().execute("SELECT * FROM employee_tax_declarations WHERE yearly_record_id=?", (r[0],)).fetchone()
                                deps = conn.cursor().execute("SELECT * FROM tds_deposits WHERE yearly_record_id=?", (r[0],)).fetchall()
                                prof_row = conn.cursor().execute("SELECT gpf_no FROM employee_master_profiles WHERE pan=?", (r[3],)).fetchone()
                                conn.close()
                                
                                recs_adm = [{
                                    'month': l[2], 'basic': l[3], 'da': l[4], 'hra': l[5], 'medical': l[6],
                                    'arrear_da': l[7], 'arrear_pay': l[8], 'gross': l[9], 'gpf': l[10],
                                    'gis': l[11], 'ptax': l[12], 'tds': l[13], 'net': l[14]
                                } for l in ledgers]
                                
                                d_dict = {}
                                if decl_row:
                                    d_dict = {'sec80c': decl_row[6], 'sec80d': decl_row[9], 'sec80e': decl_row[12], 'sec80tta': decl_row[15], 'house_property_loss': decl_row[3], 'bank_interest': decl_row[4], 'relief_89': decl_row[5]}

                                full_12_adm, tax_adm = compute_annual_tax_with_regime(recs_adm[:11], regime=r[10], decl_data=d_dict)
                                ddo_d = {
                                    'state': ddo_row[1], 'district': ddo_row[2], 'department': ddo_row[3], 
                                    'officer_name': ddo_row[4], 'father_name': ddo_row[5], 'tan': ddo_row[6], 
                                    'address': ddo_row[7] or '', 'city': ddo_row[8] or ddo_row[2], 'pincode': ddo_row[9] or ''
                                }
                                emp_d = {'ay': GLOBAL_AY, 'pan': r[3], 'name': r[4], 'designation': r[5], 'office_name': r[6], 'gpf_no': prof_row[0] if prof_row else ""}
                                pdf_data = generate_pdf_bundle(ddo_d, emp_d, full_12_adm, tax_adm, deps, d_dict, is_trial=False)

                                st.download_button(
                                    label="📥 Download PDF",
                                    data=pdf_data,
                                    file_name=f"{r[3]}_{GLOBAL_AY}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_adm_q_{r[0]}"
                                )

            # --- 4. STATUTORY TDS DEPOSITS ---
            with adm_sub_tab4:
                st.subheader("🏦 Statutory TDS Deposits (Quarter-wise Challan / BIN)")
                conn = sqlite3.connect(DB_NAME)
                emp_list = conn.cursor().execute("SELECT id, pan, name FROM employee_yearly_records WHERE ay=?", (GLOBAL_AY,)).fetchall()
                conn.close()

                if emp_list:
                    emp_opts = {f"{e[1]} - {e[2]}": e[0] for e in emp_list}
                    sel_emp_str = st.selectbox("Select Employee for TDS Deposit Tagging", list(emp_opts.keys()))
                    sel_y_id = emp_opts[sel_emp_str]

                    with st.form("tds_deposit_form"):
                        cdp1, cdp2, cdp3, cdp4 = st.columns(4)
                        with cdp1: dep_qtr = st.selectbox("Quarter", ["Q1 (Apr-Jun)", "Q2 (Jul-Sep)", "Q3 (Oct-Dec)", "Q4 (Jan-Mar)"])
                        with cdp2: dep_month = st.selectbox("Month", JHARKHAND_MONTHS)
                        with cdp3: dep_amt = st.number_input("TDS Amount Deposited (₹)", min_value=0.0, step=500.0)
                        with cdp4: dep_date = st.date_input("Deposit Date", date.today())

                        cdp5, cdp6, cdp7 = st.columns(3)
                        with cdp5: dep_mode = st.selectbox("Mode", ["Book Adjustment (Treasury)", "Challan (OLTAS)"])
                        with cdp6: dep_bsr = st.text_input("BSR Code / BIN", placeholder="e.g. 0510304")
                        with cdp7: dep_challan = st.text_input("Challan Serial / DDO Serial No", placeholder="e.g. 00124")

                        if st.form_submit_button("Record Statutory Deposit"):
                            conn = sqlite3.connect(DB_NAME)
                            conn.cursor().execute('''INSERT INTO tds_deposits (
                                yearly_record_id, quarter, month_name, amount, deposit_date, mode, bsr_code, challan_serial)
                                VALUES (?,?,?,?,?,?,?,?)''',
                                (sel_y_id, dep_qtr, dep_month, dep_amt, dep_date.strftime("%Y-%m-%d"), dep_mode, dep_bsr, dep_challan))
                            conn.commit()
                            conn.close()
                            st.success("TDS Deposit linked successfully!")
                            st.rerun()

                    conn = sqlite3.connect(DB_NAME)
                    cur_deps = conn.cursor().execute("SELECT * FROM tds_deposits WHERE yearly_record_id=?", (sel_y_id,)).fetchall()
                    conn.close()
                    if cur_deps:
                        st.table([{ "Quarter": d[2], "Month": d[3], "Amount": d[4], "Date": d[5], "Mode": d[6], "BSR/BIN": d[7], "Challan": d[8] } for d in cur_deps])
                else:
                    st.info("No employees registered for this Assessment Year yet.")

            # --- 5. DDO MASTER ---
            with adm_sub_tab5:
                st.subheader("Manage Institutional DDO Centers")
                conn = sqlite3.connect(DB_NAME)
                ddo_table = conn.cursor().execute("SELECT id, state, district, department, officer_name, tan, address, city, pincode FROM ddo_masters").fetchall()
                conn.close()
                st.dataframe(ddo_table, use_container_width=True)

                with st.expander("➕ Register New DDO Center"):
                    with st.form("adm_new_ddo"):
                        a_st = st.selectbox("State", get_creatable_list("master_states", "name"))
                        a_dt = st.selectbox("District", get_creatable_list("master_districts", "name", "state_name=?", (a_st,)))
                        a_dp = st.selectbox("Department", get_creatable_list("master_departments", "name"))
                        a_off = st.text_input("Officer Incharge Name", placeholder="e.g. Principal / Incharge")
                        a_fat = st.text_input("Father's Name (S/O)", placeholder="e.g. Father's Name")
                        a_tan = st.text_input("TAN Number", placeholder="e.g. PTIK01234A").upper()
                        a_add = st.text_input("Office Address", placeholder="e.g. SEAL DEPARTMENT GOVT. OF JHARKHAND")
                        ac_c1, ac_c2 = st.columns(2)
                        with ac_c1: a_city = st.text_input("City", placeholder="e.g. KHUNTI")
                        with ac_c2: a_pin = st.text_input("PIN Code", placeholder="e.g. 835210")

                        if st.form_submit_button("Save DDO"):
                            conn = sqlite3.connect(DB_NAME)
                            conn.cursor().execute("INSERT INTO ddo_masters (state, district, department, officer_name, father_name, tan, address, city, pincode) VALUES (?,?,?,?,?,?,?,?,?)",
                                                  (a_st, a_dt, a_dp, a_off, a_fat, a_tan, a_add, a_city, a_pin))
                            conn.commit()
                            conn.close()
                            st.success("DDO Saved!")
                            st.rerun()

            # --- 6. CONFIG & CREDENTIALS ---
            with adm_sub_tab6:
                st.subheader("⚙️ Credentials, Pricing, Whitelist & Mail Config")
                
                c_cf1, c_cf2 = st.columns(2)
                with c_cf1:
                    st.markdown("**🔐 Change Admin Credentials**")
                    new_u = st.text_input("Admin Username", value=get_setting('admin_username', '__nit@def@admin26__'))
                    new_p = st.text_input("Admin Password", value=get_setting('admin_password', '19052027def@admin'))
                    if st.button("Update Login Credentials"):
                        set_setting('admin_username', new_u)
                        set_setting('admin_password', new_p)
                        st.success("Credentials updated successfully!")

                    st.write("---")
                    fee_val = st.text_input("Form Fee (₹)", value=get_setting('form_fee', '100'))
                    upi_val = st.text_input("Receiving UPI ID", value=get_setting('upi_id', 'nitinmallick111-1@okicici'))
                    if st.button("Save Fee & UPI"):
                        set_setting('form_fee', fee_val)
                        set_setting('upi_id', upi_val)
                        st.success("Pricing updated!")

                with c_cf2:
                    st.markdown("**⭐ Pre-Approved / Whitelisted PANs**")
                    pans_txt = st.text_area("Whitelisted PANs (Comma-Separated)", value=get_setting('whitelisted_pans', ''), height=120)
                    if st.button("Save Whitelist"):
                        set_setting('whitelisted_pans', pans_txt.upper())
                        st.success("Whitelist saved!")

                    st.write("---")
                    st.markdown("**📧 SMTP Dispatch Settings (Gmail)**")
                    smtp_e = st.text_input("SMTP Email", value=get_setting('smtp_email', ''))
                    smtp_p = st.text_input("SMTP App Password (16-Digit)", type="password", value=get_setting('smtp_password', ''))
                    if st.button("Save Mail Configuration"):
                        set_setting('smtp_email', smtp_e)
                        set_setting('smtp_password', smtp_p)
                        st.success("Email configuration saved!")

# ================= WEB FOOTER (BRANDING) =================
st.markdown("""
<div style="margin-top: 50px; text-align: center; color: #888; font-size: 11px; border-top: 1px solid #333; padding-top: 15px;">
  🏛️ <b>Kosh-Tax</b> | Comprehensive TDS & Form 16 Management Portal<br>
  <span style="color: #aaa;">Designed & Developed by Nitin</span>
</div>
""", unsafe_allow_html=True)

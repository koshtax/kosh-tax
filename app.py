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
    "MARCH 2024", "APRIL 2024", "MAY 2024", "JUNE 2024", 
    "JULY 2024", "AUGUST 2024", "SEPTEMBER 2024", "OCTOBER 2024", 
    "NOVEMBER 2024", "DECEMBER 2024", "JANUARY 2025", "FEBRUARY 2025"
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
        employer_type TEXT DEFAULT 'STATE GOVERNMENT',
        pension_type TEXT DEFAULT 'GPF',
        updated_at TEXT
    )''')

    for col in ["employer_type"]:
        try:
            c.execute(f"ALTER TABLE employee_master_profiles ADD COLUMN {col} TEXT DEFAULT 'STATE GOVERNMENT'")
        except Exception:
            pass

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

    for col in ["employer_type"]:
        try:
            c.execute(f"ALTER TABLE employee_yearly_records ADD COLUMN {col} TEXT DEFAULT 'STATE GOVERNMENT'")
        except Exception:
            pass

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

    c.execute("INSERT OR IGNORE INTO master_states (name) VALUES ('JHARKHAND'), ('BIHAR'), ('WEST BENGAL')")
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
    best_lvl = "LEVEL 7 (GP 4600)"
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

# ================= SMART CPC MATCHING HELPER =================
def find_exact_or_nearest_level(basic_pay):
    b_val = int(basic_pay)
    exact_matches = []
    
    # Pehle exact match dekhein saare levels mein
    for lvl, cells in CPC_7TH_MATRIX.items():
        if b_val in cells:
            exact_matches.append(lvl)
            
    if exact_matches:
        return exact_matches[0], exact_matches
        
    # Agar exact match nahi mila toh nearest level dhoondhein
    best_lvl = "LEVEL 7 (GP 4600)"
    min_diff = 999999
    for lvl, cells in CPC_7TH_MATRIX.items():
        for c in cells:
            diff = abs(c - b_val)
            if diff < min_diff:
                min_diff = diff
                best_lvl = lvl
    return best_lvl, [best_lvl]


def parse_slip_in_memory(uploaded_file):
    extracted = {
        'name': '',
        'pan': '',
        'designation': 'ASSISTANT TEACHER',
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
        'inc_month': '1ST JULY',
        'inc_basic': 56900.0,
        'pay_level': 'LEVEL 7 (GP 4600)',
        'matching_levels': [],
        'auto_district': 'KHUNTI',
        'auto_state': 'JHARKHAND',
        'employer_type': 'STATE GOVERNMENT',
        'pension_type': 'OLD PENSION (GPF / OPS)',
        'arrear_da': 0.0,
        'arrear_pay': 0.0,
        'arrear_tds': 0.0,
        'custom_arrear_rows': []
    }
    try:
        reader = PdfReader(uploaded_file)
        pages_text = [p.extract_text() or "" for p in reader.pages]
        full_text = "\n".join(pages_text)
        raw_clean = re.sub(r'[ \t]+', ' ', full_text).upper()

        if "GOVT. OF JHARKHAND" in raw_clean or "GOVERNMENT OF JHARKHAND" in raw_clean:
            extracted['auto_state'] = 'JHARKHAND'
            extracted['employer_type'] = 'STATE GOVERNMENT'
            extracted['pension_type'] = 'OLD PENSION (GPF / OPS)'
        elif "GOVT. OF INDIA" in raw_clean or "CENTRAL GOVT" in raw_clean or "KENDRIYA" in raw_clean or "RAILWAY" in raw_clean:
            extracted['employer_type'] = 'CENTRAL GOVERNMENT'
            extracted['pension_type'] = 'NPS (10% BASIC+DA)'
        elif "PVT LTD" in raw_clean or "LIMITED" in raw_clean or "PRIVATE" in raw_clean:
            extracted['employer_type'] = 'PRIVATE / CORPORATE'
            extracted['pension_type'] = 'NPS (10% BASIC+DA)'

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

        monthly_basics = {}
        for p_txt in pages_text:
            p_up = p_txt.upper()
            is_arrear = bool(re.search(r'ARREAR|BACK[- ]?DATED|ARREARS', p_up))
            b_val = get_clean_num(p_up, ["BASIC", "मूल वेतन"])
            da_val = get_clean_num(p_up, ["DA", "DEARNESS ALLOWANCE"])
            hra_val = get_clean_num(p_up, ["HRA"])
            med_val = get_clean_num(p_up, ["MEDICAL"])
            tds_val = get_clean_num(p_up, ["I.TAX", "ITAX", "1.TAX", "TDS"])
            gpf_val = get_clean_num(p_up, ["GPF", "NPS", "PRAN", "EPF"])

            if is_arrear:
                m_match = re.search(r'(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s*(\d{4})', p_up)
                m_name = f"ARREAR ({m_match.group(1)} {m_match.group(2)})" if m_match else "ARREAR / BACK-DATED"
                
                # Intelligent breakdown assignment if total block is found
                tot_amt = get_clean_num(p_up, ["TOTAL", "कुल योग"])
                if b_val == 0 and da_val == 0 and tot_amt > 0:
                    b_val = round(tot_amt * 0.6)
                    da_val = round(tot_amt * 0.3)
                    hra_val = round(tot_amt * 0.1)

                g_val = b_val + da_val + hra_val + (med_val or 0.0)
                extracted['custom_arrear_rows'].append({
                    'month': m_name, 'basic': b_val, 'da': da_val, 'hra': hra_val, 'medical': med_val or 0.0,
                    'arrear_da': da_val, 'arrear_pay': b_val,
                    'gross': g_val, 'gpf': gpf_val, 'gis': 0.0, 'ptax': 0.0, 'tds': tds_val,
                    'net': g_val - gpf_val - tds_val
                })
                if "JUL-DEC 2024" in p_up:
                    extracted['arrear_da'] += da_val if da_val > 0 else tot_amt
                else:
                    extracted['arrear_pay'] += tot_p if (('tot_p' in locals()) and tot_p > 0) else (b_val if b_val > 0 else tot_amt)
                if tds_val > 0:
                    extracted['arrear_tds'] += tds_val
            else:
                m_m = re.search(r'SALARY\s*SLIP\s*[-–]?\s*([A-Z]{3,9})\s*(\d{4})', p_up)
                if m_m and b_val > 0:
                    m_str = m_m.group(1)[:3]
                    monthly_basics[m_str] = b_val

               mar_b = monthly_basics.get("MAR", 0.0) or monthly_basics.get("APR", 0.0) or 55200.0
        jul_b = monthly_basics.get("JUL", 0.0) or monthly_basics.get("AUG", 0.0)
        jan_b = monthly_basics.get("JAN", 0.0)

        extracted['basic'] = mar_b
        
        # SMART CPC PAY LEVEL AUTO-MATCHING
        determined_level, matching_levels = find_exact_or_nearest_level(mar_b)
        extracted['matching_levels'] = matching_levels
        extracted['pay_level'] = determined_level

        if jul_b and jul_b > mar_b:
            extracted['inc_month'] = '1ST JULY'
            extracted['inc_basic'] = jul_b
        elif jan_b and jan_b > mar_b:
            extracted['inc_month'] = '1ST JANUARY'
            extracted['inc_basic'] = jan_b
        else:
            extracted['inc_month'] = '1ST JULY'
            extracted['inc_basic'] = get_next_matrix_cell(determined_level, mar_b)

        r_da = get_clean_num(raw_clean, ["DA", "DEARNESS ALLOWANCE"])
        if r_da > 0: extracted['da'] = r_da
        r_hra = get_clean_num(raw_clean, ["HRA", "HOUSE RENT ALLOWANCE"])
        if r_hra > 0: extracted['hra'] = r_hra
        r_med = get_clean_num(raw_clean, ["MEDICAL"])
        if r_med > 0: extracted['medical'] = r_med
        r_gpf = get_clean_num(raw_clean, ["GPF", "NPS", "PRAN", "EPF"])
        if r_gpf > 0: extracted['gpf'] = r_gpf
        r_tds = get_clean_num(raw_clean, ["I.TAX", "ITAX", "1.TAX", "TDS"])
        if r_tds > 0: extracted['tds'] = r_tds

    except Exception:
        pass

    return extracted

# ================= DUAL TAX ENGINE WITH ANNUAL PTAP & FEBRUARY BALANCING =================
def compute_annual_tax_with_regime(records_11, regime="NEW REGIME", decl_data=None, manual_arrear_da=0.0, manual_arrear_pay=0.0, extra_tds=0.0, custom_rows=None):
    if decl_data is None:
        decl_data = {}
    if custom_rows is None:
        custom_rows = []
    
    tot_basic = sum(r['basic'] for r in records_11) + sum(r['basic'] for r in custom_rows)
    tot_da = sum(r['da'] for r in records_11) + sum(r['da'] for r in custom_rows)
    tot_hra = sum(r['hra'] for r in records_11) + sum(r['hra'] for r in custom_rows)
    tot_med = sum(r['medical'] for r in records_11) + sum(r['medical'] for r in custom_rows)
    tot_gpf = sum(r['gpf'] for r in records_11) + sum(r['gpf'] for r in custom_rows)
    tot_gis = sum(r['gis'] for r in records_11)
    
    tot_arrear_da = sum(r.get('arrear_da', 0) for r in records_11) + manual_arrear_da
    tot_arrear_pay = sum(r.get('arrear_pay', 0) for r in records_11) + manual_arrear_pay
    
    annual_gross_salary = tot_basic + tot_da + tot_hra + tot_med + tot_arrear_da + tot_arrear_pay
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
    
    tds_11_months = sum(r.get('tds', 0) for r in records_11) + sum(r.get('tds', 0) for r in custom_rows) + extra_tds
    feb_tds = max(0.0, total_tax_liability - tds_11_months)
    
    total_working_months = 11 + len(custom_rows) + 1
    total_ptax_paid_so_far = sum(r.get('ptax', 200) for r in records_11) + sum(r.get('ptax', 200) for r in custom_rows)
    max_annual_ptax = 2500.0 if annual_gross_salary > 1000000 else (200.0 * total_working_months)
    feb_ptax = max(0.0, max_annual_ptax - total_ptax_paid_so_far)
    
    jan_row = records_11[-1]
    feb_basic, feb_da, feb_hra, feb_med = jan_row['basic'], jan_row['da'], jan_row['hra'], jan_row['medical']
    feb_gross = feb_basic + feb_da + feb_hra + feb_med
    feb_net = feb_gross - (jan_row['gpf'] + jan_row['gis'] + feb_ptax + feb_tds)
    
    feb_row = {
        'month': 'FEBRUARY 2025', 'basic': feb_basic, 'da': feb_da, 'hra': feb_hra,
        'medical': feb_med, 'arrear_da': 0.0, 'arrear_pay': 0.0, 'gross': feb_gross,
        'gpf': jan_row['gpf'], 'gis': jan_row['gis'], 'ptax': feb_ptax, 'tds': feb_tds, 'net': feb_net
    }
    
    full_12 = list(records_11) + custom_rows + [feb_row]
    tax_summary = {
        'regime': regime, 'gross': annual_gross_salary, 'gross_total_income': gross_total_income,
        'std_ded': std_ded, 'chapter_vi_a': chapter_vi_a, 'taxable_income': taxable_income,
        'slab_details': slab_details, 'slab_tax': slab_tax, 'rebate_87a': rebate_87a,
        'cess': cess, 'relief_89': relief_89, 'total_tax': total_tax_liability,
        'tds_paid': tds_11_months + feb_tds, 'net_balance': total_tax_liability - (tds_11_months + feb_tds),
        'feb_tds': feb_tds, 'tot_arrear_da': tot_arrear_da, 'tot_arrear_pay': tot_arrear_pay,
        'ptax': max_annual_ptax
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
        msg['Subject'] = subject.upper()
        msg.attach(MIMEText(body.upper(), 'plain'))
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename.upper()}"')
        msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipient_email, msg.as_string())
        server.quit()
        return True
    except Exception:
        return False

# ================= DUAL ORIENTATION (PORTRAIT & LANDSCAPE) TEMPLATE =================
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
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(a) Section 80C (GPF, PPF, LIC, Tuition Fees, etc.)</td><td class="right">{{ "%.2f"|format(decl.sec80c) }}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(b) Section 80CCC (Pension Fund)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(c) Section 80CCD(1) (Employee Contribution to NPS)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(d) Section 80CCD(1B) (Additional NPS Deduction)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(e) Section 80D (Health Insurance Premium)</td><td class="right">{{ "%.2f"|format(decl.sec80d) }}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(f) Section 80E (Interest on Loan for Higher Education)</td><td class="right">{{ "%.2f"|format(decl.sec80e) }}</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(g) Section 80G (Donations to certain funds, etc.)</td><td class="right">0.00</td></tr>
    <tr><td>&nbsp;&nbsp;&nbsp;&nbsp;(h) Section 80TTA (Interest on Savings Bank Accounts)</td><td class="right">{{ "%.2f"|format(decl.sec80tta) }}</td></tr>
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
  
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 3: SCHEDULE OF INCOME TAX (PORTRAIT) -->
<div class="page-portrait">
  {% if is_trial %}<div class="watermark-layer-p">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}

  <div class="center title-main">{{ tax.regime }} के तहत</div>
  <div class="center title-sub">Schedule of Income - Tax</div>
  <div class="center title-main">आयकर की अनुसूची (चार प्रतियों में भर कर दें)</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 6px;">{{ emp.ay }}</div>

  <table class="no-border" style="margin-bottom: 6px;">
    <tr><td style="width: 25%;">करदाता का नाम</td><td>: <b>{{ emp.name }}</b></td></tr>
    <tr><td>पदनाम</td><td>: {{ emp.designation }}</td></tr>
    <tr><td>कार्यालय / विद्यालय का नाम</td><td>: {{ emp.office_name }}</td></tr>
    <tr><td>स्थायी लेखा संख्या (PAN)</td><td>: <b>{{ emp.pan }}</b></td></tr>
    {% if emp.gpf_no %}
    <tr><td>GPF / PRAN / PF संख्या</td><td>: {{ emp.gpf_no }}</td></tr>
    {% endif %}
  </table>

  <table class="border">
    <tr class="bg-gray bold">
      <th style="width: 6%;">क</th>
      <th style="width: 70%; text-align: left;">वेतन स्रोत से आय का विवरण:</th>
      <th style="width: 24%; text-align: right;">राशि (Rs.)</th>
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
      <th style="width: 6%;">ख</th>
      <th style="width: 70%; text-align: left;">आयकर की संगणना</th>
      <th style="width: 24%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>सकल वेतन एवं अन्य आय (Gross Total Income)</td><td class="right">{{ "%.2f"|format(tax.gross_total_income) }}</td></tr>
    <tr><td>02.</td><td>घटायें धारा 16 (ia) मानक कटौती (Standard Deduction)</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    {% if tax.regime == 'OLD REGIME' %}
    <tr><td>03.</td><td>घटायें अध्याय VI-A की कटौतियां (80C, 80D आदि)</td><td class="right">{{ "%.2f"|format(tax.chapter_vi_a) }}</td></tr>
    {% endif %}
    <tr class="bold"><td>04.</td><td>कर योग्य आय (Taxable Total Income)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr>
      <td>05.</td>
      <td colspan="2" style="padding: 4px 6px;">
        <b>रु० {{ "%.2f"|format(tax.taxable_income) }} पर देय आयकर (Tax Slabs Breakdown):</b><br>
        {% for s in tax.slab_details %}
        <span style="display:inline-block; width: 68%;">&nbsp;&nbsp;{{ s.label }}</span>
        <span style="display:inline-block; width: 30%; text-align: right;">{{ "%.2f"|format(s.amount) }}</span><br>
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
    <div style="margin-bottom: 8px;"><b>कोषागार:</b> {{ ddo.district }} ({{ ddo.state }}){% if ddo.address %} | <b>पता:</b> {{ ddo.address }}{% endif %}{% if ddo.city %}, {{ ddo.city }}{% endif %}{% if ddo.pincode %} - {{ ddo.pincode }}{% endif %}</div>
    <table class="no-border" style="margin-top: 20px;">
      <tr>
        <td style="width: 50%;">हस्ताक्षर करदाता: ____________________</td>
        <td style="width: 50%; text-align: right;">निकासी एवं व्ययन पदाधिकारी हस्ताक्षर एवं मुहर</td>
      </tr>
    </table>
  </div>
  
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

<!-- SECTION 4: MONTHLY SALARY LEDGER (LANDSCAPE) -->
<div class="page-landscape">
  {% if is_trial %}<div class="watermark-layer-l">TRIAL COPY — FOR VERIFICATION ONLY</div>{% endif %}

  <div class="center title-sub">मासिक वेतन एवं कटौतियों की विवरणी (Monthly Salary & Deduction Ledger)</div>
  <div class="center bold" style="font-size: 10px; margin-bottom: 8px;">{{ emp.name }} (PAN: {{ emp.pan }}) | {{ emp.office_name }}</div>

  <table class="border" style="font-size: 10px; margin-top: 6px;">
    <tr class="bg-gray center bold">
      <th style="width: 14%; padding: 5px;">माह</th>
      <th style="width: 8%; padding: 5px;">मूल वेतन</th>
      <th style="width: 8%; padding: 5px;">महंगाई</th>
      <th style="width: 8%; padding: 5px;">HRA</th>
      <th style="width: 6%; padding: 5px;">Med</th>
      <th style="width: 10%; padding: 5px;">Arrear / Madh</th>
      <th style="width: 9%; padding: 5px;">सकल (Gross)</th>
      <th style="width: 8%; padding: 5px;">GPF/NPS</th>
      <th style="width: 6%; padding: 5px;">GIS</th>
      <th style="width: 6%; padding: 5px;">PTax</th>
      <th style="width: 8%; padding: 5px;">TDS</th>
      <th style="width: 9%; padding: 5px;">शुद्ध (Net)</th>
    </tr>
    {% for r in records %}
    <tr>
      <td style="padding: 4px; font-weight: 600;">{{ r.month }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.basic) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.da) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.hra) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.medical) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.get('arrear_da', 0) + r.get('arrear_pay', 0)) }}</td>
      <td class="right bold" style="padding: 4px;">{{ "%.0f"|format(r.gross) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.gpf) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.gis) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.ptax) }}</td>
      <td class="right" style="padding: 4px;">{{ "%.0f"|format(r.tds) }}</td>
      <td class="right bold" style="padding: 4px;">{{ "%.0f"|format(r.net) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold bg-gray">
      <td style="padding: 5px;">कुल योग</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.basic) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.da) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.hra) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.medical) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.arrear) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.gross) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.gpf) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.gis) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.ptax) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.tds) }}</td>
      <td class="right" style="padding: 5px;">{{ "%.0f"|format(totals.net) }}</td>
    </tr>
  </table>

  <div class="sign-area" style="margin-top: 35px;">
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
  
  {% if is_trial %}
  <div class="pdf-footer-credit">DESIGNED & DEVELOPED BY @ NITIN MALLICK</div>
  {% endif %}
</div>

</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, full_records, tax_summary, deposits=None, decl_dict=None, is_trial=False):
    cleaned_records = []
    for r in full_records:
        b = float(r.get('basic', 0) or 0)
        d = float(r.get('da', 0) or 0)
        h = float(r.get('hra', 0) or 0)
        m = float(r.get('medical', 0) or 0)
        ada = float(r.get('arrear_da', 0) or 0)
        apa = float(r.get('arrear_pay', 0) or 0)
        g = float(r.get('gross', 0) or (b + d + h + m + ada + apa))
        gp = float(r.get('gpf', 0) or 0)
        gi = float(r.get('gis', 0) or 0)
        pt = float(r.get('ptax', 0) or 0)
        td = float(r.get('tds', 0) or 0)
        cleaned_records.append({
            'month': str(r.get('month', '')),
            'basic': b, 'da': d, 'hra': h, 'medical': m,
            'arrear_da': ada, 'arrear_pay': apa, 'gross': g,
            'gpf': gp, 'gis': gi, 'ptax': pt, 'tds': td,
            'net': float(r.get('net', 0) or (g - (gp + gi + pt + td)))
        })

    totals = {
        'basic': sum(r['basic'] for r in cleaned_records),
        'da': sum(r['da'] for r in cleaned_records),
        'hra': sum(r['hra'] for r in cleaned_records),
        'medical': sum(r['medical'] for r in cleaned_records),
        'arrear': sum(r['arrear_da'] + r['arrear_pay'] for r in cleaned_records),
        'gross': sum(r['gross'] for r in cleaned_records),
        'gpf': sum(r['gpf'] for r in cleaned_records),
        'gis': sum(r['gis'] for r in cleaned_records),
        'ptax': sum(r['ptax'] for r in cleaned_records),
        'tds': sum(r['tds'] for r in cleaned_records),
        'net': sum(r['net'] for r in cleaned_records),
        'q1_3_tds': sum(r['tds'] for r in cleaned_records[:11])
    }

    d_safe = {
        'sec80c': 0.0, 'sec80ccc': 0.0, 'sec80ccd': 0.0, 'sec80d': 0.0,
        'sec80dd': 0.0, 'sec80ddb': 0.0, 'sec80e': 0.0, 'sec80ee': 0.0,
        'sec80g': 0.0, 'sec80tta': 0.0, 'sec80u': 0.0, 'house_property_loss': 0.0,
        'bank_interest': 0.0, 'other_income': 0.0, 'relief_89': 0.0
    }
    if decl_dict:
        for k, v in decl_dict.items():
            try:
                d_safe[k] = float(v or 0)
            except Exception:
                d_safe[k] = 0.0

    tax_summary['ptax'] = totals['ptax']

    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=cleaned_records, tax=tax_summary,
        totals=totals, deposits=deposits or [], decl=d_safe, 
        today_date=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )
    return HTML(string=rendered).write_pdf()

# ================= SHARED GENERATOR SUITE =================
def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    st.markdown("#### 📄 Salary Slip Upload & Dynamic Auto-Fill")
    slip_up = st.file_uploader(
        "Upload Salary Slip (PDF) — District, Sector, Arrears & Back-dated Months auto-detect ho jayenge:", 
        type=["pdf"], 
        key=f"{prefix}_slip"
    )
    
    if slip_up:
        if f"{prefix}_last_uploaded" not in st.session_state or st.session_state[f"{prefix}_last_uploaded"] != slip_up.name:
            scanned = parse_slip_in_memory(slip_up)
            st.session_state[f"{prefix}_scanned"] = scanned
            st.session_state[f"{prefix}_last_uploaded"] = slip_up.name

            if scanned.get('pan'):
                st.session_state[f"{prefix}_pan_field"] = scanned['pan'].upper()
            if scanned.get('name'):
                st.session_state[f"{prefix}_vn"] = scanned['name'].upper()
            if scanned.get('designation'):
                st.session_state[f"{prefix}_vd"] = scanned['designation'].upper()
            if scanned.get('gpf_no'):
                st.session_state[f"{prefix}_vgpf_no"] = scanned['gpf_no'].upper()
            if scanned.get('pay_level'):
                st.session_state[f"{prefix}_lvl"] = scanned['pay_level'].upper()
            if scanned.get('basic', 0) > 0:
                st.session_state[f"{prefix}_bsc"] = int(scanned['basic'])
            if scanned.get('inc_month'):
                st.session_state[f"{prefix}_incm"] = scanned['inc_month'].upper()
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
            
            st.session_state[f"{prefix}_st"] = scanned.get('auto_state', 'JHARKHAND').upper()
            st.session_state[f"{prefix}_dt"] = scanned.get('auto_district', 'KHUNTI').upper()
            st.session_state[f"{prefix}_empt"] = scanned.get('employer_type', 'STATE GOVERNMENT').upper()
            st.session_state[f"{prefix}_pen"] = scanned.get('pension_type', 'OLD PENSION (GPF / OPS)').upper()

            st.session_state[f"{prefix}_arrear_da"] = float(scanned.get('arrear_da', 0))
            st.session_state[f"{prefix}_arrear_pay"] = float(scanned.get('arrear_pay', 0))
            st.session_state[f"{prefix}_arrear_tds"] = float(scanned.get('arrear_tds', 0))
            st.session_state[f"{prefix}_custom_rows"] = scanned.get('custom_arrear_rows', [])

            st.rerun()

    scanned = st.session_state.get(f"{prefix}_scanned", None)

    if scanned and scanned.get('pan'):
        with st.expander("📋 Extracted Slip Data Summary & Auto-Detection Inspection", expanded=True):
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Employee Name", (scanned.get('name') or "N/A").upper())
            r2.metric("PAN Number", (scanned.get('pan') or "N/A").upper())
            r3.metric("Auto District (via Block)", (scanned.get('auto_district') or "KHUNTI").upper())
            r4.metric("Employer Sector", (scanned.get('employer_type') or "STATE GOVERNMENT").upper())

            r5, r6, r7, r8 = st.columns(4)
            r5.metric("March Basic Pay", f"₹{scanned.get('basic', 0):,.0f}")
            r6.metric("Auto Pay Level & GP", (scanned.get('pay_level') or "LEVEL 7 (GP 4600)").upper())
            r7.metric("DA Arrear Total", f"₹{scanned.get('arrear_da', 0):,.0f}")
            r8.metric("Pay Arrear Total", f"₹{scanned.get('arrear_pay', 0):,.0f}")

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
            ["NORMAL (REGULAR CONTINUITY)", "TRANSFER (NEW SCHOOL / OFFICE)", "PROMOTION / MACP (NEW LEVEL)", "SUSPENSION / LWP"],
            key=f"{prefix}_status_sel"
        )
    with c_s2:
        regime_sel = st.selectbox(
            "Tax Assessment Regime:",
            ["NEW REGIME", "OLD REGIME"],
            key=f"{prefix}_regime_sel"
        )

    # State, District, Employment Sector & Department Hierarchy with 'Add New' capability
    c_l1, c_l2, c_l3, c_l4 = st.columns(4)
    
    states_list = get_creatable_list("master_states", "name")
    states_upper = [s.upper() for s in states_list]
    def_st_idx = states_upper.index(prof[6].upper()) if prof and prof[6] and prof[6].upper() in states_upper else (states_upper.index("JHARKHAND") if "JHARKHAND" in states_upper else 0)
    with c_l1:
        s_st_raw = st.selectbox("State", states_upper + ["➕ ADD NEW STATE"], index=def_st_idx, key=f"{prefix}_st")
        if s_st_raw == "➕ ADD NEW STATE":
            new_st = st.text_input("Type State Name", placeholder="e.g. BIHAR", key=f"{prefix}_new_st").upper().strip()
            if st.button("Lock State", key=f"{prefix}_btn_st"):
                if new_st:
                    add_creatable_item("master_states", {"name": new_st})
                    st.rerun()
            ch_state = new_st
        else: ch_state = s_st_raw

    dist_list = get_creatable_list("master_districts", "name", "state_name=?", (ch_state,))
    dist_upper = [d.upper() for d in dist_list]
    if not dist_upper and ch_state == "JHARKHAND":
        dist_upper = list(JHARKHAND_BLOCK_DISTRICT_MAP.keys())

    def_dt_idx = dist_upper.index(prof[7].upper()) if prof and prof[7] and prof[7].upper() in dist_upper else 0
    with c_l2:
        s_dt_raw = st.selectbox("District", dist_upper + ["➕ ADD NEW DISTRICT"], index=def_dt_idx if dist_upper else 0, key=f"{prefix}_dt")
        if s_dt_raw == "➕ ADD NEW DISTRICT":
            new_dt = st.text_input("Type District Name", placeholder="e.g. RANCHI", key=f"{prefix}_new_dt").upper().strip()
            if st.button("Lock District", key=f"{prefix}_btn_dt"):
                if new_dt:
                    add_creatable_item("master_districts", {"state_name": ch_state, "name": new_dt})
                    st.rerun()
            ch_dist = new_dt
        else: ch_dist = s_dt_raw

    with c_l3:
        empt_opts = ["STATE GOVERNMENT", "CENTRAL GOVERNMENT", "PRIVATE / CORPORATE"]
        def_empt_idx = empt_opts.index(prof[14].upper()) if prof and len(prof) > 14 and prof[14] and prof[14].upper() in empt_opts else 0
        s_empt = st.selectbox("Employment Sector", empt_opts, index=def_empt_idx, key=f"{prefix}_empt")

    dept_list = get_creatable_list("master_departments", "name")
    dept_upper = [dp.upper() for dp in dept_list]
    def_dp_idx = dept_upper.index(prof[8].upper()) if prof and prof[8] and prof[8].upper() in dept_upper else 0
    with c_l4:
        s_dp_raw = st.selectbox("Department", dept_upper + ["➕ ADD NEW DEPARTMENT"], index=def_dp_idx if dept_upper else 0, key=f"{prefix}_dp")
        if s_dp_raw == "➕ ADD NEW DEPARTMENT":
            new_dp = st.text_input("Type Dept Name", placeholder="e.g. HEALTH & FAMILY WELFARE", key=f"{prefix}_new_dp").upper().strip()
            if st.button("Lock Dept", key=f"{prefix}_btn_dp"):
                if new_dp:
                    add_creatable_item("master_departments", {"name": new_dp})
                    st.rerun()
            ch_dept = new_dp
        else: ch_dept = s_dp_raw

    # DDO Master Section with Safe Extraction
    st.markdown("##### 🏛️ DDO Center & Office Verification")
    conn = sqlite3.connect(DB_NAME)
    all_ddos = conn.cursor().execute("SELECT id, officer_name, tan, district, department, address, city, pincode FROM ddo_masters").fetchall()
    conn.close()

    ddo_tan_map = {d[2]: d for d in all_ddos}
    tan_input_list = ["--- SELECT OR ENTER NEW TAN ---"] + [f"{d[2]} - {d[1]} ({d[3]})" for d in all_ddos]
    
    sel_ddo_dropdown = st.selectbox("Select DDO by TAN or Register New", tan_input_list, key=f"{prefix}_ddo_dropdown")
    
    if sel_ddo_dropdown != "--- SELECT OR ENTER NEW TAN ---":
        selected_tan = sel_ddo_dropdown.split(" - ")[0]
        matched_ddo = ddo_tan_map.get(selected_tan)
        ch_ddo_id = matched_ddo[0]
        
        with st.expander("📝 Modify Existing DDO Center Details", expanded=False):
            with st.form(f"mod_ddo_form_{ch_ddo_id}"):
                m_off = st.text_input("Officer Incharge Name", value=matched_ddo[1], key=f"{prefix}_mod_off").upper()
                m_tan = st.text_input("TAN Number", value=matched_ddo[2], key=f"{prefix}_mod_tan").upper()
                m_add = st.text_input("Office Address", value=matched_ddo[5] if matched_ddo[5] else "", key=f"{prefix}_mod_add").upper()
                mc1, mc2 = st.columns(2)
                with mc1: m_city = st.text_input("City", value=matched_ddo[6] if len(matched_ddo)>6 and matched_ddo[6] else ch_dist, key=f"{prefix}_mod_city").upper()
                with mc2: m_pin = st.text_input("PIN Code", value=matched_ddo[7] if len(matched_ddo)>7 and matched_ddo[7] else "", key=f"{prefix}_mod_pin")

                if st.form_submit_button("Update DDO Details"):
                    conn = sqlite3.connect(DB_NAME)
                    conn.cursor().execute("UPDATE ddo_masters SET officer_name=?, tan=?, address=?, city=?, pincode=? WHERE id=?",
                                          (m_off, m_tan, m_add, m_city, m_pin, ch_ddo_id))
                    conn.commit()
                    conn.close()
                    st.success("DDO details updated successfully!")
                    st.rerun()
    else:
        st.info("➕ Register New DDO Center below:")
        with st.form(f"new_ddo_reg_form_{prefix}"):
            n_off = st.text_input("Officer Incharge Name *", placeholder="e.g. PRINCIPAL / INCHARGE").upper()
            n_fat = st.text_input("Father's Name (S/O)", placeholder="e.g. FATHER'S NAME").upper()
            n_tan = st.text_input("TAN Number *", placeholder="e.g. PTIK01234A").upper()
            n_add = st.text_input("Office Address", placeholder="e.g. HIGH SCHOOL CAMPUS").upper()
            nc1, nc2 = st.columns(2)
            with nc1: n_city = st.text_input("City", placeholder="e.g. KHUNTI").upper()
            with nc2: n_pin = st.text_input("PIN Code", placeholder="e.g. 835210")

            if st.form_submit_button("Save New DDO Center"):
                if n_off and n_tan:
                    conn = sqlite3.connect(DB_NAME)
                    conn.cursor().execute("INSERT OR IGNORE INTO ddo_masters (state, district, department, officer_name, father_name, tan, address, city, pincode) VALUES (?,?,?,?,?,?,?,?,?)",
                                          (ch_state.upper(), ch_dist.upper(), ch_dept.upper(), n_off, n_fat, n_tan, n_add, n_city, n_pin))
                    conn.commit()
                    conn.close()
                    st.success("New DDO saved successfully!")
                    st.rerun()
                else:
                    st.error("Please provide Officer Name and TAN Number.")
        ch_ddo_id = all_ddos[0][0] if all_ddos else 1

    off_list = get_creatable_list("master_offices", "name_and_address", "district=? AND department=?", (ch_dist, ch_dept))
    off_upper = [o.upper() for o in off_list]
    def_o_idx = off_upper.index(prof[9].upper()) if prof and prof[9] and prof[9].upper() in off_upper else 0
    s_of_raw = st.selectbox("Office / School Address", off_upper + ["➕ ADD NEW OFFICE ADDRESS"], index=def_o_idx if off_upper else 0, key=f"{prefix}_off")
    if s_of_raw == "➕ ADD NEW OFFICE ADDRESS":
        new_of = st.text_input("Full Address", placeholder="e.g. UPGRADED +2 HIGH SCHOOL...", key=f"{prefix}_new_of").upper().strip()
        if st.button("Lock Address", key=f"{prefix}_btn_of"):
            if new_of:
                add_creatable_item("master_offices", {"district": ch_dist, "department": ch_dept, "name_and_address": new_of})
                st.rerun()
        ch_office = new_of
    else: ch_office = s_of_raw

    # 7th CPC Matrix & Increment Level Progression
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    with c_m1: s_lvl = st.selectbox("7th CPC Pay Level (Grade Pay)", list(CPC_7TH_MATRIX.keys()), key=f"{prefix}_lvl")
    with c_m2: s_bsc = st.number_input("March Basic Pay", step=100, key=f"{prefix}_bsc")
    with c_m3: s_incm = st.selectbox("Increment Month", ["NONE", "1ST JULY", "1ST JANUARY"], key=f"{prefix}_incm")
    
    auto_next_cell = get_next_matrix_cell(s_lvl, s_bsc)
    with c_m4: 
        s_incb = st.number_input("Incremented Basic (7th CPC Matrix)", value=int(auto_next_cell), step=100, key=f"{prefix}_incb")

    default_pen_idx = 0 if s_empt == "STATE GOVERNMENT" else 1
    s_pen = st.radio("Pension Scheme", ["OLD PENSION (GPF / OPS)", "NPS (10% BASIC+DA)"], index=default_pen_idx, horizontal=True, key=f"{prefix}_pen")

    st.markdown("##### 🔍 Verification & Monthly Allowance Card (Mandatory: Email & Mobile)")
    with st.container(border=True):
        c_v1, c_v2, c_v3, c_v4 = st.columns(4)
        with c_v1:
            v_name = st.text_input("Full Name *", key=f"{prefix}_vn").upper()
            v_des = st.text_input("Designation", key=f"{prefix}_vd").upper()
        with c_v2:
            v_mob = st.text_input("Mobile No * (Compulsory)", value=prof[3] if prof else "", key=f"{prefix}_vm")
            v_eml = st.text_input("Email ID * (Compulsory for PDF Dispatch)", value=prof[4] if prof else "", key=f"{prefix}_ve")
        with c_v3:
            v_gpf_no = st.text_input("GPF / PRAN / PF Number (Employee Ref No)", key=f"{prefix}_vgpf_no").upper()
            v_da = st.number_input("Monthly DA", step=100, key=f"{prefix}_vda")
        with c_v4:
            v_hra = st.number_input("Monthly HRA", step=100, key=f"{prefix}_vhra")
            v_gpf = st.number_input("Monthly GPF / NPS / PF", step=100, key=f"{prefix}_vgpf")
            v_tds = st.number_input("Monthly TDS (Mar-Jan)", step=500, key=f"{prefix}_vtds")

    # Dedicated Arrear Section & Custom Back-dated Rows
    st.markdown("##### 💰 Arrear Allowances & Back-Dated Salary Entries")
    with st.container(border=True):
        c_ar1, c_ar2, c_ar3 = st.columns(3)
        with c_ar1:
            arr_da = st.number_input("DA Arrear Total (₹)", step=500.0, key=f"{prefix}_arrear_da")
        with c_ar2:
            arr_pay = st.number_input("Pay / Other Arrears (₹)", step=1000.0, key=f"{prefix}_arrear_pay")
        with c_ar3:
            arr_tds = st.number_input("TDS Deducted in Arrears (₹)", step=500.0, key=f"{prefix}_arrear_tds")
        
        custom_rows = st.session_state.get(f"{prefix}_custom_rows", [])
        if custom_rows:
            st.info(f"📌 Detected {len(custom_rows)} Back-Dated Salary / Arrear Month(s) from Slip.")
            for cr in custom_rows:
                st.text(f"• Month: {cr['month']} | Basic: ₹{cr['basic']} | DA: ₹{cr['da']} | HRA: ₹{cr['hra']}")

    decl_data = {}
    if regime_sel == "OLD REGIME":
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
        cb = s_incb if (s_incm == "1ST JULY" and idx >= 4) or (s_incm == "1ST JANUARY" and idx >= 10) else s_bsc
        cg = cb + v_da + v_hra + 1000.0
        recs_11.append({
            'month': m, 'basic': cb, 'da': v_da, 'hra': v_hra, 'medical': 1000.0,
            'arrear_da': 0.0, 'arrear_pay': 0.0, 'gross': cg, 'gpf': v_gpf,
            'gis': 60.0, 'ptax': 200.0, 'tds': float(v_tds), 'net': cg - (v_gpf + 260 + v_tds)
        })

    full_12, tax_calc = compute_annual_tax_with_regime(
        recs_11, regime=regime_sel, decl_data=decl_data, 
        manual_arrear_da=arr_da, manual_arrear_pay=arr_pay, extra_tds=arr_tds, custom_rows=custom_rows
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
                    'state': (ddo_row_preview[1] or '').upper(), 
                    'district': (ddo_row_preview[2] or '').upper(), 
                    'department': (ddo_row_preview[3] or '').upper(), 
                    'officer_name': (ddo_row_preview[4] or '').upper(), 
                    'father_name': (ddo_row_preview[5] or '').upper(), 
                    'tan': (ddo_row_preview[6] or '').upper(), 
                    'address': (ddo_row_preview[7] or '').upper() if len(ddo_row_preview) > 7 and ddo_row_preview[7] else '', 
                    'city': (ddo_row_preview[8] or '').upper() if len(ddo_row_preview) > 8 and ddo_row_preview[8] else (ddo_row_preview[2] or '').upper(), 
                    'pincode': str(ddo_row_preview[9]) if len(ddo_row_preview) > 9 and ddo_row_preview[9] else ''
                }
            else:
                ddo_d_trial = {
                    'state': ch_state.upper(), 'district': ch_dist.upper(), 'department': ch_dept.upper(),
                    'officer_name': "DDO INCHARGE", 'father_name': "OFFICER FATHER", 
                    'tan': "PTIK01234A", 'address': ch_office.upper(), 'city': ch_dist.upper(), 'pincode': "835210"
                }

            emp_d_trial = {'ay': GLOBAL_AY, 'pan': pan_in.upper(), 'name': v_name.upper(), 'designation': v_des.upper(), 'office_name': ch_office.upper(), 'gpf_no': v_gpf_no.upper()}
            trial_pdf_data = generate_pdf_bundle(ddo_d_trial, emp_d_trial, full_12, tax_calc, decl_dict=decl_data, is_trial=True)
            
            st.success("✅ Trial PDF generated successfully! Niche diye button se download karein:")
            st.download_button(
                label="📄 Click here to Download TRIAL PDF Now",
                data=trial_pdf_data,
                file_name=f"TRIAL_{pan_in}_{GLOBAL_AY}.pdf".upper(),
                mime="application/pdf",
                key=f"{prefix}_trial_dl_btn",
                use_container_width=True
            )

    st.markdown("---")
    st.markdown("##### 🚀 Official Submission & Final Unlocked Generation")

    if is_admin_mode:
        if st.button("🚀 Save & Generate Official Unlocked PDF Bundle", use_container_width=True, key=f"{prefix}_adm_btn"):
            if not (pan_in and v_name and ch_office and ch_ddo_id and v_mob and v_eml):
                st.error("Please fill PAN, Name, Mobile, Email, DDO and Office!")
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                today_str = date.today().strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute('''INSERT INTO employee_master_profiles (
                    pan, name, designation, mobile, email, gpf_no, last_state, last_district, last_dept,
                    last_office, last_ddo_id, last_pay_level, last_basic_pay, last_inc_month,
                    employer_type, pension_type, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(pan) DO UPDATE SET
                        name=excluded.name, mobile=excluded.mobile, email=excluded.email, last_office=excluded.last_office, last_basic_pay=excluded.last_basic_pay, gpf_no=excluded.gpf_no, employer_type=excluded.employer_type''',
                    (pan_in.upper(), v_name.upper(), v_des.upper(), v_mob, v_eml, v_gpf_no.upper(), ch_state.upper(), ch_dist.upper(), ch_dept.upper(), ch_office.upper(), ch_ddo_id,
                     s_lvl.upper(), s_bsc, s_incm.upper(), s_empt.upper(), "GPF" if "GPF" in s_pen else "NPS", now_str))

                conn.cursor().execute('''INSERT INTO employee_yearly_records (
                    ay, ddo_id, pan, name, designation, office_name, service_status, pay_level,
                    employer_type, pension_type, tax_regime, start_basic, inc_month, inc_basic, default_da, default_hra,
                    default_med, default_gpf, default_gis, default_ptax, monthly_tds, mobile,
                    email, payment_status, payment_mode, utr_no, amount_paid, created_at, created_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ay, pan) DO UPDATE SET payment_status='APPROVED', tax_regime=excluded.tax_regime, employer_type=excluded.employer_type, mobile=excluded.mobile, email=excluded.email''',
                    (GLOBAL_AY, ch_ddo_id, pan_in.upper(), v_name.upper(), v_des.upper(), ch_office.upper(), status_sel.upper(), s_lvl.upper(),
                     s_empt.upper(), "GPF" if "GPF" in s_pen else "NPS", regime_sel.upper(), s_bsc, s_incm.upper(), s_incb, v_da, v_hra, 1000.0,
                     v_gpf, 60.0, 200.0, v_tds, v_mob, v_eml, 'APPROVED', 'ADMIN_DIRECT', 'ADMIN_AUTH', 0.0, now_str, today_str))
                
                y_id = conn.cursor().execute("SELECT id FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in.upper())).fetchone()[0]

                conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_id,))
                for r in full_12:
                    conn.cursor().execute('''INSERT INTO monthly_salary_ledgers (
                        yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay,
                        gross, gpf, gis, ptax, tds, net, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (y_id, r['month'].upper(), r['basic'], r['da'], r['hra'], r['medical'], r['arrear_da'], r['arrear_pay'], r['gross'], r['gpf'], r['gis'], r['ptax'], r['tds'], r['net'], 'SYSTEM AUTO'))
                
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
                    'state': (ddo_r[1] or '').upper(), 'district': (ddo_r[2] or '').upper(), 'department': (ddo_r[3] or '').upper(), 
                    'officer_name': (ddo_r[4] or '').upper(), 'father_name': (ddo_r[5] or '').upper(), 'tan': (ddo_r[6] or '').upper(), 
                    'address': (ddo_r[7] or '').upper() if len(ddo_r) > 7 and ddo_r[7] else '', 'city': (ddo_r[8] or '').upper() if len(ddo_r) > 8 and ddo_r[8] else (ddo_r[2] or '').upper(), 'pincode': str(ddo_r[9]) if len(ddo_r) > 9 and ddo_r[9] else ''
                }
                emp_d = {'ay': GLOBAL_AY, 'pan': pan_in.upper(), 'name': v_name.upper(), 'designation': v_des.upper(), 'office_name': ch_office.upper(), 'gpf_no': v_gpf_no.upper()}
                pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, full_12, tax_calc, deps, decl_data, is_trial=False)

                if v_eml:
                    send_email_with_pdf(v_eml, f"OFFICIAL FORM 16 & SCHEDULE - {GLOBAL_AY}", "Attached is your official Form 16 bundle.", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf".upper())
                st.download_button("📥 Download Official 4-Page PDF Now", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf".upper(), "application/pdf", use_container_width=True)
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
                u_utr = st.text_input("Enter 12-Digit UTR Number *", key=f"{prefix}_utr").upper()
            btn_t = st.button("🚀 Submit Request for Official Unlocked Copy", use_container_width=True, key=f"{prefix}_t_btn")
            u_mode = "CASH" if "Cash" in p_mode else "UPI"
            fee_amt = c_fee

        if btn_t:
            if not (pan_in and v_name and v_mob and v_eml and ch_office and ch_ddo_id):
                st.error("Please fill PAN, Name, Mobile, Email, DDO and Office!")
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                today_str = date.today().strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute('''INSERT INTO employee_master_profiles (
                    pan, name, designation, mobile, email, gpf_no, last_state, last_district, last_dept,
                    last_office, last_ddo_id, last_pay_level, last_basic_pay, last_inc_month,
                    employer_type, pension_type, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(pan) DO UPDATE SET
                        name=excluded.name, mobile=excluded.mobile, email=excluded.email, last_office=excluded.last_office, last_basic_pay=excluded.last_basic_pay, gpf_no=excluded.gpf_no, employer_type=excluded.employer_type''',
                    (pan_in.upper(), v_name.upper(), v_des.upper(), v_mob, v_eml, v_gpf_no.upper(), ch_state.upper(), ch_dist.upper(), ch_dept.upper(), ch_office.upper(), ch_ddo_id,
                     s_lvl.upper(), s_bsc, s_incm.upper(), s_empt.upper(), "GPF" if "GPF" in s_pen else "NPS", now_str))

                pay_stat = "APPROVED" if is_wl else "PENDING"
                conn.cursor().execute('''INSERT INTO employee_yearly_records (
                    ay, ddo_id, pan, name, designation, office_name, service_status, pay_level,
                    employer_type, pension_type, tax_regime, start_basic, inc_month, inc_basic, default_da, default_hra,
                    default_med, default_gpf, default_gis, default_ptax, monthly_tds, mobile,
                    email, payment_status, payment_mode, utr_no, amount_paid, created_at, created_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ay, pan) DO UPDATE SET payment_status=excluded.payment_status, tax_regime=excluded.tax_regime, employer_type=excluded.employer_type, mobile=excluded.mobile, email=excluded.email''',
                    (GLOBAL_AY, ch_ddo_id, pan_in.upper(), v_name.upper(), v_des.upper(), ch_office.office_name if 'office_name' in locals() else ch_office, status_sel.upper(), s_lvl.upper(),
                     s_empt.upper(), "GPF" if "GPF" in s_pen else "NPS", regime_sel.upper(), s_bsc, s_incm.upper(), s_incb, v_da, v_hra, 1000.0,
                     v_gpf, 60.0, 200.0, v_tds, v_mob, v_eml, pay_stat, u_mode, u_utr, fee_amt, now_str, today_str))
                
                y_id = conn.cursor().execute("SELECT id FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in.upper())).fetchone()[0]

                conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_id,))
                for r in full_12:
                    conn.cursor().execute('''INSERT INTO monthly_salary_ledgers (
                        yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay,
                        gross, gpf, gis, ptax, tds, net, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (y_id, r['month'].upper(), r['basic'], r['da'], r['hra'], r['medical'], r['arrear_da'], r['arrear_pay'], r['gross'], r['gpf'], r['gis'], r['ptax'], r['tds'], r['net'], 'SELF-SERVICE SUBMISSION'))
                
                conn.cursor().execute("DELETE FROM employee_tax_declarations WHERE yearly_record_id=?", (y_id,))
                conn.cursor().execute('''INSERT INTO employee_tax_declarations (
                    yearly_record_id, sec80c, sec80d, sec80e, sec80tta, house_property_loss, bank_interest, relief_89, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (y_id, decl_data.get('sec80c',0), decl_data.get('sec80d',0), decl_data.get('sec80e',0), decl_data.get('sec80tta',0),
                     decl_data.get('house_property_loss',0), decl_data.get('bank_interest',0), decl_data.get('relief_89',0), now_str))

                conn.commit()
                conn.close()
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
                    'state': (ddo_row[1] or '').upper(), 'district': (ddo_row[2] or '').upper(), 'department': (ddo_row[3] or '').upper(), 
                    'officer_name': (ddo_row[4] or '').upper(), 'father_name': (ddo_row[5] or '').upper(), 'tan': (ddo_row[6] or '').upper(), 
                    'address': (ddo_row[7] or '').upper() if len(ddo_row) > 7 and ddo_row[7] else '', 'city': (ddo_row[8] or '').upper() if len(ddo_row) > 8 and ddo_row[8] else (ddo_row[2] or '').upper(), 'pincode': str(ddo_row[9]) if len(ddo_row) > 9 and ddo_row[9] else ''
                }
                emp_d = {'ay': rd_ay, 'pan': rd_pan.upper(), 'name': y_rec[4].upper(), 'designation': y_rec[5].upper(), 'office_name': y_rec[6].upper(), 'gpf_no': prof_row[0].upper() if prof_row and prof_row[0] else ""}
                pdf_data = generate_pdf_bundle(ddo_d, emp_d, full_12_rd, tax_rd, deposits, d_dict, is_trial=False)

                st.success(f"Verified Record Found: **{y_rec[4]}** | Office: {y_rec[6]}")
                col_dla, col_dlb = st.columns(2)
                with col_dla:
                    st.download_button("📥 Download Official 4-Page PDF Bundle", pdf_data, f"{rd_pan}_{rd_ay}.pdf".upper(), "application/pdf", use_container_width=True)
                with col_dlb:
                    if y_rec[21] and st.button("📩 Re-Send to Registered Email"):
                        sent = send_email_with_pdf(y_rec[21], f"OFFICIAL FORM 16 - {rd_ay}", "Attached is your official Form 16.", pdf_data, f"{rd_pan}_{rd_ay}.pdf".upper())
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
                        file_name=f"Audit_Report_{filter_from}_to_{filter_to}.xlsx".upper(),
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
                                ed_name = st.text_input("Name", value=u_name, key=f"ed_n_{u_id}").upper()
                                ed_pan = st.text_input("PAN", value=u_pan, key=f"ed_p_{u_id}").upper()
                            with ce2:
                                ed_des = st.text_input("Designation", value=u_des, key=f"ed_d_{u_id}").upper()
                                ed_bsc = st.number_input("Basic Pay", value=int(u_bsc), key=f"ed_b_{u_id}")
                            with ce3:
                                ed_stat = st.selectbox("Status", ["APPROVED", "PENDING", "REJECTED"], index=["APPROVED", "PENDING", "REJECTED"].index(u_stat) if u_stat in ["APPROVED", "PENDING", "REJECTED"] else 0, key=f"ed_s_{u_id}")
                                ed_amt = st.number_input("Amount Paid", value=int(u_amt), key=f"ed_a_{u_id}")
                            
                            c_btn_a, c_btn_d = st.columns([1, 1])
                            with c_btn_a:
                                if st.form_submit_button("💾 Save Changes"):
                                    conn = sqlite3.connect(DB_NAME)
                                    conn.cursor().execute("UPDATE employee_yearly_records SET name=?, pan=?, designation=?, start_basic=?, payment_status=?, amount_paid=? WHERE id=?",
                                                          (ed_name.upper(), ed_pan.upper(), ed_des.upper(), ed_bsc, ed_stat, ed_amt, u_id))
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
                                    'state': (ddo_row[1] or '').upper(), 'district': (ddo_row[2] or '').upper(), 'department': (ddo_row[3] or '').upper(), 
                                    'officer_name': (ddo_row[4] or '').upper(), 'father_name': (ddo_row[5] or '').upper(), 'tan': (ddo_row[6] or '').upper(), 
                                    'address': (ddo_row[7] or '').upper() if len(ddo_row) > 7 and ddo_row[7] else '', 'city': (ddo_row[8] or '').upper() if len(ddo_row) > 8 and ddo_row[8] else (ddo_row[2] or '').upper(), 'pincode': str(ddo_row[9]) if len(ddo_row) > 9 and ddo_row[9] else ''
                                }
                                emp_d = {'ay': GLOBAL_AY, 'pan': r[3].upper(), 'name': r[4].upper(), 'designation': r[5].upper(), 'office_name': r[6].upper(), 'gpf_no': prof_row[0].upper() if prof_row and prof_row[0] else ""}
                                pdf_data = generate_pdf_bundle(ddo_d, emp_d, full_12_adm, tax_adm, deps, d_dict, is_trial=False)

                                st.download_button(
                                    label="📥 Download PDF",
                                    data=pdf_data,
                                    file_name=f"{r[3]}_{GLOBAL_AY}.pdf".upper(),
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
                        with cdp1: dep_qtr = st.selectbox("Quarter", ["Q1 (APR-JUN)", "Q2 (JUL-SEP)", "Q3 (OCT-DEC)", "Q4 (JAN-MAR)"])
                        with cdp2: dep_month = st.selectbox("Month", JHARKHAND_MONTHS)
                        with cdp3: dep_amt = st.number_input("TDS Amount Deposited (₹)", min_value=0.0, step=500.0)
                        with cdp4: dep_date = st.date_input("Deposit Date", date.today())

                        cdp5, cdp6, cdp7 = st.columns(3)
                        with cdp5: dep_mode = st.selectbox("Mode", ["BOOK ADJUSTMENT (TREASURY)", "CHALLAN (OLTAS)"])
                        with cdp6: dep_bsr = st.text_input("BSR Code / BIN", placeholder="e.g. 0510304").upper()
                        with cdp7: dep_challan = st.text_input("Challan Serial / DDO Serial No", placeholder="e.g. 00124").upper()

                        if st.form_submit_button("Record Statutory Deposit"):
                            conn = sqlite3.connect(DB_NAME)
                            conn.cursor().execute('''INSERT INTO tds_deposits (
                                yearly_record_id, quarter, month_name, amount, deposit_date, mode, bsr_code, challan_serial)
                                VALUES (?,?,?,?,?,?,?,?)''',
                                (sel_y_id, dep_qtr, dep_month, dep_amt, dep_date.strftime("%Y-%m-%d"), dep_mode.upper(), dep_bsr.upper(), dep_challan.upper()))
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
                        a_off = st.text_input("Officer Incharge Name", placeholder="e.g. PRINCIPAL / INCHARGE").upper()
                        a_fat = st.text_input("Father's Name (S/O)", placeholder="e.g. FATHER'S NAME").upper()
                        a_tan = st.text_input("TAN Number", placeholder="e.g. PTIK01234A").upper()
                        a_add = st.text_input("Office Address", placeholder="e.g. SEAL DEPARTMENT GOVT. OF JHARKHAND").upper()
                        ac_c1, ac_c2 = st.columns(2)
                        with ac_c1: a_city = st.text_input("City", placeholder="e.g. KHUNTI").upper()
                        with ac_c2: a_pin = st.text_input("PIN Code", placeholder="e.g. 835210")

                        if st.form_submit_button("Save DDO"):
                            conn = sqlite3.connect(DB_NAME)
                            conn.cursor().execute("INSERT INTO ddo_masters (state, district, department, officer_name, father_name, tan, address, city, pincode) VALUES (?,?,?,?,?,?,?,?,?)",
                                                  (a_st.upper(), a_dt.upper(), a_dp.upper(), a_off.upper(), a_fat.upper(), a_tan.upper(), a_add.upper(), a_city.upper(), a_pin))
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
                    new_p = st.text_input("Admin Password", type="password", value=get_setting('admin_password', '19052027def@admin'))
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
                    pans_txt = st.text_area("Whitelisted PANs (Comma-Separated)", value=get_setting('whitelisted_pans', ''), height=120).upper()
                    if st.button("Save Whitelist"):
                        set_setting('whitelisted_pans', pans_txt)
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
  🏛️ <b>KOSH-TAX</b> | COMPREHENSIVE TDS & FORM 16 MANAGEMENT PORTAL<br>
  <span style="color: #aaa;">DESIGNED & DEVELOPED BY NITIN</span>
</div>
""", unsafe_allow_html=True)

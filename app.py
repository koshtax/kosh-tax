import streamlit as st
import sqlite3
import openpyxl
from jinja2 import Template
from weasyprint import HTML
import io
import re
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime, date
from pypdf import PdfReader

st.set_page_config(
    page_title="TDS & Form 16 Enterprise Portal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "tds_enterprise_master.sqlite"

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
        tan TEXT UNIQUE NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS employee_master_profiles (
        pan TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        designation TEXT NOT NULL,
        mobile TEXT,
        email TEXT,
        last_state TEXT,
        last_district TEXT,
        last_dept TEXT,
        last_office TEXT,
        last_ddo_id INTEGER,
        last_pay_level TEXT,
        last_basic_pay REAL,
        last_inc_month TEXT,
        pension_type TEXT DEFAULT 'NPS',
        voluntary_gpf REAL DEFAULT 0,
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
        pension_type TEXT DEFAULT 'NPS',
        start_basic REAL DEFAULT 0,
        inc_month TEXT DEFAULT 'NONE',
        inc_basic REAL DEFAULT 0,
        default_da REAL DEFAULT 0,
        default_hra REAL DEFAULT 0,
        default_med REAL DEFAULT 500,
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
        FOREIGN KEY (yearly_record_id) REFERENCES employee_yearly_records(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('admin_username', '__nit@def@admin26__')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('admin_password', '19052027def@admin')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('form_fee', '100')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('upi_id', 'mallick.nitin@okaxis')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('whitelisted_pans', '')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('smtp_email', '')")
    c.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('smtp_password', '')")

    c.execute("SELECT COUNT(*) FROM master_states")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO master_states (name) VALUES ('JHARKHAND'), ('BIHAR'), ('WEST BENGAL'), ('UTTAR PRADESH')")
        c.executemany("INSERT INTO master_districts (state_name, name) VALUES (?,?)", [
            ('JHARKHAND', 'KHUNTI'), ('JHARKHAND', 'RANCHI'), ('JHARKHAND', 'GUMLA'), ('JHARKHAND', 'SIMDEGA'),
            ('BIHAR', 'PATNA'), ('BIHAR', 'GAYA'), ('BIHAR', 'MUZAFFARPUR')
        ])
        c.executemany("INSERT INTO master_departments (name) VALUES (?)", [
            ('SCHOOL EDUCATION & LITERACY',), ('HEALTH & FAMILY WELFARE',), ('RURAL DEVELOPMENT',), ('REVENUE & LAND REFORMS',)
        ])
        c.execute("INSERT INTO master_offices (district, department, name_and_address) VALUES ('KHUNTI', 'SCHOOL EDUCATION & LITERACY', 'Utkramit +2 High School, Tubil, Arki, Khunti')")

    conn.commit()
    conn.close()

init_db()

PAY_MATRIX = {
    "Level 1": [18000, 18500, 19100, 19700, 20300, 20900, 21500, 22100, 22800, 23500],
    "Level 2": [19900, 20500, 21100, 21700, 22400, 23100, 23800, 24500, 25200, 26000],
    "Level 4": [25500, 26300, 27100, 27900, 28700, 29600, 30500, 31400, 32300, 33300],
    "Level 5": [29200, 30100, 31000, 31900, 32900, 33900, 34900, 35900, 37000, 38100],
    "Level 6": [35400, 36500, 37600, 38700, 39900, 41100, 42300, 43600, 44900, 46200],
    "Level 7": [44900, 46200, 47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600],
    "Level 8": [47600, 49000, 50500, 52000, 53600, 55200, 56900, 58600, 60400, 62200],
    "Level 9": [53100, 54700, 56300, 58000, 59700, 61500, 63300, 65200, 67200, 69200],
    "Level 10": [56100, 57800, 59500, 61300, 63100, 65000, 67000, 69000, 71100, 73200]
}

REGULAR_MONTHS = [
    "March 2025", "April 2025", "May 2025", "June 2025", 
    "July 2025", "August 2025", "September 2025", "October 2025", 
    "November 2025", "December 2025", "January 2026", "February 2026"
]

AY_OPTIONS = ["AY 2026-27 (FY 2025-26)", "AY 2025-26 (FY 2024-25)"]

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

def compute_allowances(basic, pension_type="NPS", voluntary_gpf=0.0, hra_pct=9.0):
    da_amount = round(basic * 0.53)
    hra_amount = round(basic * (hra_pct / 100))
    pension_ded = round((basic + da_amount) * 0.10) if pension_type == "NPS" else (voluntary_gpf if voluntary_gpf > 0 else round(basic * 0.10))
    return {'da': da_amount, 'hra': hra_amount, 'med': 500.0, 'gpf_nps': pension_ded, 'gis': 60.0, 'ptax': 200.0}

def get_next_matrix_cell(level, current_basic):
    if level in PAY_MATRIX:
        cells = PAY_MATRIX[level]
        for idx, cell in enumerate(cells):
            if current_basic <= cell and idx + 1 < len(cells):
                return cells[idx + 1]
    return round((current_basic * 1.03) / 100) * 100

def parse_slip_in_memory(uploaded_file):
    extracted = {'basic': 49000.0, 'da': 0.0, 'hra': 0.0, 'med': 500.0, 'gpf': 0.0, 'pan': '', 'name': '', 'designation': '+2 Teacher'}
    try:
        reader = PdfReader(uploaded_file)
        full_text = "".join([page.extract_text() or "" for page in reader.pages])
        pan_match = re.search(r'[A-Z]{5}[0-9]{4}[A-Z]{1}', full_text)
        if pan_match: extracted['pan'] = pan_match.group(0)
        basic_match = re.search(r'(?:BASIC|Basic Pay|मूल वेतन)\s*[:=-]?\s*([0-9,]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)
        if basic_match: extracted['basic'] = float(basic_match.group(1).replace(',', ''))
        da_match = re.search(r'(?:D\.?A\.?|Dearness Allowance|महंगाई)\s*[:=-]?\s*([0-9,]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)
        if da_match: extracted['da'] = float(da_match.group(1).replace(',', ''))
        hra_match = re.search(r'(?:H\.?R\.?A\.?|House Rent)\s*[:=-]?\s*([0-9,]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)
        if hra_match: extracted['hra'] = float(hra_match.group(1).replace(',', ''))
        gpf_match = re.search(r'(?:GPF|NPS|Pran)\s*[:=-]?\s*([0-9,]+(?:\.[0-9]+)?)', full_text, re.IGNORECASE)
        if gpf_match: extracted['gpf'] = float(gpf_match.group(1).replace(',', ''))
        name_match = re.search(r'(?:Name|Employee Name|नाम)\s*[:=-]?\s*([A-Za-z\s]+?)(?=\n|PAN|Designation|$)', full_text, re.IGNORECASE)
        if name_match:
            cand = name_match.group(1).strip()
            if len(cand) > 3 and not any(c.isdigit() for c in cand): extracted['name'] = cand
    except Exception:
        pass
    if extracted['da'] == 0: extracted['da'] = round(extracted['basic'] * 0.53)
    if extracted['hra'] == 0: extracted['hra'] = round(extracted['basic'] * 0.09)
    if extracted['gpf'] == 0: extracted['gpf'] = round(extracted['basic'] * 0.10)
    return extracted

def compute_annual_tax_feb_balancing(records_11, manual_arrear_da=0.0, manual_arrear_pay=0.0):
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
    
    annual_gross = tot_basic + tot_da + tot_hra + tot_med + tot_arrear_da + tot_arrear_pay
    std_ded = 75000.0
    taxable_income = round(max(0.0, annual_gross - std_ded), -1)
    
    slabs = [
        (0, 400000, 0.0, "₹0-₹4 Lakh: Nil"),
        (400000, 800000, 0.05, "4 Lakh- 8 Lakh: 5%"),
        (800000, 1200000, 0.10, "8 Lakh-12 Lakh: 10%"),
        (1200000, 1600000, 0.15, "12 Lakh-16 Lakh: 15%"),
        (1600000, 2000000, 0.20, "16 Lakh-20 Lakh: 20%"),
        (2000000, 2400000, 0.25, "20 Lakh-24 Lakh: 25%"),
        (2400000, None, 0.30, "Above 24 Lakh: 30%")
    ]
    slab_details, slab_tax = [], 0.0
    for s_from, s_to, rate, label in slabs:
        amt = 0.0
        if taxable_income > s_from:
            upper = taxable_income if s_to is None else min(taxable_income, s_to)
            amt = (upper - s_from) * rate
            slab_tax += amt
        slab_details.append({"label": label, "amount": amt})
        
    rebate_87a = min(slab_tax, 60000.0) if taxable_income <= 1200000.0 else 0.0
    net_tax = max(0.0, slab_tax - rebate_87a)
    cess = round(net_tax * 0.04)
    total_tax_liability = net_tax + cess
    
    tds_11_months = sum(r.get('tds', 0) for r in records_11)
    feb_tds = max(0.0, total_tax_liability - tds_11_months)
    feb_net = feb_gross - (feb_gpf + feb_gis + feb_ptax + feb_tds)
    
    feb_row = {
        'month': 'February 2026', 'basic': feb_basic, 'da': feb_da, 'hra': feb_hra,
        'medical': feb_med, 'arrear_da': 0.0, 'arrear_pay': 0.0, 'gross': feb_gross,
        'gpf': feb_gpf, 'gis': feb_gis, 'ptax': feb_ptax, 'tds': feb_tds, 'net': feb_net
    }
    
    full_12 = list(records_11) + [feb_row]
    tax_summary = {
        'gross': annual_gross, 'std_ded': std_ded, 'taxable_income': taxable_income,
        'slab_details': slab_details, 'slab_tax': slab_tax, 'rebate_87a': rebate_87a,
        'cess': cess, 'total_tax': total_tax_liability, 'tds_paid': tds_11_months + feb_tds,
        'net_balance': total_tax_liability - (tds_11_months + feb_tds), 'feb_tds': feb_tds,
        'tot_arrear_da': tot_arrear_da, 'tot_arrear_pay': tot_arrear_pay
    }
    return full_12, tax_summary

def send_email_with_pdf(recipient_email, subject, body, pdf_bytes, filename):
    smtp_user = get_setting('smtp_email', '')
    smtp_pass = get_setting('smtp_password', '')
    if not (smtp_user and smtp_pass and recipient_email): return False
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

# ================= HTML MASTER 4-PAGE TEMPLATE =================
HTML_MASTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page { size: A4 portrait; margin: 8mm 10mm 8mm 10mm; }
  * { box-sizing: border-box; -webkit-print-color-adjust: exact; }
  body { font-family: 'Nirmala UI', 'Mangal', 'Arial', sans-serif; font-size: 10px; color: #000; line-height: 1.15; margin: 0; padding: 0; }
  .sheet-page { height: 275mm; max-height: 275mm; position: relative; page-break-after: always; page-break-inside: avoid; overflow: hidden; }
  .sheet-page:last-child { page-break-after: auto; }
  .center { text-align: center; } .right { text-align: right; } .bold { font-weight: bold; }
  .title-1 { font-size: 11px; font-weight: bold; line-height: 1.2; }
  .title-2 { font-size: 12px; font-weight: bold; line-height: 1.2; }
  table { width: 100%; border-collapse: collapse; margin-top: 3px; margin-bottom: 3px; }
  table.border, table.border th, table.border td { border: 0.8px solid #000; }
  th, td { padding: 2.5px 4px; vertical-align: middle; }
  .no-border td { border: none !important; padding: 1.5px 2px; }
  .bg-gray { background-color: #f2f2f2 !important; }
  .sign-area { position: absolute; bottom: 5mm; left: 0; width: 100%; }
</style>
</head>
<body>

<!-- PAGE 1: SCHEDULE -->
<div class="sheet-page">
  <div class="center title-1">नई कर व्यवस्था के तहत</div>
  <div class="center title-2">Schedule of Income - Tax</div>
  <div class="center title-1">आयकर की अनुसूची (चार प्रतियों में भर कर दें)</div>
  <div class="center bold" style="font-size: 10px;">{{ emp.ay }} (वित्तीय वर्ष 2025-26)</div>

  <table class="no-border" style="margin-top: 4px;">
    <tr><td style="width: 25%;">करदाता का नाम</td><td>: <b>{{ emp.name }}</b></td></tr>
    <tr><td>पदनाम</td><td>: {{ emp.designation }}</td></tr>
    <tr><td>कार्यालय/विद्यालय का नाम</td><td>: {{ emp.office_name }}</td></tr>
    <tr><td>स्थायी लेखा संख्या (PAN)</td><td>: <b>{{ emp.pan }}</b></td></tr>
  </table>

  <table class="border">
    <tr class="bg-gray bold">
      <th style="width: 5%;">क</th>
      <th style="width: 72%; text-align: left;">वेतन स्रोत से आय का विवरण:</th>
      <th style="width: 23%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>वेतन (दिनांक 01.03.2025 से 28.02.2026 तक)</td><td class="right">{{ "%.2f"|format(totals.basic) }}</td></tr>
    <tr><td>02.</td><td>महँगाई भत्ता</td><td class="right">{{ "%.2f"|format(totals.da) }}</td></tr>
    <tr><td>03.</td><td>मकान किराया भत्ता</td><td class="right">{{ "%.2f"|format(totals.hra) }}</td></tr>
    <tr><td>04.</td><td>चिकित्सा भत्ता</td><td class="right">{{ "%.2f"|format(totals.medical) }}</td></tr>
    <tr><td>05.</td><td>परिवहन भत्ता</td><td class="right">0.00</td></tr>
    <tr><td>06.</td><td>परिवहन भत्ता पर महंगाई भत्ता</td><td class="right">0.00</td></tr>
    <tr><td>07.</td><td>विशेष वेतन/बोनस / मानदेय / नर्सिंग भत्ता</td><td class="right">0.00</td></tr>
    <tr><td>08.</td><td>महंगाई भत्ता की बकाया राशि (DA Arrear)</td><td class="right">{{ "%.2f"|format(tax.tot_arrear_da) }}</td></tr>
    <tr><td>09.</td><td>बकाया वेतन एवं भत्ते का राशि (Pay Arrear)</td><td class="right">{{ "%.2f"|format(tax.tot_arrear_pay) }}</td></tr>
    <tr class="bold bg-gray"><td>10.</td><td>वेतन स्रोत से प्राप्त कुल आय</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
  </table>

  <table class="border">
    <tr class="bg-gray bold">
      <th style="width: 5%;">ख</th>
      <th style="width: 72%; text-align: left;">आयकर की संगणना</th>
      <th style="width: 23%; text-align: right;">राशि (Rs.)</th>
    </tr>
    <tr><td>01.</td><td>वेतन स्रोत से प्राप्त कुल आय</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>02.</td><td>घटायें धारा 16 (ia) मानक कटौती (Standard Deduction)</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr><td>03.</td><td>सकल कुल आय</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>04.</td><td>जोडें अन्य स्रोतों / बैंक बचत खाता ब्याज से आय</td><td class="right">0.00</td></tr>
    <tr class="bold"><td>08.</td><td>सकल प्राप्त आय (Gross Total Income)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr class="bold"><td>09.</td><td>कर योग्य आय (रु० 10 के गुणक में परिवर्तित राशि)</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr>
      <td>10.</td>
      <td colspan="2" style="padding: 3px 5px;">
        <b>रु० {{ "%.2f"|format(tax.taxable_income) }} पर देय आयकर:</b><br>
        {% for s in tax.slab_details %}
        <span style="display:inline-block; width: 68%;">&nbsp;&nbsp;{{ s.label }}</span>
        <span style="display:inline-block; width: 30%; text-align: right;">{{ "%.2f"|format(s.amount) }}</span><br>
        {% endfor %}
        <div style="border-top: 0.5px dashed #000; margin-top: 2px;">
          <b>&nbsp;&nbsp;कुल देय आयकर (Slab Tax):</b>
          <span style="float: right;"><b>{{ "%.2f"|format(tax.slab_tax) }}</b></span>
        </div>
      </td>
    </tr>
    <tr><td>11.</td><td>घटायें-धारा 87A के तहत कर में राहत (Rebate)</td><td class="right">{{ "%.2f"|format(tax.rebate_87a) }}</td></tr>
    <tr><td>12.</td><td>शुद्ध देय आयकर</td><td class="right">{{ "%.2f"|format(tax.total_tax - tax.cess) }}</td></tr>
    <tr><td>13.</td><td>जोड़े-4% (स्वास्थ्य एवं शिक्षा उपकर)</td><td class="right">{{ "%.2f"|format(tax.cess) }}</td></tr>
    <tr class="bold bg-gray"><td>14.</td><td>आयकर और शिक्षा उपकर का योग</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>16.</td><td>घटायें-प्रतिमाह वेतन से आयकर (TDS) का भुगतान</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>18.</td><td>वित्तीय वर्ष 2025-26 में भुगतेय आयकर / (रिफंड)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>

  <div class="sign-area">
    <div style="margin-bottom: 8px;"><b>कोषागार:</b> {{ ddo.district }} ({{ ddo.state }})</div>
    <table class="no-border">
      <tr>
        <td style="width: 50%;">हस्ताक्षर करदाता: ____________________</td>
        <td style="width: 50%; text-align: right;">निकासी एवं व्ययन पदाधिकारी हस्ताक्षर एवं मुहर</td>
      </tr>
    </table>
  </div>
</div>

<!-- PAGE 2: FORM 16 PART A -->
<div class="sheet-page">
  <div class="center title-2">FORM NO. 16 - PART A</div>
  <table class="border" style="margin-top: 10px;">
    <tr>
      <td style="width: 50%;"><b>Employer / Department:</b><br>{{ ddo.department }}, {{ ddo.district }} ({{ ddo.state }})</td>
      <td style="width: 50%;"><b>Employee:</b><br>{{ emp.name }}<br>{{ emp.office_name }}</td>
    </tr>
    <tr>
      <td><b>Officer:</b> {{ ddo.officer_name }} (S/O: {{ ddo.father_name }})<br><b>TAN:</b> {{ ddo.tan }}</td>
      <td><b>PAN:</b> {{ emp.pan }}</td>
    </tr>
  </table>
  <table class="border" style="margin-top: 10px;">
    <tr class="bg-gray center bold"><th>Quarter</th><th>TDS Deducted</th><th>TDS Deposited</th></tr>
    <tr class="center"><td>Q1 to Q3</td><td>0.00</td><td>0.00</td></tr>
    <tr class="center"><td>Q4</td><td>{{ "%.2f"|format(tax.tds_paid) }}</td><td>{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray center"><td>Total</td><td>{{ "%.2f"|format(tax.tds_paid) }}</td><td>{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
  </table>
  <div class="sign-area">
    <p>Certified that Rs. <b>{{ "%.2f"|format(tax.tds_paid) }}</b> has been deducted & deposited.</p>
    <table class="no-border"><tr><td>Place: {{ ddo.district }}</td><td style="text-align: right;">_______________________<br>Signature of DDO</td></tr></table>
  </div>
</div>

<!-- PAGE 3: FORM 16 PART B -->
<div class="sheet-page">
  <div class="center title-2">PART B (Annexure)</div>
  <table class="border" style="margin-top: 10px;">
    <tr><td>1. Gross Salary</td><td class="right">{{ "%.2f"|format(tax.gross) }}</td></tr>
    <tr><td>2. Deductions u/s 16(ia)</td><td class="right">{{ "%.2f"|format(tax.std_ded) }}</td></tr>
    <tr class="bold bg-gray"><td>3. Total Taxable Income</td><td class="right">{{ "%.2f"|format(tax.taxable_income) }}</td></tr>
    <tr><td>4. Total Tax Payable</td><td class="right">{{ "%.2f"|format(tax.total_tax) }}</td></tr>
    <tr><td>5. Less TDS Deducted</td><td class="right">{{ "%.2f"|format(tax.tds_paid) }}</td></tr>
    <tr class="bold bg-gray"><td>6. Balance Payable / (Refund)</td><td class="right">{{ "%.2f"|format(tax.net_balance) }}</td></tr>
  </table>
  <div class="sign-area"><table class="no-border"><tr><td>Place: {{ ddo.district }}</td><td style="text-align: right;">Signature of DDO</td></tr></table></div>
</div>

<!-- PAGE 4: MONTHLY SALARY LEDGER -->
<div class="sheet-page">
  <div class="center title-2">मासिक वेतन एवं कटौतियों की विवरणी</div>
  <table class="border" style="font-size: 8px; margin-top: 6px;">
    <tr class="bg-gray center bold">
      <th>माह</th><th>मूल वेतन</th><th>महंगाई</th><th>HRA</th><th>Med</th><th>Arrear</th><th>सकल</th><th>GPF/NPS</th><th>GIS</th><th>PTax</th><th>TDS</th><th>शुद्ध</th>
    </tr>
    {% for r in records %}
    <tr>
      <td>{{ r.month }}</td><td class="right">{{ "%.0f"|format(r.basic) }}</td><td class="right">{{ "%.0f"|format(r.da) }}</td>
      <td class="right">{{ "%.0f"|format(r.hra) }}</td><td class="right">{{ "%.0f"|format(r.medical) }}</td>
      <td class="right">{{ "%.0f"|format(r.arrear_da + r.arrear_pay) }}</td><td class="right bold">{{ "%.0f"|format(r.gross) }}</td>
      <td class="right">{{ "%.0f"|format(r.gpf) }}</td><td class="right">{{ "%.0f"|format(r.gis) }}</td><td class="right">{{ "%.0f"|format(r.ptax) }}</td>
      <td class="right">{{ "%.0f"|format(r.tds) }}</td><td class="right bold">{{ "%.0f"|format(r.net) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold bg-gray">
      <td>कुल योग</td><td class="right">{{ "%.0f"|format(totals.basic) }}</td><td class="right">{{ "%.0f"|format(totals.da) }}</td>
      <td class="right">{{ "%.0f"|format(totals.hra) }}</td><td class="right">{{ "%.0f"|format(totals.medical) }}</td>
      <td class="right">{{ "%.0f"|format(tax.tot_arrear_da + tax.tot_arrear_pay) }}</td><td class="right">{{ "%.0f"|format(tax.gross) }}</td>
      <td class="right">{{ "%.0f"|format(totals.gpf) }}</td><td class="right">{{ "%.0f"|format(totals.gis) }}</td><td class="right">{{ "%.0f"|format(totals.ptax) }}</td>
      <td class="right">{{ "%.0f"|format(tax.tds_paid) }}</td><td class="right">{{ "%.0f"|format(totals.net) }}</td>
    </tr>
  </table>
  <div class="sign-area"><table class="no-border"><tr><td>हस्ताक्षर करदाता</td><td style="text-align: right;">निकासी एवं व्ययन पदाधिकारी</td></tr></table></div>
</div>
</body>
</html>
"""

def generate_pdf_bundle(ddo_dict, emp_dict, full_records, tax_summary):
    totals = {
        'basic': sum(r['basic'] for r in full_records),
        'da': sum(r['da'] for r in full_records),
        'hra': sum(r['hra'] for r in full_records),
        'medical': sum(r['medical'] for r in full_records),
        'gpf': sum(r['gpf'] for r in full_records),
        'gis': sum(r['gis'] for r in full_records),
        'ptax': sum(r['ptax'] for r in full_records),
        'net': sum(r['net'] for r in full_records)
    }
    rendered = Template(HTML_MASTER_TEMPLATE).render(
        ddo=ddo_dict, emp=emp_dict, records=full_records, tax=tax_summary, totals=totals
    )
    return HTML(string=rendered).write_pdf()

# ================= SHARED GENERATOR SUITE =================
def render_full_employee_suite(is_admin_mode=False, prefix="emp"):
    c_p1, c_p2 = st.columns([2, 1])
    with c_p1:
        pan_in = st.text_input("Permanent Account Number (PAN) *", placeholder="ABCDE1234F", key=f"{prefix}_pan_field").upper().strip()
    
    prof = None
    if pan_in and len(pan_in) == 10:
        conn = sqlite3.connect(DB_NAME)
        prof = conn.cursor().execute("SELECT * FROM employee_master_profiles WHERE pan=?", (pan_in,)).fetchone()
        conn.close()
        with c_p2:
            if prof: st.success("✅ Profile Found! Rolled-Forward.")
            else: st.info("🆕 Fresh Registration.")

    status_sel = st.selectbox(
        "Service Condition:",
        ["NORMAL (Regular Continuity)", "TRANSFER (New School / Office)", "PROMOTION / MACP (New Level)", "SUSPENSION / LWP"],
        key=f"{prefix}_status_sel"
    )

    c_l1, c_l2, c_l3 = st.columns(3)
    states_list = get_creatable_list("master_states", "name")
    def_st_idx = states_list.index(prof[5]) if prof and prof[5] in states_list else 0
    with c_l1:
        s_st = st.selectbox("State", states_list + ["➕ Add New State"], index=def_st_idx, key=f"{prefix}_st")
        if s_st == "➕ Add New State":
            new_st = st.text_input("Type State Name", key=f"{prefix}_new_st").upper().strip()
            if st.button("Lock State", key=f"{prefix}_btn_st"):
                add_creatable_item("master_states", {"name": new_st})
                st.rerun()
            ch_state = new_st
        else: ch_state = s_st

    dist_list = get_creatable_list("master_districts", "name", "state_name=?", (ch_state,))
    def_dt_idx = dist_list.index(prof[6]) if prof and prof[6] in dist_list else 0
    with c_l2:
        s_dt = st.selectbox("District", dist_list + ["➕ Add New District"], index=def_dt_idx if dist_list else 0, key=f"{prefix}_dt")
        if s_dt == "➕ Add New District":
            new_dt = st.text_input("Type District Name", key=f"{prefix}_new_dt").upper().strip()
            if st.button("Lock District", key=f"{prefix}_btn_dt"):
                add_creatable_item("master_districts", {"state_name": ch_state, "name": new_dt})
                st.rerun()
            ch_dist = new_dt
        else: ch_dist = s_dt

    dept_list = get_creatable_list("master_departments", "name")
    def_dp_idx = dept_list.index(prof[7]) if prof and prof[7] in dept_list else 0
    with c_l3:
        s_dp = st.selectbox("Department", dept_list + ["➕ Add New Department"], index=def_dp_idx, key=f"{prefix}_dp")
        if s_dp == "➕ Add New Department":
            new_dp = st.text_input("Type Dept Name", key=f"{prefix}_new_dp").upper().strip()
            if st.button("Lock Dept", key=f"{prefix}_btn_dp"):
                add_creatable_item("master_departments", {"name": new_dp})
                st.rerun()
            ch_dept = new_dp
        else: ch_dept = s_dp

    c_d1, c_d2 = st.columns(2)
    conn = sqlite3.connect(DB_NAME)
    matching_ddos = conn.cursor().execute("SELECT id, officer_name, tan FROM ddo_masters WHERE district=? AND department=?", (ch_dist, ch_dept)).fetchall()
    conn.close()

    with c_d1:
        if matching_ddos:
            ddo_opts = {f"DDO: {d[1]} | TAN: {d[2]}": d[0] for d in matching_ddos}
            ch_ddo_name = st.selectbox("Select DDO Center", list(ddo_opts.keys()), key=f"{prefix}_ddo_s")
            ch_ddo_id = ddo_opts[ch_ddo_name]
        else:
            st.warning("No DDO registered for this location yet.")
            with st.popover("➕ Create DDO Center"):
                in_off = st.text_input("Officer Name", value="DDO Incharge", key=f"{prefix}_in_off")
                in_fat = st.text_input("Father's Name (S/O)", value="Father Name", key=f"{prefix}_in_fat")
                in_tan = st.text_input("TAN Number", value="PTIK01234A", key=f"{prefix}_in_tan").upper()
                if st.button("Save DDO", key=f"{prefix}_in_ddo_btn"):
                    conn = sqlite3.connect(DB_NAME)
                    conn.cursor().execute("INSERT INTO ddo_masters (state, district, department, officer_name, father_name, tan) VALUES (?,?,?,?,?,?)",
                                          (ch_state, ch_dist, ch_dept, in_off, in_fat, in_tan))
                    conn.commit()
                    conn.close()
                    st.rerun()
            ch_ddo_id = None

    with c_d2:
        off_list = get_creatable_list("master_offices", "name_and_address", "district=? AND department=?", (ch_dist, ch_dept))
        def_o_idx = off_list.index(prof[8]) if prof and prof[8] in off_list else 0
        s_of = st.selectbox("Office / School Address", off_list + ["➕ Add New Office Address"], index=def_o_idx if off_list else 0, key=f"{prefix}_off")
        if s_of == "➕ Add New Office Address":
            new_of = st.text_input("Full Address", key=f"{prefix}_new_of").strip()
            if st.button("Lock Address", key=f"{prefix}_btn_of"):
                add_creatable_item("master_offices", {"district": ch_dist, "department": ch_dept, "name_and_address": new_of})
                st.rerun()
            ch_office = new_of
        else: ch_office = s_of

    st.caption("🔒 Zero Space Memory Scanner: Parsed in RAM and discarded instantly.")
    slip_up = st.file_uploader("Upload Salary Slip (PDF)", type=["pdf"], key=f"{prefix}_slip")
    scanned = parse_slip_in_memory(slip_up) if slip_up else None
    if scanned and slip_up:
        st.success(f"⚡ Extracted: Basic ₹{scanned['basic']:,.0f} | DA ₹{scanned['da']:,.0f} | Buffer purged.")

    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    h_level = prof[10] if prof else "Level 7"
    h_basic = prof[11] if prof else 49000.0
    h_inc_m = prof[12] if prof else "1st JULY"
    h_pen = prof[13] if prof else "NPS"
    h_vgpf = prof[14] if prof else 0.0

    if scanned and scanned['basic'] > 0: h_basic = scanned['basic']
    if prof and status_sel == "NORMAL (Regular Continuity)": h_basic = get_next_matrix_cell(h_level, h_basic)

    with c_m1: s_lvl = st.selectbox("Pay Level", list(PAY_MATRIX.keys()), index=list(PAY_MATRIX.keys()).index(h_level) if h_level in PAY_MATRIX else 5, key=f"{prefix}_lvl")
    with c_m2: s_bsc = st.number_input("March Basic Pay", value=int(h_basic), step=100, key=f"{prefix}_bsc")
    with c_m3: s_incm = st.selectbox("Increment Month", ["NONE", "1st JULY", "1st JANUARY"], index=["NONE", "1st JULY", "1st JANUARY"].index(h_inc_m), key=f"{prefix}_incm")
    with c_m4:
        c_incb = get_next_matrix_cell(s_lvl, s_bsc) if s_incm != "NONE" else s_bsc
        s_incb = st.number_input("Incremented Basic", value=int(c_incb), step=100, key=f"{prefix}_incb")

    c_p1, c_p2 = st.columns(2)
    with c_p1: s_pen = st.radio("Pension Scheme", ["NPS (10% Basic+DA)", "Old Pension (GPF)"], index=0 if h_pen == "NPS" else 1, horizontal=True, key=f"{prefix}_pen")
    with c_p2: s_vgp = st.number_input("Voluntary GPF/Mo", value=int(h_vgpf), step=500, key=f"{prefix}_vgp") if "GPF" in s_pen else 0.0

    allow_def = compute_allowances(s_bsc, "NPS" if "NPS" in s_pen else "GPF", s_vgp)

    st.markdown("##### 🔍 Live Verification & Quick-Edit Summary Card")
    with st.container(border=True):
        c_v1, c_v2, c_v3, c_v4 = st.columns(4)
        with c_v1:
            v_name = st.text_input("Name *", value=prof[1] if prof else (scanned['name'] if scanned and scanned['name'] else "Employee Name"), key=f"{prefix}_vn")
            v_des = st.text_input("Designation", value=prof[2] if prof else "+2 Teacher", key=f"{prefix}_vd")
        with c_v2:
            v_mob = st.text_input("Mobile *", value=prof[3] if prof else "", key=f"{prefix}_vm")
            v_eml = st.text_input("Email (For Dispatch)", value=prof[4] if prof else "", key=f"{prefix}_ve")
        with c_v3:
            v_da = st.number_input("DA/Mo", value=int(scanned['da'] if scanned and scanned['da'] else allow_def['da']), step=100, key=f"{prefix}_vda")
            v_hra = st.number_input("HRA/Mo", value=int(scanned['hra'] if scanned and scanned['hra'] else allow_def['hra']), step=100, key=f"{prefix}_vhra")
        with c_v4:
            v_gpf = st.number_input("GPF/NPS /Mo", value=int(scanned['gpf'] if scanned and scanned['gpf'] else allow_def['gpf_nps']), step=100, key=f"{prefix}_vgpf")
            v_tds = st.number_input("Monthly TDS (March-Jan)", value=0, step=500, key=f"{prefix}_vtds")

    recs_11 = []
    for idx in range(11):
        m = REGULAR_MONTHS[idx]
        cb = s_incb if (s_incm == "1st JULY" and idx >= 4) or (s_incm == "1st JANUARY" and idx >= 10) else s_bsc
        cg = cb + v_da + v_hra + 500
        recs_11.append({
            'month': m, 'basic': cb, 'da': v_da, 'hra': v_hra, 'medical': 500.0,
            'arrear_da': 0.0, 'arrear_pay': 0.0, 'gross': cg, 'gpf': v_gpf,
            'gis': 60.0, 'ptax': 200.0, 'tds': float(v_tds), 'net': cg - (v_gpf + 260 + v_tds)
        })

    full_12, tax_calc = compute_annual_tax_feb_balancing(recs_11)
    st.info(f"🎯 **February Balancing:** Feb Basic ₹{full_12[11]['basic']:,.0f} | **Feb Balanced TDS:** ₹{tax_calc['feb_tds']:,.0f} | **Final Schedule Balance:** ₹{tax_calc['net_balance']:,.0f} (NIL)")

    if is_admin_mode:
        if st.button("🚀 Save & Instantly Generate PDF (Admin Authority)", use_container_width=True, key=f"{prefix}_adm_btn"):
            if not (pan_in and v_name and ch_office and ch_ddo_id):
                st.error("Please fill PAN, Name, DDO and Office!")
            else:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                today_str = date.today().strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_NAME)
                conn.cursor().execute('''INSERT INTO employee_master_profiles (
                    pan, name, designation, mobile, email, last_state, last_district, last_dept,
                    last_office, last_ddo_id, last_pay_level, last_basic_pay, last_inc_month,
                    pension_type, voluntary_gpf, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(pan) DO UPDATE SET
                        name=excluded.name, last_office=excluded.last_office, last_basic_pay=excluded.last_basic_pay''',
                    (pan_in, v_name, v_des, v_mob, v_eml, ch_state, ch_dist, ch_dept, ch_office, ch_ddo_id,
                     s_lvl, s_bsc, s_incm, "NPS" if "NPS" in s_pen else "GPF", s_vgp, now_str))

                conn.cursor().execute('''INSERT INTO employee_yearly_records (
                    ay, ddo_id, pan, name, designation, office_name, service_status, pay_level,
                    pension_type, start_basic, inc_month, inc_basic, default_da, default_hra,
                    default_med, default_gpf, default_gis, default_ptax, monthly_tds, mobile,
                    email, payment_status, payment_mode, utr_no, amount_paid, created_at, created_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ay, pan) DO UPDATE SET payment_status='APPROVED' ''',
                    (GLOBAL_AY, ch_ddo_id, pan_in, v_name, v_des, ch_office, status_sel, s_lvl,
                     "NPS" if "NPS" in s_pen else "GPF", s_bsc, s_incm, s_incb, v_da, v_hra, 500.0,
                     v_gpf, 60.0, 200.0, v_tds, v_mob, v_eml, 'APPROVED', 'ADMIN_DIRECT', 'ADMIN_AUTH', 0.0, now_str, today_str))
                y_id = conn.cursor().execute("SELECT id FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()[0]

                conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_id,))
                for r in full_12:
                    conn.cursor().execute('''INSERT INTO monthly_salary_ledgers (
                        yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay,
                        gross, gpf, gis, ptax, tds, net) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (y_id, r['month'], r['basic'], r['da'], r['hra'], r['medical'], r['arrear_da'], r['arrear_pay'], r['gross'], r['gpf'], r['gis'], r['ptax'], r['tds'], r['net']))
                
                ddo_r = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (ch_ddo_id,)).fetchone()
                conn.commit()
                conn.close()

                ddo_d = {'state': ddo_r[1], 'district': ddo_r[2], 'department': ddo_r[3], 'officer_name': ddo_r[4], 'father_name': ddo_r[5], 'tan': ddo_r[6]}
                emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': v_name, 'designation': v_des, 'office_name': ch_office}
                pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, full_12, tax_calc)

                if v_eml: send_email_with_pdf(v_eml, f"Official Form 16 - {GLOBAL_AY}", "Attached is your Form 16.", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf")
                st.download_button("📥 Download Generated 4-Page PDF Now", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf", "application/pdf", use_container_width=True)
    else:
        c_fee = float(get_setting('form_fee', '100'))
        c_upi = get_setting('upi_id', 'mallick.nitin@okaxis')
        is_wl = is_pan_whitelisted(pan_in)

        if is_wl:
            st.success("⭐ Pre-Approved Whitelist active: Payment step bypassed.")
            btn_t = st.button("🚀 Generate PDF Bundle (Instant)", use_container_width=True, key=f"{prefix}_t_btn")
            u_mode, u_utr, fee_amt = "WHITELIST", "PRE_APPROVED", 0.0
        else:
            st.write(f"**Fee Amount:** ₹{c_fee:,.0f}")
            p_mode = st.radio("Payment Mode:", [f"💳 UPI QR (₹{c_fee:,.0f})", "💵 Paid Cash to Admin"], horizontal=True, key=f"{prefix}_pm")
            u_utr = ""
            if "UPI" in p_mode:
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=upi://pay?pa={c_upi}%26pn=TDS%20Office%26am={c_fee}%26cu=INR"
                st.image(qr_url, caption="Scan & Pay via any UPI App")
                u_utr = st.text_input("Enter 12-Digit UTR Number *", key=f"{prefix}_utr")
            btn_t = st.button("🚀 Confirm & Submit Request", use_container_width=True, key=f"{prefix}_t_btn")
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
                    pan, name, designation, mobile, email, last_state, last_district, last_dept,
                    last_office, last_ddo_id, last_pay_level, last_basic_pay, last_inc_month,
                    pension_type, voluntary_gpf, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(pan) DO UPDATE SET
                        name=excluded.name, last_office=excluded.last_office, last_basic_pay=excluded.last_basic_pay''',
                    (pan_in, v_name, v_des, v_mob, v_eml, ch_state, ch_dist, ch_dept, ch_office, ch_ddo_id,
                     s_lvl, s_bsc, s_incm, "NPS" if "NPS" in s_pen else "GPF", s_vgp, now_str))

                pay_stat = "APPROVED" if is_wl else "PENDING"
                conn.cursor().execute('''INSERT INTO employee_yearly_records (
                    ay, ddo_id, pan, name, designation, office_name, service_status, pay_level,
                    pension_type, start_basic, inc_month, inc_basic, default_da, default_hra,
                    default_med, default_gpf, default_gis, default_ptax, monthly_tds, mobile,
                    email, payment_status, payment_mode, utr_no, amount_paid, created_at, created_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ay, pan) DO UPDATE SET payment_status=excluded.payment_status''',
                    (GLOBAL_AY, ch_ddo_id, pan_in, v_name, v_des, ch_office, status_sel, s_lvl,
                     "NPS" if "NPS" in s_pen else "GPF", s_bsc, s_incm, s_incb, v_da, v_hra, 500.0,
                     v_gpf, 60.0, 200.0, v_tds, v_mob, v_eml, pay_stat, u_mode, u_utr, fee_amt, now_str, today_str))
                y_id = conn.cursor().execute("SELECT id FROM employee_yearly_records WHERE ay=? AND pan=?", (GLOBAL_AY, pan_in)).fetchone()[0]

                conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_id,))
                for r in full_12:
                    conn.cursor().execute('''INSERT INTO monthly_salary_ledgers (
                        yearly_record_id, month_name, basic_pay, da, hra, medical, arrear_da, arrear_pay,
                        gross, gpf, gis, ptax, tds, net) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (y_id, r['month'], r['basic'], r['da'], r['hra'], r['medical'], r['arrear_da'], r['arrear_pay'], r['gross'], r['gpf'], r['gis'], r['ptax'], r['tds'], r['net']))
                
                ddo_r = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (ch_ddo_id,)).fetchone()
                conn.commit()
                conn.close()

                if is_wl:
                    ddo_d = {'state': ddo_r[1], 'district': ddo_r[2], 'department': ddo_r[3], 'officer_name': ddo_r[4], 'father_name': ddo_r[5], 'tan': ddo_r[6]}
                    emp_d = {'ay': GLOBAL_AY, 'pan': pan_in, 'name': v_name, 'designation': v_des, 'office_name': ch_office}
                    pdf_bytes = generate_pdf_bundle(ddo_d, emp_d, full_12, tax_calc)
                    if v_eml: send_email_with_pdf(v_eml, f"Official Form 16 - {GLOBAL_AY}", "Attached is your Form 16.", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf")
                    st.download_button("📥 Download Official 4-Page PDF Now", pdf_bytes, f"{pan_in}_{GLOBAL_AY}.pdf", "application/pdf", use_container_width=True)
                else:
                    st.success("Request recorded successfully! Once approved by Admin, download from 'Already Paid' tab.")

# ================= TOP BAR & SECRET URL ROUTING =================
query_params = st.query_params
is_admin_url = query_params.get("admin", "").lower() == "true"

col_ay1, col_ay2 = st.columns([3, 1])
with col_ay1: st.markdown("## 🏛️ Comprehensive Institutional TDS & Form 16 Portal")
with col_ay2: GLOBAL_AY = st.selectbox("Active Assessment Year", AY_OPTIONS, index=0)

if is_admin_url:
    tab_emp, tab_redownload, tab_admin = st.tabs([
        "👤 Standalone Employee Portal",
        "🔍 Already Paid? Re-Download Archive",
        "🔒 Admin Command Center"
    ])
else:
    tab_emp, tab_redownload = st.tabs([
        "👤 Standalone Employee Portal",
        "🔍 Already Paid? Re-Download Archive"
    ])
    tab_admin = None

# ================= TAB 1: EMPLOYEE PORTAL =================
with tab_emp:
    render_full_employee_suite(is_admin_mode=False, prefix="emp_public")

# ================= TAB 2: RE-DOWNLOAD ARCHIVE =================
with tab_redownload:
    st.markdown("### 🔍 Re-Download Your Official Generated Form 16")
    c_rd1, c_rd2 = st.columns(2)
    with c_rd1: rd_pan = st.text_input("Enter PAN Number", key="rd_pan_field").upper().strip()
    with c_rd2: rd_ay = st.selectbox("Select Assessment Year", AY_OPTIONS, key="rd_ay_field")

    if st.button("Search Archive & Download"):
        if not rd_pan:
            st.warning("Please enter your PAN.")
        else:
            conn = sqlite3.connect(DB_NAME)
            y_rec = conn.cursor().execute("SELECT * FROM employee_yearly_records WHERE ay=? AND pan=?", (rd_ay, rd_pan)).fetchone()
            conn.close()

            if not y_rec:
                st.error(f"No record found for PAN: {rd_pan} in {rd_ay}.")
            elif y_rec[21] != "APPROVED":
                st.warning(f"Record found for {y_rec[4]}, but Payment Status is **{y_rec[21]}**. Awaiting Admin Verification.")
            else:
                conn = sqlite3.connect(DB_NAME)
                ddo_row = conn.cursor().execute("SELECT * FROM ddo_masters WHERE id=?", (y_rec[2],)).fetchone()
                ledgers = conn.cursor().execute("SELECT * FROM monthly_salary_ledgers WHERE yearly_record_id=?", (y_rec[0],)).fetchall()
                conn.close()

                recs_rd = [{
                    'month': l[2], 'basic': l[3], 'da': l[4], 'hra': l[5], 'medical': l[6],
                    'arrear_da': l[7], 'arrear_pay': l[8], 'gross': l[9], 'gpf': l[10],
                    'gis': l[11], 'ptax': l[12], 'tds': l[13], 'net': l[14]
                } for l in ledgers]

                full_12_rd, tax_rd = compute_annual_tax_feb_balancing(recs_rd[:11])
                ddo_d = {'state': ddo_row[1], 'district': ddo_row[2], 'department': ddo_row[3], 'officer_name': ddo_row[4], 'father_name': ddo_row[5], 'tan': ddo_row[6]}
                emp_d = {'ay': rd_ay, 'pan': rd_pan, 'name': y_rec[4], 'designation': y_rec[5], 'office_name': y_rec[6]}
                pdf_data = generate_pdf_bundle(ddo_d, emp_d, full_12_rd, tax_rd)

                st.success(f"Verified Record Found: **{y_rec[4]}** | Office: {y_rec[6]}")
                col_dla, col_dlb = st.columns(2)
                with col_dla:
                    st.download_button("📥 Download 4-Page PDF Bundle", pdf_data, f"{rd_pan}_{rd_ay}.pdf", "application/pdf", use_container_width=True)
                with col_dlb:
                    if y_rec[20] and st.button("📩 Re-Send to Registered Email"):
                        sent = send_email_with_pdf(y_rec[20], f"Official Form 16 - {rd_ay}", "Attached is your Form 16.", pdf_data, f"{rd_pan}_{rd_ay}.pdf")
                        if sent: st.toast("Email re-sent successfully!")

# ================= TAB 3: ADMIN COMMAND CENTER (SECRET GATE) =================
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

            adm_sub_tab0, adm_sub_tab1, adm_sub_tab2, adm_sub_tab3, adm_sub_tab4, adm_sub_tab5 = st.tabs([
                "⚡ Single Employee Suite",
                "📊 Revenue & Analytics Dashboard",
                "🗃️ Master Database Manager",
                "📥 Live Payment Queue",
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
                with c_dt1:
                    filter_from = st.date_input("From Date", value=date(2025, 4, 1))
                with c_dt2:
                    filter_to = st.date_input("To Date", value=date.today())

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
                st.markdown("#### 🥧 Payment & Channel Distribution")
                cat_data = [
                    {"Channel": "Online UPI (Captured)", "Transactions": sum(1 for r in raw_records if r[0] == 'UPI' and r[1] == 'APPROVED'), "Revenue (₹)": total_upi_rev},
                    {"Channel": "Cash to Admin (Verified)", "Transactions": sum(1 for r in raw_records if r[0] == 'CASH' and r[1] == 'APPROVED'), "Revenue (₹)": total_cash_rev},
                    {"Channel": "Whitelisted / Pre-Approved", "Transactions": whitelisted_count, "Revenue (₹)": 0.0},
                    {"Channel": "Awaiting Approval (Pipeline)", "Transactions": pending_count, "Revenue (₹)": sum(r[2] for r in raw_records if r[1] == 'PENDING')}
                ]
                st.table(cat_data)

                st.write("---")
                st.markdown("#### 📥 Accountant Excel Audit Report (.xlsx)")
                if st.button("Generate Audit Report"):
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
                        label="💾 Download Financial Audit Excel (.xlsx)",
                        data=xl_buf.getvalue(),
                        file_name=f"Audit_Report_{filter_from}_to_{filter_to}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            # --- 2. MASTER DATABASE MANAGER (CRUD) ---
            with adm_sub_tab2:
                st.subheader("🗃️ Master Database Manager (Direct Edit & Delete)")
                conn = sqlite3.connect(DB_NAME)
                users = conn.cursor().execute("""
                    SELECT id, pan, name, designation, office_name, start_basic, payment_status, payment_mode, mobile, amount_paid 
                    FROM employee_yearly_records WHERE ay=? ORDER BY id DESC
                """, (GLOBAL_AY,)).fetchall()
                conn.close()

                st.markdown(f"**Total Registered Employees ({GLOBAL_AY}):** {len(users)}")
                
                for u in users:
                    u_id, u_pan, u_name, u_des, u_off, u_bsc, u_stat, u_mod, u_mob, u_amt = u
                    with st.expander(f"👤 {u_name} ({u_pan}) | {u_off} | Status: {u_stat}"):
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
                                    st.success("Updated!")
                                    st.rerun()
                            with c_btn_d:
                                if st.form_submit_button("🗑️ Delete Record Permanently"):
                                    conn = sqlite3.connect(DB_NAME)
                                    conn.cursor().execute("DELETE FROM monthly_salary_ledgers WHERE yearly_record_id=?", (u_id,))
                                    conn.cursor().execute("DELETE FROM employee_yearly_records WHERE id=?", (u_id,))
                                    conn.commit()
                                    conn.close()
                                    st.warning("Deleted!")
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
                            st.markdown(f"**{r[4]}** (`{r[3]}`) | 📞 {r[19]}")
                            st.caption(f"Office: {r[6]} | Basic: ₹{r[9]:,.0f} | Inc: {r[10]} (₹{r[11]:,.0f})")
                        with cB:
                            st.markdown(f"**Mode:** {r[22]} | **UTR:** `{r[23]}`")
                            st.caption(f"Status: **{r[21]}** | Time: {r[25]}")
                        with cC:
                            if r[21] == "PENDING":
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
                                conn.close()
                                
                                recs_adm = [{
                                    'month': l[2], 'basic': l[3], 'da': l[4], 'hra': l[5], 'medical': l[6],
                                    'arrear_da': l[7], 'arrear_pay': l[8], 'gross': l[9], 'gpf': l[10],
                                    'gis': l[11], 'ptax': l[12], 'tds': l[13], 'net': l[14]
                                } for l in ledgers]
                                
                                full_12_adm, tax_adm = compute_annual_tax_feb_balancing(recs_adm[:11])
                                ddo_d = {'state': ddo_row[1], 'district': ddo_row[2], 'department': ddo_row[3], 'officer_name': ddo_row[4], 'father_name': ddo_row[5], 'tan': ddo_row[6]}
                                emp_d = {'ay': GLOBAL_AY, 'pan': r[3], 'name': r[4], 'designation': r[5], 'office_name': r[6]}
                                pdf_data = generate_pdf_bundle(ddo_d, emp_d, full_12_adm, tax_adm)

                                st.download_button(
                                    label="📥 Download PDF",
                                    data=pdf_data,
                                    file_name=f"{r[3]}_{GLOBAL_AY}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_adm_q_{r[0]}"
                                )

            # --- 4. DDO & HIERARCHY MASTER ---
            with adm_sub_tab4:
                st.subheader("Manage Institutional DDO Centers")
                conn = sqlite3.connect(DB_NAME)
                ddo_table = conn.cursor().execute("SELECT id, state, district, department, officer_name, tan FROM ddo_masters").fetchall()
                conn.close()
                st.dataframe(ddo_table, use_container_width=True)

                with st.expander("➕ Register New DDO Center"):
                    with st.form("adm_new_ddo"):
                        a_st = st.selectbox("State", get_creatable_list("master_states", "name"))
                        a_dt = st.selectbox("District", get_creatable_list("master_districts", "name", "state_name=?", (a_st,)))
                        a_dp = st.selectbox("Department", get_creatable_list("master_departments", "name"))
                        a_off = st.text_input("Officer Incharge Name")
                        a_fat = st.text_input("Father's Name (S/O)")
                        a_tan = st.text_input("TAN Number").upper()
                        if st.form_submit_button("Save DDO"):
                            conn = sqlite3.connect(DB_NAME)
                            conn.cursor().execute("INSERT INTO ddo_masters (state, district, department, officer_name, father_name, tan) VALUES (?,?,?,?,?,?)",
                                                  (a_st, a_dt, a_dp, a_off, a_fat, a_tan))
                            conn.commit()
                            conn.close()
                            st.success("DDO Saved!")
                            st.rerun()

            # --- 5. CONFIG & CREDENTIALS ---
            with adm_sub_tab5:
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
                    upi_val = st.text_input("Receiving UPI ID", value=get_setting('upi_id', 'mallick.nitin@okaxis'))
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

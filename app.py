import streamlit as st
import sqlite3
from pypdf import PdfReader
import re
from datetime import date
from weasyprint import HTML
from jinja2 import Template

# ================= PAGE CONFIGURATION =================
st.set_page_config(
    page_title="Kosh-Tax | Form 16 & TDS Manager",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_NAME = "kosh_tax_enterprise.sqlite"

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS employee_profiles (
        pan TEXT PRIMARY KEY, name TEXT, designation TEXT, mobile TEXT, email TEXT, 
        office_name TEXT, district TEXT, gpf_no TEXT, updated_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS ddo_masters (
        tan TEXT PRIMARY KEY, office_address TEXT, officer_name TEXT, father_name TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}
if 'payment_status' not in st.session_state:
    st.session_state.payment_status = 'pending'

# Helper to convert dictionary values to uppercase
def make_upper(data_dict):
    return {k: (v.upper() if isinstance(v, str) else v) for k, v in data_dict.items()}

# ================= HELPER PARSER =================
def parse_salary_slip_data(uploaded_file):
    data = {
        'name': '', 'pan': '', 'designation': '', 'district': 'KHUNTI',
        'basic': 0.0, 'da': 0.0, 'hra': 0.0, 'medical': 0.0,
        'gpf': 0.0, 'gis': 60.0, 'ptax': 200.0, 'gpf_no': '',
        'arrear_da': 0.0, 'arrear_pay': 0.0, 'confidence': 0
    }
    try:
        reader = PdfReader(uploaded_file)
        text = "".join([p.extract_text() or "" for p in reader.pages]).upper()

        pan_m = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', text)
        if pan_m:
            data['pan'] = pan_m.group(1).upper()

        name_m = re.search(r'EMPLOYEE\s*NAME\s*[:\-]?\s*([A-Z\s\.]+?)(?=\s*PAN|\s*DDO|\n|$)', text)
        if name_m:
            data['name'] = name_m.group(1).strip().upper()

        for des in ["CLERK", "LIPIK", "ASSISTANT TEACHER", "TEACHER", "HEADMASTER", "PRINCIPAL", "ACCOUNTANT"]:
            if des in text:
                data['designation'] = des.upper()
                break

        gpf_m = re.search(r'(?:GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', text)
        if gpf_m: data['gpf_no'] = gpf_m.group(1).strip().upper()

        def get_val(labels):
            for l in labels:
                m = re.search(rf"{l}\s*[:\-]?\s*[₹Rs\.\s]*([0-9,]+(?:\.[0-9]+)?)", text)
                if m:
                    try: return float(m.group(1).replace(',', ''))
                    except: pass
            return 0.0

        data['basic'] = get_val(["BASIC", "मूल वेतन"])
        data['da'] = get_val(["DA", "महंगाई भत्ता"])
        data['hra'] = get_val(["HRA"])
        data['gpf'] = get_val(["GPF", "NPS"])
        data['gis'] = get_val(["GIS"]) or 60.0
        data['ptax'] = get_val(["PTAX", "PROFESSIONAL TAX"]) or 200.0
        data['arrear_da'] = get_val(["ARREAR DA"])
        data['arrear_pay'] = get_val(["ARREAR PAY", "PAY ARREAR"])

    except Exception as e:
        print(f"Error parsing: {e}")
    return make_upper(data)

# ================= PDF GENERATOR =================
def generate_form16_pdf(data):
    template = Template("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 10px; text-transform: uppercase; }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  table, th, td { border: 1px solid black; }
  th, td { padding: 5px; }
</style>
</head>
<body>
<div class="center">
  <h2>FORM NO. 16 - PART A & B</h2>
  <p>ASSESSMENT YEAR: {{ data.assessment_year }}</p>
</div>

<table>
  <tr>
    <td><b>EMPLOYER / DDO ADDRESS:</b><br>{{ data.employer_address }}<br><b>TAN:</b> {{ data.ddo_tan }}</td>
    <td><b>EMPLOYEE NAME:</b><br>{{ data.name }}<br><b>PAN:</b> {{ data.pan }}<br><b>DESIGNATION:</b> {{ data.designation }}</td>
  </tr>
  <tr>
    <td><b>OFFICE / SCHOOL:</b><br>{{ data.office_name }}</td>
    <td><b>DISTRICT:</b> {{ data.district }} | <b>GPF NO:</b> {{ data.gpf_no }}</td>
  </tr>
</table>

<h3>SALARY COMPONENTS</h3>
<table>
  <tr class="bold">
    <th>COMPONENT</th>
    <th>AMOUNT (RS)</th>
  </tr>
  <tr><td>BASIC PAY</td><td>{{ data.basic }}</td></tr>
  <tr><td>DA</td><td>{{ data.da }}</td></tr>
  <tr><td>HRA</td><td>{{ data.hra }}</td></tr>
  <tr><td>MEDICAL</td><td>{{ data.medical }}</td></tr>
  <tr><td>ARREAR DA</td><td>{{ data.arrear_da }}</td></tr>
  <tr><td>ARREAR PAY</td><td>{{ data.arrear_pay }}</td></tr>
  <tr class="bold"><td>GROSS SALARY</td><td>{{ data.basic + data.da + data.hra + data.medical + data.arrear_da + data.arrear_pay }}</td></tr>
</table>

<div style="margin-top: 30px;">
  <p>CERTIFIED THAT THE INFORMATION PROVIDED ABOVE IS TRUE AND CORRECT.</p>
  <div style="margin-top: 40px; text-align: right;">
    ________________________<br>
    DDO OFFICER: {{ data.ddo_officer }}<br>
    FATHER NAME: {{ data.ddo_father }}<br>
    DRAWING AND DISBURSING OFFICER<br>
    DATE: {{ today }}
  </div>
</div>
</body>
</html>
""")
    html_content = template.render(data=data, today=date.today().strftime("%d.%m.%Y"))
    return HTML(string=html_content).write_pdf()

# ================= PAGES =================
def show_home():
    st.markdown("# 🏛️ KOSH-TAX | FORM 16 & TDS MANAGEMENT PORTAL")
    st.markdown("### AUTOMATED SALARY MANAGEMENT FOR JHARKHAND GOVERNMENT EMPLOYEES")
    
    if st.button("🚀 START FORM 16 GENERATOR", type="primary", use_container_width=True):
        st.session_state.current_page = 'upload'
        st.rerun()

def show_upload():
    st.title("📎 STEP 1: UPLOAD SALARY SLIP")
    st.write("Upload your salary slip PDF to auto-extract details. Returning users will have their profiles auto-loaded via PAN.")

    uploaded_file = st.file_uploader("CHOOSE PDF SALARY SLIP", type=['pdf'])

    if uploaded_file:
        with st.spinner("Analyzing salary slip and checking database records..."):
            scanned = parse_salary_slip_data(uploaded_file)
            
            pan_val = scanned.get('pan', '')
            saved_profile = {}
            if pan_val:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                row = c.execute("SELECT mobile, email, office_name, district, designation, gpf_no FROM employee_profiles WHERE pan=?", (pan_val,)).fetchone()
                conn.close()
                if row:
                    saved_profile = {
                        'mobile': row[0] or '', 'email': row[1] or '', 'office_name': row[2] or '',
                        'district': row[3] or 'KHUNTI', 'designation': row[4] or scanned['designation'],
                        'gpf_no': row[5] or ''
                    }

            st.session_state.extracted_data = {**scanned, **saved_profile}
            st.success("✅ SALARY SLIP SCANNED SUCCESSFULLY!")
            
            if saved_profile:
                st.info("🔄 RETURNING USER RECOGNIZED! Office details and contact info auto-loaded from previous records.")

            if st.button("PROCEED TO REVIEW & ENTRY →", type="primary"):
                st.session_state.current_page = 'review'
                st.rerun()

    if st.button("← BACK TO HOME"):
        st.session_state.current_page = 'home'
        st.rerun()

def show_review():
    st.title("📋 STEP 2: REVIEW & COMPLETE DETAILS")
    data = st.session_state.extracted_data or {}

    with st.form("main_entry_form"):
        # --- 1. DDO Details ---
        st.subheader("🏢 DDO & EMPLOYER DETAILS")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            tan_input = st.text_input("DDO TAN NUMBER * (ENTER FIRST)", value=data.get('ddo_tan', '')).upper()
            
            fetched_officer, fetched_father, fetched_addr = "", "", ""
            if tan_input:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                ddo_row = c.execute("SELECT office_address, officer_name, father_name FROM ddo_masters WHERE tan=?", (tan_input,)).fetchone()
                conn.close()
                if ddo_row:
                    fetched_addr, fetched_officer, fetched_father = ddo_row

            employer_address = st.text_area("NAME & ADDRESS OF THE EMPLOYER / OFFICE", value=data.get('employer_address', fetched_addr)).upper()
        with col_d2:
            ddo_officer = st.text_input("DDO OFFICER NAME", value=data.get('ddo_officer', fetched_officer)).upper()
            ddo_father = st.text_input("DDO OFFICER'S FATHER NAME", value=data.get('ddo_father', fetched_father)).upper()
            st.text_input("DDO DESIGNATION", value="DRAWING AND DISBURSING OFFICER", disabled=True)

        # --- 2. Employee Personal Details ---
        st.subheader("👤 EMPLOYEE PERSONAL DETAILS")
        col1, col2 = st.columns(2)
        with col1:
            pan = st.text_input("PAN NUMBER *", value=data.get('pan', '')).upper()
            name = st.text_input("EMPLOYEE NAME *", value=data.get('name', '')).upper()
            designation = st.text_input("DESIGNATION (AUTO FROM SLIP)", value=data.get('designation', '')).upper()
            gpf_no = st.text_input("GPF / PRAN NUMBER", value=data.get('gpf_no', '')).upper()
        with col2:
            mobile = st.text_input("MOBILE NUMBER *", value=data.get('mobile', '')).upper()
            email = st.text_input("EMAIL ADDRESS *", value=data.get('email', '')).upper()
            office_name = st.text_input("OFFICE NAME & ADDRESS (MANUAL)", value=data.get('office_name', '')).upper()
            
            dist_list = ["KHUNTI", "RANCHI", "EAST SINGHBHUM", "DHANBAD", "BOKARO", "HAZARIBAGH", "GUMLA", "SIMDEGA"]
            d_val = data.get('district', 'KHUNTI')
            district = st.selectbox("DISTRICT", dist_list, index=dist_list.index(d_val) if d_val in dist_list else 0)

        # --- 3. Tax & Salary Configuration ---
        st.subheader("💰 SALARY & TAX CONFIGURATION")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            assessment_year = st.selectbox("ASSESSMENT YEAR", ["AY 2026-27 (FY 2025-26)", "AY 2025-26 (FY 2024-25)"])
            tax_regime = st.selectbox("TAX REGIME", ["NEW REGIME", "OLD REGIME"])
        with col_t2:
            arrear_da = st.number_input("ARREAR DA", value=float(data.get('arrear_da', 0)))
            arrear_pay = st.number_input("ARREAR PAY", value=float(data.get('arrear_pay', 0)))

        # --- 4. Monthly Components ---
        st.subheader("📊 MONTHLY SALARY COMPONENTS")
        c1, c2, c3, c4 = st.columns(4)
        with c1: basic = st.number_input("BASIC PAY", value=float(data.get('basic', 0)))
        with c2: da = st.number_input("DA", value=float(data.get('da', 0)))
        with c3: hra = st.number_input("HRA", value=float(data.get('hra', 0)))
        with c4: medical = st.number_input("MEDICAL", value=float(data.get('medical', 1000)))

        c5, c6, c7 = st.columns(3)
        with c5: gpf = st.number_input("GPF / NPS", value=float(data.get('gpf', 0)))
        with c6: gis = st.number_input("GIS", value=float(data.get('gis', 60)))
        with c7: ptax = st.number_input("PROFESSIONAL TAX (PTAX)", value=float(data.get('ptax', 200)))

        submitted = st.form_submit_button("SAVE & GENERATE FORM 16 PDF →", type="primary", use_container_width=True)

        if submitted:
            if not pan or not name or not tan_input:
                st.error("KRIPYA SABHI ZAROORI FIELDS BHAREIN: PAN, EMPLOYEE NAME, AUR DDO TAN!")
            else:
                # Store everything strictly in UPPERCASE in Database
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute('''INSERT OR REPLACE INTO employee_profiles (pan, name, designation, mobile, email, office_name, district, gpf_no, updated_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
                          (pan.upper(), name.upper(), designation.upper(), mobile.upper(), email.upper(), office_name.upper(), district.upper(), gpf_no.upper()))
                if tan_input:
                    c.execute('''INSERT OR REPLACE INTO ddo_masters (tan, office_address, officer_name, father_name)
                                 VALUES (?, ?, ?, ?)''',
                              (tan_input.upper(), employer_address.upper(), ddo_officer.upper(), ddo_father.upper()))
                conn.commit()
                conn.close()

                st.session_state.user_data = {
                    'pan': pan.upper(), 'name': name.upper(), 'designation': designation.upper(), 'mobile': mobile.upper(), 'email': email.upper(),
                    'office_name': office_name.upper(), 'district': district.upper(), 'gpf_no': gpf_no.upper(),
                    'ddo_tan': tan_input.upper(), 'employer_address': employer_address.upper(),
                    'ddo_officer': ddo_officer.upper(), 'ddo_father': ddo_father.upper(),
                    'assessment_year': assessment_year, 'tax_regime': tax_regime,
                    'basic': basic, 'da': da, 'hra': hra, 'medical': medical,
                    'gpf': gpf, 'gis': gis, 'ptax': ptax, 'arrear_da': arrear_da, 'arrear_pay': arrear_pay
                }
                st.session_state.current_page = 'download'
                st.rerun()

    if st.button("← BACK TO UPLOAD"):
        st.session_state.current_page = 'upload'
        st.rerun()

def show_download():
    st.title("📄 STEP 3: DOWNLOAD FORM 16")
    user_data = st.session_state.get('user_data', {})
    
    st.success("✅ PROFILE AUR SALARY RECORDS SUCCESSFULLY PROCESS HO GAYE HAIN!")
    st.info(f"EMPLOYEE: **{user_data.get('name')}** | PAN: **{user_data.get('pan')}** | DDO TAN: **{user_data.get('ddo_tan')}**")

    # Generate PDF with Uppercase data
    pdf_bytes = generate_form16_pdf(user_data)

    st.download_button(
        label="📥 DOWNLOAD FORM 16 PDF",
        data=pdf_bytes,
        file_name=f"FORM16_{user_data.get('pan', 'UNKNOWN')}.PDF",
        mime="application/pdf",
        type="primary",
        use_container_width=True
    )

    if st.button("🔄 PROCESS ANOTHER EMPLOYEE / SLIP", use_container_width=True):
        st.session_state.extracted_data = {}
        st.session_state.user_data = {}
        st.session_state.current_page = 'home'
        st.rerun()

def main():
    if st.session_state.current_page == 'home':
        show_home()
    elif st.session_state.current_page == 'upload':
        show_upload()
    elif st.session_state.current_page == 'review':
        show_review()
    elif st.session_state.current_page == 'download':
        show_download()

    # Footer added here
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: gray; font-size: 12px;'>DEVELOPED & DESIGNED BY @ NITIN MALLICK</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

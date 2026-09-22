import streamlit as st
import sqlite3
from pypdf import PdfReader
import re
from datetime import date

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
    # Employee profiles for returning users (PAN based)
    c.execute('''CREATE TABLE IF NOT EXISTS employee_profiles (
        pan TEXT PRIMARY KEY, name TEXT, designation TEXT, mobile TEXT, email TEXT, 
        office_name TEXT, district TEXT, gpf_no TEXT, updated_at TEXT
    )''')
    # DDO Masters (TAN based)
    c.execute('''CREATE TABLE IF NOT EXISTS ddo_masters (
        tan TEXT PRIMARY KEY, office_address TEXT, officer_name TEXT, father_name TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# Session State Initialization
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}
if 'payment_status' not in st.session_state:
    st.session_state.payment_status = 'pending'

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

        # PAN
        pan_m = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', text)
        if pan_m:
            data['pan'] = pan_m.group(1)
            data['confidence'] += 20

        # Name
        name_m = re.search(r'EMPLOYEE\s*NAME\s*[:\-]?\s*([A-Z\s\.]+?)(?=\s*PAN|\s*DDO|\n|$)', text)
        if name_m:
            data['name'] = name_m.group(1).strip()
            data['confidence'] += 20

        # Designation
        for des in ["CLERK", "LIPIK", "ASSISTANT TEACHER", "TEACHER", "HEADMASTER", "PRINCIPAL"]:
            if des in text:
                data['designation'] = des
                break

        # GPF No
        gpf_m = re.search(r'(?:GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', text)
        if gpf_m: data['gpf_no'] = gpf_m.group(1).strip()

        # Numeric fields extraction helper
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
    return data

# ================= PAGES =================
def show_home():
    st.markdown("# 🏛️ Kosh-Tax | Form 16 & TDS Management Portal")
    st.markdown("### Automated Salary Management for Jharkhand Government Employees")
    
    if st.button("🚀 Start Form 16 Generator", type="primary", use_container_width=True):
        st.session_state.current_page = 'upload'
        st.rerun()

def show_upload():
    st.title("📎 Step 1: Upload Salary Slip")
    st.write("Upload your salary slip PDF to auto-extract details. Returning users will have their profiles auto-loaded via PAN.")

    uploaded_file = st.file_uploader("Choose PDF Salary Slip", type=['pdf'])

    if uploaded_file:
        with st.spinner("Analyzing salary slip and checking database records..."):
            scanned = parse_salary_slip_data(uploaded_file)
            
            # Check if PAN exists in database for returning user auto-fill
            pan_val = scanned.get('pan', '')
            saved_profile = {}
            if pan_val:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                row = c.execute("SELECT mobile, email, office_name, district, designation, gpf_no FROM employee_profiles WHERE pan=?", (pan_val,)).fetchone()
                conn.close()
                if row:
                    saved_profile = {
                        'mobile': row[0], 'email': row[1], 'office_name': row[2],
                        'district': row[3], 'designation': row[4] or scanned['designation'],
                        'gpf_no': row[5]
                    }

            # Merge scanned with saved profile if available
            st.session_state.extracted_data = {**scanned, **saved_profile}
            st.success("✅ Salary slip scanned successfully!")
            
            if saved_profile:
                st.info("🔄 Returning User Recognized! Office details and contact info auto-loaded from previous records.")

            if st.button("Proceed to Review & Entry →", type="primary"):
                st.session_state.current_page = 'review'
                st.rerun()

    if st.button("← Back to Home"):
        st.session_state.current_page = 'home'
        st.rerun()

def show_review():
    st.title("📋 Step 2: Review & Complete Details")
    data = st.session_state.extracted_data or {}

    with st.form("main_entry_form"):
        # --- Employer / DDO Details ---
        st.subheader("🏢 Employer & DDO Details")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            tan_input = st.text_input("DDO TAN Number *", value=data.get('ddo_tan', '')).upper()
            
            # Auto fetch DDO details if TAN exists in DB
            fetched_officer, fetched_father, fetched_addr = "", "", ""
            if tan_input:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                ddo_row = c.execute("SELECT office_address, officer_name, father_name FROM ddo_masters WHERE tan=?", (tan_input,)).fetchone()
                conn.close()
                if ddo_row:
                    fetched_addr, fetched_officer, fetched_father = ddo_row

            employer_address = st.text_area("Name & Address of the Employer / Office", value=data.get('employer_address', fetched_addr))
        with col_d2:
            ddo_officer = st.text_input("DDO Officer Name", value=data.get('ddo_officer', fetched_officer))
            ddo_father = st.text_input("DDO Officer's Father Name", value=data.get('ddo_father', fetched_father))
            st.text_input("DDO Designation", value="Drawing and Disbursing Officer", disabled=True)

        # --- Employee Personal Details ---
        st.subheader("👤 Employee Personal Details")
        col1, col2 = st.columns(2)
        with col1:
            pan = st.text_input("PAN Number * (Auto/Permanent Key)", value=data.get('pan', '')).upper()
            name = st.text_input("Employee Name *", value=data.get('name', ''))
            designation = st.text_input("Designation", value=data.get('designation', ''))
            gpf_no = st.text_input("GPF / PRAN Number", value=data.get('gpf_no', ''))
        with col2:
            mobile = st.text_input("Mobile Number *", value=data.get('mobile', ''))
            email = st.text_input("Email Address *", value=data.get('email', ''))
            office_name = st.text_input("Office Name & Address (Manual)", value=data.get('office_name', ''))
            
            dist_list = ["KHUNTI", "RANCHI", "EAST SINGHBHUM", "DHANBAD", "BOKARO", "HAZARIBAGH", "GUMLA", "SIMDEGA"]
            d_val = data.get('district', 'KHUNTI')
            district = st.selectbox("District", dist_list, index=dist_list.index(d_val) if d_val in dist_list else 0)

        # --- Tax & Salary Configuration ---
        st.subheader("💰 Salary & Tax Configuration")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            assessment_year = st.selectbox("Assessment Year", ["AY 2026-27 (FY 2025-26)", "AY 2025-26 (FY 2024-25)"])
            tax_regime = st.selectbox("Tax Regime", ["NEW REGIME", "OLD REGIME"])
        with col_t2:
            arrear_da = st.number_input("Arrear DA (Auto-detected)", value=float(data.get('arrear_da', 0)))
            arrear_pay = st.number_input("Arrear Pay (Auto-detected)", value=float(data.get('arrear_pay', 0)))

        # --- Monthly Components ---
        st.subheader("📊 Monthly Salary Components")
        c1, c2, c3, c4 = st.columns(4)
        with c1: basic = st.number_input("Basic Pay", value=float(data.get('basic', 0)))
        with c2: da = st.number_input("DA", value=float(data.get('da', 0)))
        with c3: hra = st.number_input("HRA", value=float(data.get('hra', 0)))
        with c4: medical = st.number_input("Medical", value=float(data.get('medical', 1000)))

        c5, c6, c7 = st.columns(3)
        with c5: gpf = st.number_input("GPF / NPS", value=float(data.get('gpf', 0)))
        with c6: gis = st.number_input("GIS", value=float(data.get('gis', 60)))
        with c7: ptax = st.number_input("Professional Tax (PTax)", value=float(data.get('ptax', 200)))

        submitted = st.form_submit_button("Save & Generate Form 16 PDF →", type="primary", use_container_width=True)

        if submitted:
            if not pan or not name or not tan_input:
                st.error("Please fill mandatory fields: PAN, Employee Name, and DDO TAN!")
            else:
                # Save into database for future auto-fill memory
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                # Save employee profile
                c.execute('''INSERT OR REPLACE INTO employee_profiles (pan, name, designation, mobile, email, office_name, district, gpf_no, updated_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
                          (pan, name, designation, mobile, email, office_name, district, gpf_no))
                # Save DDO master if new
                if tan_input:
                    c.execute('''INSERT OR REPLACE INTO ddo_masters (tan, office_address, officer_name, father_name)
                                 VALUES (?, ?, ?, ?)''',
                              (tan_input, employer_address, ddo_officer, ddo_father))
                conn.commit()
                conn.close()

                # Save session user data
                st.session_state.user_data = {
                    'pan': pan, 'name': name, 'designation': designation, 'mobile': mobile, 'email': email,
                    'office_name': office_name, 'district': district, 'gpf_no': gpf_no,
                    'ddo_tan': tan_input, 'employer_address': employer_address,
                    'ddo_officer': ddo_officer, 'ddo_father': ddo_father,
                    'assessment_year': assessment_year, 'tax_regime': tax_regime,
                    'basic': basic, 'da': da, 'hra': hra, 'medical': medical,
                    'gpf': gpf, 'gis': gis, 'ptax': ptax, 'arrear_da': arrear_da, 'arrear_pay': arrear_pay
                }
                st.session_state.current_page = 'download'
                st.rerun()

    if st.button("← Back to Upload"):
        st.session_state.current_page = 'upload'
        st.rerun()

def show_download():
    st.title("📄 Step 3: Download Form 16")
    user_data = st.session_state.get('user_data', {})
    
    st.success("✅ Profile and salary records processed successfully with database memory updated!")
    st.info(f"Employee: **{user_data.get('name')}** | PAN: **{user_data.get('pan')}** | DDO TAN: **{user_data.get('ddo_tan')}**")

    if st.button("🔄 Process Another Employee / Slip", use_container_width=True):
        st.session_state.extracted_data = {}
        st.session_state.user_data = {}
        st.session_state.current_page = 'home'
        st.rerun()

# Main Router
def main():
    if st.session_state.current_page == 'home':
        show_home()
    elif st.session_state.current_page == 'upload':
        show_upload()
    elif st.session_state.current_page == 'review':
        show_review()
    elif st.session_state.current_page == 'download':
        show_download()

if __name__ == "__main__":
    main()

import streamlit as st
import sqlite3
from datetime import date
from utils.salary_parser import parse_salary_slip
from utils.pdf_generator import generate_form16_pdf
from utils.tax_calculator import calculate_tax
from utils.trial_watermark import is_trial_mode

# ================= PAGE CONFIGURATION (Must be the first Streamlit command) =================
st.set_page_config(
    page_title="Kosh-Tax | Form 16 & TDS Manager",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

DB_NAME = "kosh_tax_enterprise.sqlite"

# Default Whitelisted PAN Numbers
if 'whitelisted_pans' not in st.session_state:
    st.session_state.whitelisted_pans = {"OSYPK6572D", "ABCDE1234F"}

# ================= DATABASE SETUP WITH CONTEXT MANAGER =================
def init_db():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS employee_profiles (
                pan TEXT PRIMARY KEY, name TEXT, designation TEXT, mobile TEXT, email TEXT, 
                office_name TEXT, district TEXT, gpf_no TEXT, updated_at TEXT
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS ddo_masters (
                tan TEXT PRIMARY KEY, office_address TEXT, officer_name TEXT, father_name TEXT
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS transaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pan TEXT, name TEXT, utr TEXT, payment_type TEXT, timestamp TEXT
            )''')
            conn.commit()
    except Exception as e:
        st.error(f"Database Initialization Error: {e}")

init_db()

# Session State Initialization
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}
if 'user_data' not in st.session_state:
    st.session_state.user_data = {}
if 'payment_status' not in st.session_state:
    st.session_state.payment_status = 'pending'
if 'is_admin_logged' not in st.session_state:
    st.session_state.is_admin_logged = False
if 'mode' not in st.session_state:
    st.session_state.mode = 'regular'

def make_upper(data_dict):
    return {k: (v.upper() if isinstance(v, str) else v) for k, v in data_dict.items()}

# ================= PAGES =================
def show_home():
    st.markdown("# 🏛️ KOSH-TAX | FORM 16 & TDS MANAGEMENT PORTAL")
    st.markdown("### AUTOMATED SALARY MANAGEMENT FOR JHARKHAND GOVERNMENT EMPLOYEES")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 START FORM 16 GENERATOR", use_container_width=True, type="primary"):
            st.session_state.mode = 'regular'
            st.session_state.current_page = 'upload'
            st.rerun()
    with col2:
        if st.button("🎁 START FREE TRIAL", use_container_width=True):
            st.session_state.mode = 'trial'
            st.session_state.current_page = 'upload'
            st.rerun()
    with col3:
        if st.button("🔐 ADMIN LOGIN", use_container_width=True):
            st.session_state.current_page = 'admin_login'
            st.rerun()

def show_admin_login():
    st.title("🔐 ADMIN PORTAL LOGIN")
    st.write("Enter administrator credentials to manage whitelist, UTR transactions, and system databases.")

    with st.form("admin_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Login to Admin Dashboard", type="primary", use_container_width=True)

        if login_btn:
            if username == "admin" and password == "kosh_tax_2026":
                st.session_state.is_admin_logged = True
                st.session_state.current_page = 'admin_dashboard'
                st.success("Login Successful!")
                st.rerun()
            else:
                st.error("Invalid Username or Password! (Default: admin / kosh_tax_2026)")

    if st.button("← Back to Home"):
        st.session_state.current_page = 'home'
        st.rerun()

def show_admin_dashboard():
    if not st.session_state.get('is_admin_logged', False):
        st.warning("Unauthorized Access! Please login first.")
        st.session_state.current_page = 'admin_login'
        st.rerun()
        return

    st.title("🛠️ ADMIN CONTROL PANEL")
    st.write("Welcome Boss! Manage your whitelist, view transaction logs, and control system databases here.")

    tab1, tab2, tab3 = st.tabs(["📋 Whitelist Management", "📊 UTR & Payment Logs", "🗄️ Database Records"])

    with tab1:
        st.subheader("Manage Whitelisted PAN Numbers")
        st.info("Whitelisted PANs can bypass payment and download clean Form 16 PDFs directly.")
        
        st.write("Current Whitelisted PANs:", list(st.session_state.whitelisted_pans))
        
        new_pan = st.text_input("Add New PAN to Whitelist").upper()
        if st.button("Add to Whitelist"):
            if len(new_pan) == 10:
                st.session_state.whitelisted_pans.add(new_pan)
                st.success(f"PAN {new_pan} added successfully!")
                st.rerun()
            else:
                st.error("Enter a valid 10-character PAN number.")

        remove_pan = st.selectbox("Select PAN to Remove", options=[""] + list(st.session_state.whitelisted_pans))
        if st.button("Remove Selected PAN") and remove_pan:
            st.session_state.whitelisted_pans.remove(remove_pan)
            st.success(f"PAN {remove_pan} removed from whitelist.")
            st.rerun()

    with tab2:
        st.subheader("User Transaction & UTR Records")
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                rows = cursor.execute("SELECT pan, name, utr, payment_type, timestamp FROM transaction_logs").fetchall()
                if rows:
                    st.table(rows)
                else:
                    st.write("No transaction logs found yet.")
        except Exception as e:
            st.error(f"Error fetching logs: {e}")

    with tab3:
        st.subheader("Employee Profiles Database")
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cursor = conn.cursor()
                profiles = cursor.execute("SELECT pan, name, designation, mobile, district, gpf_no FROM employee_profiles").fetchall()
                if profiles:
                    st.dataframe(profiles)
                else:
                    st.write("No employee profiles saved in database yet.")
        except Exception as e:
            st.error(f"Error loading profiles: {e}")

    if st.button("🚪 Logout Admin"):
        st.session_state.is_admin_logged = False
        st.session_state.current_page = 'home'
        st.rerun()

def show_upload():
    st.title("📎 STEP 1: UPLOAD SALARY SLIP")
    st.write("Upload your salary slip PDF to auto-extract details. Returning users will have their profiles auto-loaded via PAN.")

    uploaded_file = st.file_uploader("CHOOSE PDF SALARY SLIP", type=['pdf'])

    if uploaded_file:
        with st.spinner("Analyzing salary slip and checking database records..."):
            scanned = parse_salary_slip(uploaded_file)
            scanned = make_upper(scanned)
            
            pan_val = scanned.get('pan', '')
            saved_profile = {}
            if pan_val:
                try:
                    with sqlite3.connect(DB_NAME) as conn:
                        c = conn.cursor()
                        row = c.execute("SELECT mobile, email, office_name, district, designation, gpf_no FROM employee_profiles WHERE pan=?", (pan_val,)).fetchone()
                        if row:
                            # FIXED: Added correct index mapping (row[0], row[1], etc.)
                            saved_profile = {
                                'mobile': row[0] or '', 'email': row[1] or '', 'office_name': row[2] or '',
                                'district': row[3] or 'KHUNTI', 'designation': row[4] or scanned.get('designation', ''),
                                'gpf_no': row[5] or ''
                            }
                except Exception as e:
                    st.error(f"Error loading profile: {e}")

            st.session_state.extracted_data = {**scanned, **saved_profile}
            st.success("✅ SALARY SLIP SCANNED SUCCESSFULLY!")

            st.markdown("### 📊 Extracted Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Name", st.session_state.extracted_data.get('name', 'N/A'))
            with col2:
                st.metric("PAN", st.session_state.extracted_data.get('pan', 'N/A'))
            with col3:
                st.metric("Basic Pay", f"₹{st.session_state.extracted_data.get('basic', 0):,}")
            
            total_entries = len(st.session_state.extracted_data.get('monthly_entries', []))
            st.info(f"📁 Total Salary Blocks/Entries detected: {total_entries}")

            if saved_profile:
                st.info("🔄 RETURNING USER RECOGNIZED! Office details and contact info auto-loaded.")

            if st.button("PROCEED TO REVIEW & ENTRY →", type="primary"):
                st.session_state.current_page = 'review'
                st.rerun()

    if st.button("← BACK TO HOME"):
        st.session_state.current_page = 'home'
        st.rerun()

def show_review():
    st.title("📋 Review Your Data")
    data = st.session_state.extracted_data or {}

        with st.form("review_form"):
        st.subheader("🏢 Employer Details")
        col_d1, col_d2 = st.columns(2)
        
        with col_d1:
            ddo_tan = st.text_input(
                "TAN Number",
                value=data.get('ddo_tan', '')
            )
            ddo_pan = st.text_input(
                "PAN of Deductor / DDO",
                value=data.get('ddo_pan', '')
            )
            employer_address = st.text_area(
                "Name & Address of the Employer",
                value=data.get('employer_address', '')
            )

        with col_d2:
            ddo_officer = st.text_input(
                "DDO Officer Name",
                value=data.get('ddo_officer', '')
            )
            ddo_father = st.text_input(
                "DDO Father Name",
                value=data.get('ddo_father', '')
            )
            ddo_capacity = st.text_input(
                "DDO Capacity",
                value="DISBURSING & DRAWING OFFICER"
            )

        st.subheader("👤 Personal & Employment Details")

        col1, col2 = st.columns(2)
        with col1:
            pan = st.text_input("PAN *", value=data.get('pan', ''))
            name = st.text_input("Full Name *", value=data.get('name', ''))
            designation = st.text_input("Employee Designation", value=data.get('designation', ''))
        with col2:
            mobile = st.text_input("Mobile Number *", value=data.get('mobile', ''))
            email = st.text_input("Email Address *", value=data.get('email', ''))
            office_name = st.text_input("Office / School Name & Address", value=data.get('office_name', ''))

        districts = ["KHUNTI", "RANCHI", "EAST SINGHBHUM", "DHANBAD", "BOKARO", "HAZARIBAGH"]
        current_district = data.get('district', 'KHUNTI').upper()
        default_index = districts.index(current_district) if current_district in districts else 0

        col_3, col_4 = st.columns(2)
        with col_3:
            district = st.selectbox("District", districts, index=default_index)
        with col_4:
            gpf_no = st.text_input("GPF/CPS Number", value=data.get('gpf_no', ''))

        st.subheader("💰 Salary Details (Monthly Summary)")
        col1, col2, col3 = st.columns(3)
        with col1:
            basic = st.number_input("Basic Pay (₹)", value=float(data.get('basic', 0)))
            da = st.number_input("DA (₹)", value=float(data.get('da', 0)))
        with col2:
            hra = st.number_input("HRA (₹)", value=float(data.get('hra', 0)))
            medical = st.number_input("Medical (₹)", value=float(data.get('medical', 0)))
        with col3:
            gpf = st.number_input("GPF (₹)", value=float(data.get('gpf', 0)))
            tds = st.number_input("TDS (₹)", value=float(data.get('tds', 0)))

        st.subheader("📊 Tax Details")
        col1, col2 = st.columns(2)
        with col1:
            assessment_year = st.selectbox("Assessment Year", ["AY 2025-26 (FY 2024-25)", "AY 2026-27 (FY 2025-26)"])
        with col2:
            tax_regime = st.selectbox("Tax Regime", ["NEW REGIME", "OLD REGIME"])

        submitted = st.form_submit_button("Save & Proceed to Download →", type="primary", use_container_width=True)

        if submitted:
            # 1. Base user data dictionary
            base_user_data = {
    # Employee
    'pan': pan.upper(),
    'name': name.upper(),
    'designation': designation.upper(),

    'mobile': mobile,
    'email': email,
    'office_name': office_name.upper(),
    'district': district,
    'gpf_no': gpf_no.upper(),

    # DDO / Deductor
    'ddo_pan': ddo_pan.upper(),
    'ddo_tan': ddo_tan.upper(),
    'ddo_officer': ddo_officer.upper(),
    'ddo_father': ddo_father.upper(),
    'ddo_capacity': ddo_capacity.upper(),

    'employer_address': employer_address.upper(),

    # Salary
    'basic': basic,
    'da': da,
    'hra': hra,
    'medical': medical,
    'gpf': gpf,
    'tds': tds,

    # Tax
    'assessment_year': assessment_year,
    'tax_regime': tax_regime,

    # Monthly salary entries
    'monthly_entries': data.get('monthly_entries', [])
}
            
            # 2. FIXED: Integrated calculate_tax to compute tax details automatically
            try:
                tax_computations = calculate_tax(base_user_data)
                st.session_state.user_data = {**base_user_data, **tax_computations}
            except Exception as tax_err:
                st.error(f"Tax Calculation Error: {tax_err}")
                st.session_state.user_data = base_user_data

                        # Auto-save to SQLite Database
            try:
                with sqlite3.connect(DB_NAME) as conn:
                    c = conn.cursor()
                    # Employee Data Save
                    c.execute('''INSERT OR REPLACE INTO employee_profiles(pan, name, designation, mobile, email, office_name, district, gpf_no, updated_at)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (pan.upper(), name.upper(), designation.upper(), mobile, email, office_name.upper(), district, gpf_no.upper(), str(date.today())))
                    
                    # Employer/DDO Data Save
                    if ddo_tan.strip():
                        c.execute('''INSERT OR REPLACE INTO ddo_masters(tan, office_address, officer_name, father_name)
                                     VALUES (?, ?, ?, ?)''',
                                  (ddo_tan.upper(), employer_address.upper(), ddo_officer.upper(), ddo_father.upper()))
                    
                    conn.commit()
            except Exception as e:
                st.error(f"Database Save Error: {e}")


            # Check Whitelist bypass status
            is_whitelisted = pan.upper() in st.session_state.whitelisted_pans
            if is_whitelisted or st.session_state.mode == 'trial':
                st.session_state.payment_status = 'bypassed'
            else:
                st.session_state.payment_status = 'pending'
                
            st.session_state.current_page = 'download_pdf'
            st.rerun()

    if st.button("← Back to Upload"):
        st.session_state.current_page = 'upload'
        st.rerun()

def show_download_pdf():
    st.title("📥 Step 3: Download Form 16")
    if not st.session_state.user_data:
        st.warning("No data found. Please complete the review form first.")
        if st.button("Go to Review"):
            st.session_state.current_page = 'review'
            st.rerun()
        return

    user_data = st.session_state.user_data
    is_trial = st.session_state.mode == 'trial'

    if st.session_state.payment_status == 'pending':
        st.subheader("💳 Secure Payment Required")
        st.info("Your PAN is not whitelisted. Please complete the payment to generate a clean PDF.")
        utr_input = st.text_input("Enter 12-Digit UTR / Transaction Number")
        if st.button("Verify & Activate Download"):
            if len(utr_input) >= 12:
                try:
                    with sqlite3.connect(DB_NAME) as conn:
                        c = conn.cursor()
                        c.execute("INSERT INTO transaction_logs (pan, name, utr, payment_type, timestamp) VALUES (?, ?, ?, ?, ?)",
                                  (user_data['pan'], user_data['name'], utr_input, "Gateway", str(date.today())))
                        conn.commit()
                    st.session_state.payment_status = 'completed'
                    st.success("Payment recorded! You can now download the PDF.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to log transaction: {e}")
            else:
                st.error("Please enter a valid Transaction/UTR number.")
    else:
        if is_trial:
            st.warning("⚠️ Running in FREE TRIAL Mode. Generated PDF will contain a watermark.")
        else:
            st.success("🎉 Access Granted! Clean PDF copy ready for deployment.")

        with st.spinner("Generating Form 16 PDF..."):
            pdf_bytes = generate_form16_pdf(user_data, is_trial=is_trial)

            st.download_button(
                label="📥 Download Form 16 PDF",
                data=pdf_bytes,
                file_name=f"Form16_{user_data['pan']}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    if st.button("← Start Over (Home)"):
        st.session_state.current_page = 'home'
        st.session_state.user_data = {}
        st.rerun()

# ================= APP ROUTER =================
def main():
    if st.session_state.current_page == 'home':
        show_home()
    elif st.session_state.current_page == 'admin_login':
        show_admin_login()
    elif st.session_state.current_page == 'admin_dashboard':
        show_admin_dashboard()
    elif st.session_state.current_page == 'upload':
        show_upload()
    elif st.session_state.current_page == 'review':
        show_review()
    elif st.session_state.current_page == 'download_pdf':
        show_download_pdf()

    st.markdown("---")
    st.markdown("<p style='text-align: center; color: gray; font-size: 12px;'>DEVELOPED & DESIGNED BY @ NITIN MALLICK</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

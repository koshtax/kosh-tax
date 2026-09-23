import streamlit as st
import sqlite3
from datetime import date
from utils.salary_parser import parse_salary_slip
from utils.pdf_generator import generate_form16_pdf
from utils.tax_calculator import calculate_tax
from utils.trial_watermark import is_trial_mode

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

# Session State Initialization
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = {}
if 'user_data' not in st.session_state:
    st.session_state.user_data = {}
if 'payment_status' not in st.session_state:
    st.session_state.payment_status = 'pending'

def make_upper(data_dict):
    return {k: (v.upper() if isinstance(v, str) else v) for k, v in data_dict.items()}

# ================= PAGES =================
def show_home():
    st.markdown("# 🏛️ KOSH-TAX | FORM 16 & TDS MANAGEMENT PORTAL")
    st.markdown("### AUTOMATED SALARY MANAGEMENT FOR JHARKHAND GOVERNMENT EMPLOYEES")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 START FORM 16 GENERATOR", use_container_width=True, type="primary"):
            st.session_state.current_page = 'upload'
            st.rerun()
    with col2:
        if st.button("🎁 START FREE TRIAL", use_container_width=True):
            st.session_state.mode = 'trial'
            st.session_state.current_page = 'upload'
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
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                row = c.execute("SELECT mobile, email, office_name, district, designation, gpf_no FROM employee_profiles WHERE pan=?", (pan_val,)).fetchone()
                conn.close()
                if row:
                    saved_profile = {
                        'mobile': row[0] or '', 'email': row[1] or '', 'office_name': row[2] or '',
                        'district': row[3] or 'KHUNTI', 'designation': row[4] or scanned.get('designation', ''),
                        'gpf_no': row[5] or ''
                    }

            st.session_state.extracted_data = {**scanned, **saved_profile}
            st.success("✅ SALARY SLIP SCANNED SUCCESSFULLY!")

            # Display Extracted Summary on same page
            st.markdown("### 📊 Extracted Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Name", st.session_state.extracted_data.get('name', 'N/A'))
            with col2:
                st.metric("PAN", st.session_state.extracted_data.get('pan', 'N/A'))
            with col3:
                st.metric("Basic Pay", f"₹{st.session_state.extracted_data.get('basic', 0):,}")
            
            if saved_profile:
                st.info("🔄 RETURNING USER RECOGNIZED! Office details and contact info auto-loaded from previous records.")

            if st.button("PROCEED TO REVIEW & ENTRY →", type="primary"):
                st.session_state.current_page = 'review'
                st.rerun()

    if st.button("← BACK TO HOME"):
        st.session_state.current_page = 'home'
        st.rerun()


# Review Page
def show_review():
    st.title("✏️ STEP 2: REVIEW & EDIT DETAILS")
    data = st.session_state.user_data

    with st.form("review_form", clear_on_submit=False):
        st.markdown("### Personal & Official Details")
        data['name'] = st.text_input("Employee Name", value=data.get('name', ''), key="rev_name")
        data['pan'] = st.text_input("PAN Number", value=data.get('pan', ''), key="rev_pan")
        data['designation'] = st.text_input("Designation", value=data.get('designation', ''), key="rev_desig")
        data['office_name'] = st.text_input("Office / School Name", value=data.get('office_name', 'Utkramit +2 High School, Tubil'), key="rev_office")
        data['district'] = st.text_input("District / Treasury", value=data.get('district', 'Khunti'), key="rev_dist")
        data['ddo_tan'] = st.text_input("DDO TAN", value=data.get('ddo_tan', 'RANC01234E'), key="rev_tan")
        data['employer_address'] = st.text_area("Employer Address", value=data.get('employer_address', 'District Education Office, Khunti, Jharkhand'), key="rev_emp_addr")
        data['ddo_officer'] = st.text_input("DDO Officer Name", value=data.get('ddo_officer', 'DDO Officer'), key="rev_ddo_name")
        data['ddo_father'] = st.text_input("DDO Father's Name", value=data.get('ddo_father', ''), key="rev_ddo_father")

        st.markdown("### Salary Details (Monthly)")
        data['basic'] = st.number_input("Basic Pay (₹)", value=float(data.get('basic', 0)), key="rev_basic")
        data['da'] = st.number_input("DA (₹)", value=float(data.get('da', 0)), key="rev_da")
        data['hra'] = st.number_input("HRA (₹)", value=float(data.get('hra', 0)), key="rev_hra")
        data['medical'] = st.number_input("Medical (₹)", value=float(data.get('medical', 1000)), key="rev_med")
        data['gpf'] = st.number_input("GPF / Deduction (₹)", value=float(data.get('gpf', 5000)), key="rev_gpf")
        data['tds'] = st.number_input("TDS / Income Tax (₹)", value=float(data.get('tds', 0)), key="rev_tds")

        st.markdown("### Tax Details")
        assessment_year = st.selectbox(
            "Assessment Year", 
            ["AY 2025-26 (FY 2024-25)", "AY 2026-27 (FY 2025-26)"], 
            index=0 if "2025" in data.get('assessment_year', '') else 1,
            key="rev_ay"
        )
        tax_regime = st.selectbox(
            "Tax Regime", 
            ["NEW REGIME", "OLD REGIME"], 
            index=0 if "NEW" in data.get('tax_regime', '') else 1,
            key="rev_regime"
        )

        data['assessment_year'] = assessment_year
        data['tax_regime'] = tax_regime

        submitted = st.form_submit_button("Next: Payment →", type="primary", use_container_width=True, key="form_next_payment_btn")
        if submitted:
            st.session_state.user_data = data
            st.session_state.current_page = 'payment'
            st.rerun()

    if st.button("← Back to Upload", key="rev_back_btn"):
        st.session_state.current_page = 'upload'
        st.rerun()

    
def show_payment():
    st.title("💰 STEP 3: PAYMENT")
    mode = st.session_state.get('mode', 'paid')

    if mode == 'trial' or is_trial_mode(st.session_state.get('payment_status')):
        st.success("🎁 FREE TRIAL MODE ACTIVE")
        if st.button("PROCEED TO DOWNLOAD (TRIAL)", key="trial_download_btn"):
            st.session_state.payment_status = 'trial'
            st.session_state.current_page = 'download'
            st.rerun()
    else:
        st.markdown("### CHOOSE PAYMENT METHOD")
        tab1, tab2, tab3 = st.tabs(["📱 UPI PAYMENT", "💵 CASH PAYMENT", "🎁 FREE TRIAL"])

        with tab1:
            st.markdown("**AMOUNT: ₹99**\n\nUPI ID: `nitinmallick111-1@okicici`")
            utr = st.text_input("ENTER 12-DIGIT UTR NUMBER", max_chars=12)
        if st.button("VERIFY & DOWNLOAD", key="verify_paid_btn"):
                if len(utr) == 12:
                    st.session_state.payment_status = 'paid'
                    st.session_state.utr = utr
                    st.session_state.current_page = 'download'
                    st.rerun()
                else:
                    st.error("UTR MUST BE 12 DIGITS")

        with tab2:
            st.markdown("**AMOUNT: ₹99**\n\nPAY CASH AT ADMIN OFFICE.")
            if st.button("I PAID CASH", key="cash_paid_btn"):
                st.session_state.payment_status = 'cash'
                st.session_state.current_page = 'download'
                st.rerun()

        with tab3:
            st.markdown("**FREE TRIAL COPY** (WATERMARKED)")
            if st.button("DOWNLOAD TRIAL", key="tab3_trial_btn"):
                st.session_state.payment_status = 'trial'
                st.session_state.current_page = 'download'
                st.rerun()

    if st.button("← BACK", key="payment_back_btn"):
        st.session_state.current_page = 'review'
        st.rerun()

def show_download():
    st.title("📄 STEP 4: DOWNLOAD FORM 16")
    payment_status = st.session_state.get('payment_status', 'pending')
    user_data = st.session_state.get('user_data', {})

    if payment_status == 'trial':
        st.warning("⚠️ **TRIAL COPY** - FOR VERIFICATION ONLY")
    else:
        st.success("✅ PAYMENT VERIFIED SUCCESSFULLY!")

    with st.spinner("Generating Form 16 PDF in Uppercase..."):
        pdf_bytes = generate_form16_pdf(user_data, is_trial=(payment_status == 'trial'))

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
        st.session_state.payment_status = 'pending'
        st.session_state.current_page = 'home'
        st.rerun()

def main():
    if st.session_state.current_page == 'home':
        show_home()
    elif st.session_state.current_page == 'upload':
        show_upload()
    elif st.session_state.current_page == 'review':
        show_review()
    elif st.session_state.current_page == 'payment':
        show_payment()
    elif st.session_state.current_page == 'download':
        show_download()

    # Footer requirement
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: gray; font-size: 12px;'>DEVELOPED & DESIGNED BY @ NITIN MALLICK</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

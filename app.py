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
    st.title("📋 Review Your Data")

    data = st.session_state.extracted_data or {}

    with st.form("review_form"):
        # --- Employer Details Section ---
        st.subheader("🏢 Employer Details")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            ddo_tan = st.text_input("TAN Number", value=data.get('ddo_tan', ''))
            employer_address = st.text_area("Name & Address of the Employer", value=data.get('employer_address', ''))
        with col_d2:
            ddo_officer = st.text_input("Ddo Officer Name", value=data.get('ddo_officer', ''))
            ddo_father = st.text_input("Ddo Father Name", value=data.get('ddo_father', ''))
            st.text_input("Designation", value="Drawing and Disbursing Officer", disabled=True)

        # --- Personal & Employment Details ---
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

        col_3, col_4 = st.columns(2)
        with col_3:
            district = st.selectbox(
                "District",
                ["KHUNTI", "RANCHI", "EAST SINGHBHUM", "DHANBAD", "BOKARO", "HAZARIBAGH"],
                index=0 if data.get('district') == 'KHUNTI' else 0
            )

        # Salary Details
        st.subheader("💰 Salary Details (Monthly)")
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

        # Tax Details
        st.subheader("📊 Tax Details")
        col1, col2 = st.columns(2)
        with col1:
            assessment_year = st.selectbox(
                "Assessment Year",
                ["AY 2025-26 (FY 2024-25)", "AY 2026-27 (FY 2025-26)"]
            )
        with col2:
            tax_regime = st.selectbox(
                "Tax Regime",
                ["NEW REGIME", "OLD REGIME"]
            )

        submitted = st.form_submit_button("Next: Payment →", type="primary", use_container_width=True)

        if submitted:
            # Save to session
            st.session_state.user_data = {
                'pan': pan,
                'name': name,
                'designation': designation,
                'mobile': mobile,
                'email': email,
                'office_name': office_name,
                'district': district,
                'ddo_tan': ddo_tan,
                'employer_address': employer_address,
                'ddo_officer': ddo_officer,
                'ddo_father': ddo_father,
                'basic': basic,
                'da': da,
                'hra': hra,
                'medical': medical,
                'gpf': gpf,
                'tds': tds,
                'assessment_year': assessment_year,
                'tax_regime': tax_regime
            }
                    if st.button("Next: Payment →"):
        st.session_state.current_page = 'payment'
        st.rerun()


    if st.button("← Back"):
        go_upload()


def show_payment():
    st.title("💰 STEP 3: PAYMENT")
    mode = st.session_state.get('mode', 'paid')

    if mode == 'trial' or is_trial_mode(st.session_state.get('payment_status')):
        st.success("🎁 FREE TRIAL MODE ACTIVE")
        if st.button("PROCEED TO DOWNLOAD (TRIAL)", type="primary", use_container_width=True):
            st.session_state.payment_status = 'trial'
            st.session_state.current_page = 'download'
            st.rerun()
    else:
        st.markdown("### CHOOSE PAYMENT METHOD")
        tab1, tab2, tab3 = st.tabs(["📱 UPI PAYMENT", "💵 CASH PAYMENT", "🎁 FREE TRIAL"])

        with tab1:
            st.markdown("**AMOUNT: ₹99**\n\nUPI ID: `nitinmallick111-1@okicici`")
            utr = st.text_input("ENTER 12-DIGIT UTR NUMBER", max_chars=12)
            if st.button("VERIFY & DOWNLOAD", type="primary", use_container_width=True):
                if len(utr) == 12:
                    st.session_state.payment_status = 'paid'
                    st.session_state.utr = utr
                    st.session_state.current_page = 'download'
                    st.rerun()
                else:
                    st.error("UTR MUST BE 12 DIGITS")

        with tab2:
            st.markdown("**AMOUNT: ₹99**\n\nPAY CASH AT ADMIN OFFICE.")
            if st.button("I PAID CASH", use_container_width=True):
                st.session_state.payment_status = 'cash'
                st.session_state.current_page = 'download'
                st.rerun()

        with tab3:
            st.markdown("**FREE TRIAL COPY** (WATERMARKED)")
            if st.button("DOWNLOAD TRIAL", use_container_width=True):
                st.session_state.payment_status = 'trial'
                st.session_state.current_page = 'download'
                st.rerun()

    if st.button("← BACK"):
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

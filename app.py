import streamlit as st
import qrcode
from io import BytesIO
import sqlite3
from datetime import date
import re
import os
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

# Regex Patterns for Strict Validation
PAN_REGEX = r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$"
EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

# ================= DATABASE SETUP =================
def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=15, check_same_thread=False)

def init_db():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS employee_profiles (
                pan TEXT PRIMARY KEY, name TEXT, designation TEXT, mobile TEXT, email TEXT, 
                office_name TEXT, district TEXT, gpf_no TEXT, updated_at TEXT
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS ddo_masters (
                tan TEXT PRIMARY KEY, office_address TEXT, officer_name TEXT, father_name TEXT
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS transaction_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pan TEXT, name TEXT, utr TEXT, 
                payment_type TEXT, timestamp TEXT, status TEXT
            )''')
            
            # Migration check
            try:
                c.execute("ALTER TABLE transaction_logs ADD COLUMN status TEXT DEFAULT 'pending'")
            except sqlite3.OperationalError:
                pass 
            
            c.execute('''CREATE TABLE IF NOT EXISTS whitelist_pans (
                pan TEXT PRIMARY KEY
            )''')
            
            c.execute("SELECT count(*) FROM whitelist_pans")
            if c.fetchone()[0] == 0:
                c.executemany("INSERT INTO whitelist_pans (pan) VALUES (?)", [("OSYPK6572D",), ("ABCDE1234F",)])
            conn.commit()
    except Exception as e:
        st.error(f"Database Initialization Error: {e}")

init_db()

def load_whitelist():
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            rows = c.execute("SELECT pan FROM whitelist_pans").fetchall()
            return set(row[0] for row in rows)
    except Exception:
        return {"OSYPK6572D", "ABCDE1234F"}

if 'whitelisted_pans' not in st.session_state:
    st.session_state.whitelisted_pans = load_whitelist()

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

def reset_user_session():
    """Clears previous user data when starting a new session"""
    st.session_state.extracted_data = {}
    st.session_state.user_data = {}
    st.session_state.payment_status = 'pending'

def make_upper(data_dict):
    return {k: (v.upper() if isinstance(v, str) else v) for k, v in data_dict.items()}

# ================= PAGES =================
def show_home():
    st.markdown("# 🏛️ KOSH-TAX | FORM 16 & TDS MANAGEMENT PORTAL")
    st.markdown("### AUTOMATED SALARY MANAGEMENT FOR JHARKHAND GOVERNMENT EMPLOYEES")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🚀 START FORM 16 GENERATOR", use_container_width=True, type="primary"):
            reset_user_session()
            st.session_state.mode = 'regular'
            st.session_state.current_page = 'upload'
            st.rerun()
    with col2:
        if st.button("🎁 START FREE TRIAL", use_container_width=True):
            reset_user_session()
            st.session_state.mode = 'trial'
            st.session_state.current_page = 'upload'
            st.rerun()
    with col3:
        if st.button("🔐 ADMIN LOGIN", use_container_width=True):
            st.session_state.current_page = 'admin_login'
            st.rerun()

def show_admin_login():
    st.title("🔐 ADMIN PORTAL LOGIN")
    with st.form("admin_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Login to Admin Dashboard", type="primary", use_container_width=True)

        if login_btn:
            try:
                valid_user = st.secrets["admin_credentials"]["username"]
                valid_pass = st.secrets["admin_credentials"]["password"]
            except KeyError:
                st.error("⚠️ Secrets not configured properly. Check .streamlit/secrets.toml")
                return

            if username == valid_user and password == valid_pass:
                st.session_state.is_admin_logged = True
                st.session_state.current_page = 'admin_dashboard'
                st.success("Login Successful!")
                st.rerun()
            else:
                st.error("❌ Invalid Username or Password!")

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
    tab1, tab2, tab3 = st.tabs(["📊 UTR Approvals", "📋 Whitelist Management", "🗄️ Database Records & Backup"])

    with tab1:
        st.subheader("Action Required: Pending UTRs")
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                pending_rows = cursor.execute("SELECT id, pan, name, utr, timestamp FROM transaction_logs WHERE status='pending'").fetchall()
                
                if pending_rows:
                    for row in pending_rows:
                        with st.container():
                            col_info, col_app, col_rej = st.columns([4, 1, 1])
                            with col_info:
                                st.write(f"**PAN:** {row[1]} | **Name:** {row[2]}")
                                st.write(f"**UTR:** `{row[3]}` | **Date:** {row[4]}")
                            with col_app:
                                if st.button("✅ Approve", key=f"app_{row[0]}", type="primary"):
                                    cursor.execute("UPDATE transaction_logs SET status='approved' WHERE id=?", (row[0],))
                                    conn.commit()
                                    st.success(f"Approved UTR for {row[1]}")
                                    st.rerun()
                            with col_rej:
                                if st.button("❌ Reject", key=f"rej_{row[0]}"):
                                    cursor.execute("UPDATE transaction_logs SET status='rejected' WHERE id=?", (row[0],))
                                    conn.commit()
                                    st.error(f"Rejected UTR for {row[1]}")
                                    st.rerun()
                            st.markdown("---")
                else:
                    st.success("🎉 No pending UTRs! You are all caught up.")

                st.subheader("All Transaction Records")
                all_logs = cursor.execute("SELECT pan, name, utr, payment_type, status, timestamp FROM transaction_logs ORDER BY id DESC").fetchall()
                if all_logs:
                    st.dataframe([{"PAN": r[0], "Name": r[1], "UTR": r[2], "Type": r[3], "Status": r[4], "Date": r[5]} for r in all_logs])
        except Exception as e:
            st.error(f"Error fetching logs: {e}")

    with tab2:
        st.subheader("Manage Whitelisted PAN Numbers")
        new_pan = st.text_input("Add New PAN to Whitelist").upper()
        if st.button("Add to Whitelist"):
            if re.match(PAN_REGEX, new_pan):
                try:
                    with get_db_connection() as conn:
                        conn.cursor().execute("INSERT OR IGNORE INTO whitelist_pans (pan) VALUES (?)", (new_pan,))
                        conn.commit()
                    st.session_state.whitelisted_pans.add(new_pan)
                    st.success(f"PAN {new_pan} added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.error("❌ Enter a valid PAN Number (e.g., ABCDE1234F).")

        remove_pan = st.selectbox("Select PAN to Remove", options=[""] + list(st.session_state.whitelisted_pans))
        if st.button("Remove Selected PAN") and remove_pan:
            try:
                with get_db_connection() as conn:
                    conn.cursor().execute("DELETE FROM whitelist_pans WHERE pan=?", (remove_pan,))
                    conn.commit()
                st.session_state.whitelisted_pans.remove(remove_pan)
                st.success(f"PAN {remove_pan} removed.")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    with tab3:
        st.subheader("Employee & Employer Database")
        
        if os.path.exists(DB_NAME):
            with open(DB_NAME, "rb") as fp:
                st.download_button(
                    label="💾 Download Full Database Backup",
                    data=fp,
                    file_name=f"kosh_tax_backup_{date.today()}.sqlite",
                    mime="application/x-sqlite3",
                    type="primary"
                )
                st.caption("Regularly download this file if hosting on temporary cloud platforms.")
                
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                profiles = cursor.execute("SELECT pan, name, designation, district FROM employee_profiles").fetchall()
                if profiles:
                    st.write("Employee Profiles (Preview)")
                    st.dataframe([{"PAN": r[0], "Name": r[1], "Designation": r[2], "District": r[3]} for r in profiles])
                
                ddo_records = cursor.execute("SELECT tan, office_address, officer_name, father_name FROM ddo_masters").fetchall()
                if ddo_records:
                    st.write("DDO Masters Database")
                    st.dataframe(ddo_records)
        except Exception as e:
            st.error(f"Error loading database records: {e}")

    if st.button("🚪 Logout Admin"):
        st.session_state.is_admin_logged = False
        st.session_state.current_page = 'home'
        st.rerun()

def show_upload():
    st.title("📎 STEP 1: UPLOAD SALARY SLIP")
    st.write("Upload your salary slip PDF to auto-extract details. Employer details will be auto-loaded if available.")

    uploaded_file = st.file_uploader("CHOOSE PDF SALARY SLIP", type=['pdf'])

    if uploaded_file:
        with st.spinner("Analyzing salary slip and checking database records..."):
            scanned = parse_salary_slip(uploaded_file)
            scanned = make_upper(scanned)
            
            pan_val = scanned.get('pan', '')
            tan_val = scanned.get('ddo_tan', '')
            saved_profile = {}
            
            try:
                with get_db_connection() as conn:
                    c = conn.cursor()
                    if pan_val:
                        row = c.execute("SELECT office_name, district, designation FROM employee_profiles WHERE pan=?", (pan_val,)).fetchone()
                        if row:
                            saved_profile.update({
                                'office_name': row[0] or '',
                                'district': row[1] or 'KHUNTI',
                                'designation': row[2] or scanned.get('designation', '')
                            })
                            st.info("🔄 PROFILE DETECTED! Public details auto-loaded. Please enter your Mobile & Email manually for security.")
                    
                    if tan_val:
                        ddo_row = c.execute("SELECT office_address, officer_name, father_name FROM ddo_masters WHERE tan=?", (tan_val,)).fetchone()
                        if ddo_row:
                            saved_profile.update({
                                'employer_address': ddo_row[0] or '',
                                'ddo_officer': ddo_row[1] or '',
                                'ddo_father': ddo_row[2] or ''
                            })
                            st.success(f"🏢 DDO Data loaded automatically for TAN: {tan_val}.")
                            
            except Exception as e:
                st.error(f"Error loading data from database: {e}")

            st.session_state.extracted_data = {**scanned, **saved_profile}
            st.success("✅ SALARY SLIP SCANNED SUCCESSFULLY!")

            # ----------- YAHAN SE NAYA CODE ADD KAREIN -----------
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
            # ----------- YAHAN TAK NAYA CODE ADD KAREIN -----------

            if st.button("PROCEED TO REVIEW & ENTRY →", type="primary"):
                st.session_state.current_page = 'review'
                st.rerun()


    if st.button("← BACK TO HOME"):
        st.session_state.current_page = 'home'
        st.rerun()

def show_review():
    st.title("📋 Review Your Data")
    st.write("⚠️ *All fields are mandatory. Strict format validation is active.*")
    
    data = st.session_state.extracted_data or {}

    with st.form("review_form"):
        st.subheader("🏢 Employer Details")
        col_d1, col_d2 = st.columns(2)
        
        with col_d1:
            ddo_tan = st.text_input("TAN Number *", value=data.get('ddo_tan', ''))
            ddo_pan = st.text_input("PAN of Deductor / DDO", value=data.get('ddo_pan', ''))
            employer_address = st.text_area("Name & Address of the Employer *", value=data.get('employer_address', ''))
            
        with col_d2:
            ddo_officer = st.text_input("DDO Officer Name *", value=data.get('ddo_officer', ''))
            ddo_father = st.text_input("DDO Father Name *", value=data.get('ddo_father', ''))
            ddo_capacity = st.text_input("DDO Capacity", value="DISBURSING & DRAWING OFFICER")

        st.subheader("👤 Personal & Employment Details")
        col1, col2 = st.columns(2)
        with col1:
            pan = st.text_input("PAN *", value=data.get('pan', ''))
            name = st.text_input("Full Name *", value=data.get('name', ''))
            designation = st.text_input("Employee Designation *", value=data.get('designation', ''))
            gpf_no = st.text_input("GPF/CPS Number *", value=data.get('gpf_no', ''))
        with col2:
            mobile = st.text_input("Mobile Number (10 digits) *", value=data.get('mobile', ''), max_chars=10)
            email_val = data.get('email', '')
            if email_val and "@" not in email_val:
                email_val += "@gmail.com"
            email = st.text_input("Email Address *", value=email_val, placeholder="e.g. rahul@gmail.com")
            
            office_name = st.text_input("Office / School Name & Address *", value=data.get('office_name', ''))
            districts = ["KHUNTI", "RANCHI", "EAST SINGHBHUM", "DHANBAD", "BOKARO", "HAZARIBAGH"]
            current_district = data.get('district', 'KHUNTI').upper()
            default_index = districts.index(current_district) if current_district in districts else 0
            district = st.selectbox("District *", districts, index=default_index)

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
            errors = []
            pan_cleaned = pan.strip().upper()
            email_cleaned = email.strip().lower()
            if email_cleaned and "@" not in email_cleaned:
                email_cleaned += "@gmail.com"
            
            if not re.match(PAN_REGEX, pan_cleaned): errors.append("Invalid PAN Format (Must be 5 Letters, 4 Digits, 1 Letter).")
            if not re.match(EMAIL_REGEX, email_cleaned): errors.append("Invalid Email Address Format.")
            
            if not name.strip(): errors.append("Full Name is required.")
            if not designation.strip(): errors.append("Employee Designation is required.")
            if not office_name.strip(): errors.append("Office/School Name & Address is required.")
            if not gpf_no.strip(): errors.append("GPF/CPS Number is required.")
            
            if not ddo_tan.strip(): errors.append("TAN Number is required.")
            if not employer_address.strip(): errors.append("Employer Name & Address is required.")
            if not ddo_officer.strip(): errors.append("DDO Officer Name is required.")
            if not ddo_father.strip(): errors.append("DDO Father Name is required.")

            if not mobile.strip() or not (mobile.strip().isdigit() and len(mobile.strip()) == 10):
                errors.append("Mobile Number must be exactly 10 numeric digits.")
                
            if errors:
                for err in errors:
                    st.error(f"❌ {err}")
            else:
                base_user_data = {
                    'pan': pan_cleaned, 'name': name.upper(), 'designation': designation.upper(),
                    'mobile': mobile.strip(), 'email': email_cleaned, 'office_name': office_name.upper(),
                    'district': district, 'gpf_no': gpf_no.upper(), 
                    'ddo_tan': ddo_tan.upper(), 'ddo_pan': ddo_pan.upper(),
                    'employer_address': employer_address.upper(), 'ddo_officer': ddo_officer.upper(),
                    'ddo_father': ddo_father.upper(), 'ddo_capacity': ddo_capacity.upper(),
                    'basic': basic, 'da': da, 'hra': hra,
                    'medical': medical, 'gpf': gpf, 'tds': tds, 'assessment_year': assessment_year,
                    'tax_regime': tax_regime, 'monthly_entries': data.get('monthly_entries', [])
                }
                
                try:
                    tax_computations = calculate_tax(base_user_data)
                    st.session_state.user_data = {**base_user_data, **tax_computations}
                except Exception as tax_err:
                    st.error(f"Tax Calculation Error: {tax_err}")
                    st.session_state.user_data = base_user_data

                try:
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        c.execute('''INSERT OR REPLACE INTO employee_profiles(pan, name, designation, mobile, email, office_name, district, gpf_no, updated_at)
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (pan_cleaned, name.upper(), designation.upper(), mobile.strip(), email_cleaned, office_name.upper(), district, gpf_no.upper(), str(date.today())))
                        
                        c.execute('''INSERT OR REPLACE INTO ddo_masters(tan, office_address, officer_name, father_name)
                                     VALUES (?, ?, ?, ?)''',
                                  (ddo_tan.upper(), employer_address.upper(), ddo_officer.upper(), ddo_father.upper()))
                        conn.commit()
                except Exception as e:
                    st.error(f"Database Save Error: {e}")

                is_whitelisted = pan_cleaned in st.session_state.whitelisted_pans
                if is_whitelisted or st.session_state.mode == 'trial':
                    st.session_state.payment_status = 'bypassed'
                else:
                    try:
                        with get_db_connection() as conn:
                            c = conn.cursor()
                            txn = c.execute("SELECT status FROM transaction_logs WHERE pan=? ORDER BY id DESC LIMIT 1", (pan_cleaned,)).fetchone()
                            if txn:
                                if txn[0] == 'approved': st.session_state.payment_status = 'completed'
                                elif txn[0] == 'pending': st.session_state.payment_status = 'awaiting_approval'
                                else: st.session_state.payment_status = 'pending'
                            else:
                                st.session_state.payment_status = 'pending'
                    except:
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
    is_whitelisted = user_data['pan'] in st.session_state.whitelisted_pans

if st.session_state.payment_status == 'pending':
    st.subheader("💳 Secure Payment Required")
    st.info("Your PAN is not whitelisted. Please complete the payment to generate a clean PDF.")
    st.markdown("**Note: Enter exact 12-digit UPI UTR...")
        
        # ==========================================
        # YAHAN SE NAYA QR CODE WALA BLOCK ADD KAREIN
        # ==========================================
    col_qr, col_info = st.columns([1, 2])
    with col_qr:
        upi_choice = st.radio(
            "Select Payment Gateway:", 
            ["UPI Option 1 (PhonePe/SBI)", "UPI Option 2 (Paytm/HDFC)"]
        )
            
        if upi_choice == "UPI Option 1 (PhonePe/SBI)":
            upi_id = "aapka_pehla_upi@bank"        # Apna primary UPI ID dalein
            payee_name = "Nitin Mallick"
        else:
            upi_id = "aapka_dusra_upi@bank"        # Apna secondary UPI ID dalein
            payee_name = "Nitin Mallick"
            
        upi_url = f"upi://pay?pa={upi_id}&pn={payee_name}&cu=INR"
            
        qr = qrcode.make(upi_url)
        img_buffer = BytesIO()
        qr.save(img_buffer, format="PNG")
            
        st.image(img_buffer, caption=f"Scan to Pay: {upi_id}", width=200)
                
    with col_info:
        st.markdown("### Payment Instructions:")
        st.markdown("1. Select your preferred Payment Gateway from the left.")
        st.markdown("2. Open PhonePe, Google Pay, or Paytm and scan the generated QR code.")
        st.markdown("3. After successful payment, copy the **12-Digit UTR / Transaction ID**.")
        st.markdown("4. Paste it below to unlock your PDF.")
        # ==========================================
        # YAHAN TAK NAYA CODE HAI
        # ==========================================

        # Yahan se aapka purana UTR wala code continue hoga jo screenshot mein hai:
        utr_input = st.text_input("Enter 12-Digit UTR / ...")
        
        if st.button("Submit UTR for Verification"):
            utr_cleaned = utr_input.strip()
            # ... baaki ka aapka purana code ...

        
        utr_input = st.text_input("Enter 12-Digit UTR / Transaction Number", max_chars=12)
        
        if st.button("Submit UTR for Verification"):
            utr_cleaned = utr_input.strip()
            if len(utr_cleaned) == 12 and utr_cleaned.isdigit():
                try:
                    with get_db_connection() as conn:
                        c = conn.cursor()
                        existing_utr = c.execute("SELECT pan FROM transaction_logs WHERE utr=?", (utr_cleaned,)).fetchone()
                        
                        if existing_utr:
                            st.error("❌ This UTR has already been used! Please enter a valid unique UTR.")
                        else:
                            c.execute("INSERT INTO transaction_logs (pan, name, utr, payment_type, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
                                      (user_data['pan'], user_data['name'], utr_cleaned, "Manual_UPI", str(date.today()), "pending"))
                            conn.commit()
                            
                            st.session_state.payment_status = 'awaiting_approval'
                            st.success("✅ UTR Submitted! Waiting for Admin Approval.")
                            st.rerun()
                except Exception as e:
                    st.error(f"Failed to log transaction: {e}")
            else:
                st.error("❌ Invalid Format! UTR must be exactly 12 numeric digits.")

elif st.session_state.payment_status == 'awaiting_approval':
      st.subheader("⏳ Awaiting Admin Approval")
      st.warning("Your UTR has been submitted and is currently being verified by the admin.")
        
        if st.button("🔄 Refresh Status", type="primary"):
            try:
                with get_db_connection() as conn:
                    c = conn.cursor()
                    txn = c.execute("SELECT status FROM transaction_logs WHERE pan=? ORDER BY id DESC LIMIT 1", (user_data['pan'],)).fetchone()
                    if txn and txn[0] == 'approved':
                        st.session_state.payment_status = 'completed'
                        st.rerun()
                    elif txn and txn[0] == 'rejected':
                        st.session_state.payment_status = 'pending'
                        st.error("❌ Your UTR was rejected by the admin. Please provide a valid UTR.")
                        st.rerun()
                    else:
                        st.info("Still pending... Please wait.")
            except Exception as e:
                st.error(f"Error checking status: {e}")

    else:
        if is_whitelisted and not is_trial:
            try:
                with get_db_connection() as conn:
                    c = conn.cursor()
                    # Log whitelist usage safely
                    c.execute("INSERT INTO transaction_logs (pan, name, utr, payment_type, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)",
                              (user_data['pan'], user_data['name'], f"WL-{user_data['pan']}-{date.today()}", "Whitelist", str(date.today()), "approved"))
                    conn.commit()
            except Exception:
                pass 
            st.success("🎉 Whitelist Access Granted! Clean PDF copy ready.")
        elif is_trial:
            st.warning("⚠️ Running in FREE TRIAL Mode. Generated PDF will contain a watermark.")
        else:
            st.success("🎉 Payment Verified! Clean PDF copy ready for deployment.")

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
        reset_user_session()
        st.session_state.current_page = 'home'
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

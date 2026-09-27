import streamlit as st
import qrcode
from io import BytesIO
import sqlite3
from datetime import date
import re
import os
import requests
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
                    # --- NEW ADDITIONS FOR ADMIN SETTINGS & EMAIL ---
            c.execute('''CREATE TABLE IF NOT EXISTS app_settings (
                 id INTEGER PRIMARY KEY, upi_id TEXT, payee_name TEXT, amount REAL,
                 sender_email TEXT, sender_password TEXT, telegram_token TEXT, telegram_chat_id TEXT
            )''')
      
            c.execute("SELECT count(*) FROM app_settings")
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO app_settings (id, upi_id, payee_name, amount, sender_email, sender_password) VALUES (1, 'admin@upi', 'Kosh-Tax Admin', 150.0, '', '')")
            
            # Migration for old data (Alag-alag try-except zaroori h SQLite k liye)
            try: c.execute("ALTER TABLE transaction_logs ADD COLUMN amount REAL DEFAULT 0.0")
            except: pass
            try: c.execute("ALTER TABLE transaction_logs ADD COLUMN email TEXT DEFAULT ''")
            except: pass
            try: c.execute("ALTER TABLE app_settings ADD COLUMN sender_email TEXT DEFAULT ''")
            except: pass
            try: c.execute("ALTER TABLE app_settings ADD COLUMN sender_password TEXT DEFAULT ''")
            except: pass
            try: c.execute("ALTER TABLE app_settings ADD COLUMN telegram_token TEXT DEFAULT ''")
            except: pass
            try: c.execute("ALTER TABLE app_settings ADD COLUMN telegram_chat_id TEXT DEFAULT ''")
            except: pass

            # ------------------------------------------------

            c.execute("SELECT count(*) FROM whitelist_pans")
            if c.fetchone()[0] == 0:
                c.executemany("INSERT INTO whitelist_pans (pan) VALUES (?)", [("OSYPK6572D",), ("ABCDE1234F",)])
            conn.commit()
    except Exception as e:
        st.error(f"Database Initialization Error: {e}")

init_db()
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

def send_approval_email(receiver_email, user_name, pdf_file_path):
    if not receiver_email or "@" not in receiver_email: return False

    try:
        with get_db_connection() as conn:
            settings = conn.cursor().execute("SELECT sender_email, sender_password FROM app_settings WHERE id=1").fetchone()
            if settings:
                sender_email, sender_password = settings[0], settings[1]
            else:
                sender_email, sender_password = "", ""
    except Exception:
        sender_email, sender_password = "", ""

    if not sender_email or not sender_password:
        st.error("⚠️ Email dispatch failed: Admin has not configured the Sender Email in settings.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "✅ Your Form-16 is Approved & Ready!"
    
    body = f"Hello {user_name},\n\nAapka payment verify ho gaya hai. Aapka Form 16 PDF is email me attached hai.\n\nThank you for using Kosh-Tax System!"
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with open(pdf_file_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(pdf_file_path)}")
            msg.attach(part)
            
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send email: Please check your App Password or Email in Admin Settings.")
        return False

def send_telegram_alert(name, pan, utr, amount):
    try:
        with get_db_connection() as conn:
            settings = conn.cursor().execute("SELECT telegram_token, telegram_chat_id FROM app_settings WHERE id=1").fetchone()
            if settings and settings[0] and settings[1]:
                token, chat_id = settings[0], settings[1]
                msg = f"🔔 *Naya Payment Aaya Hai!*\n\n👤 *Name:* {name}\n💳 *PAN:* {pan}\n💰 *Amount:* ₹{amount}\n🧾 *UTR:* `{utr}`\n\nJaldi se Admin Panel check karein!"
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        pass # Notification fail ho toh bhi user ka process na ruke


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
    
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            tot_rev = c.execute("SELECT SUM(amount) FROM transaction_logs WHERE status='approved'").fetchone()[0] or 0.0
            tot_purchasers = c.execute("SELECT COUNT(DISTINCT pan) FROM transaction_logs WHERE status='approved'").fetchone()[0] or 0
            tot_wl = c.execute("SELECT COUNT(*) FROM whitelist_pans").fetchone()[0] or 0
            active_wl = c.execute("SELECT COUNT(DISTINCT pan) FROM transaction_logs WHERE payment_type='Whitelist'").fetchone()[0] or 0
            
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("💰 Total Revenue", f"₹{tot_rev:,.2f}")
        m2.metric("👥 Total Purchasers", tot_purchasers)
        m3.metric("📋 Whitelisted Users", tot_wl)
        m4.metric("🔥 Active WL Users", active_wl)
    except Exception as e:
        st.error("Could not load metrics")
    
    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 UTR Approvals", "⚙️ App Settings", "🗄️ Detailed Ledger & Backup", "📋 Whitelist"])

    with tab1:
        st.subheader("Action Required: Pending UTRs")
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                pending_rows = cursor.execute("SELECT id, pan, name, utr, timestamp, amount, email FROM transaction_logs WHERE status='pending'").fetchall()
                
                if pending_rows:
                    for row in pending_rows:
                        with st.container():
                            col_info, col_app, col_rej = st.columns([4, 1, 1])
                            with col_info:
                                st.write(f"**PAN:** {row[1]} | **Name:** {row[2]} | **Email:** {row[6]}")
                                st.write(f"**UTR:** `{row[3]}` | **Amount Paid:** ₹{row[5]} | **Date:** {row[4]}")
                            with col_app:
                                if st.button("✅ Approve & Email", key=f"app_{row[0]}", type="primary"):
                                    pdf_path = f"temp_pdfs/{row[1]}_{row[3]}.pdf"
                                    
                                    if os.path.exists(pdf_path):
                                        mail_sent = send_approval_email(row[6], row[2], pdf_path)
                                        # Sirf email success hone par hi DB me approve mark karein
                                        if mail_sent:
                                            cursor.execute("UPDATE transaction_logs SET status='approved' WHERE id=?", (row[0],))
                                            conn.commit()
                                            os.remove(pdf_path) # Clean temp file
                                            st.success(f"Approved! PDF sent to {row[6]}")
                                            st.rerun()
                                        else:
                                            st.warning("Email fail ho gaya. Status abhi bhi Pending hai taaki aap fix karke dobara try kar sakein.")
                                    else:
                                        st.error("PDF file server par nahi mili. Approval aborted.")
                            with col_rej:
                                if st.button("❌ Reject", key=f"rej_{row[0]}"):
                                    cursor.execute("UPDATE transaction_logs SET status='rejected' WHERE id=?", (row[0],))
                                    conn.commit()
                                    st.rerun()
                            st.markdown("---")
                else:
                    st.success("🎉 No pending UTRs! You are all caught up.")
        except Exception as e:
            st.error(f"Error fetching logs: {e}")

    with tab2:
        st.subheader("System Configurations")
        try:
            with get_db_connection() as conn:
                current_settings = conn.cursor().execute("SELECT upi_id, payee_name, amount, sender_email, sender_password, telegram_token, telegram_chat_id FROM app_settings WHERE id=1").fetchone()
            
            with st.form("settings_form"):
                st.markdown("**💰 Payment QR Settings**")
                new_upi = st.text_input("Active UPI ID", value=current_settings[0])
                new_name = st.text_input("Payee Name", value=current_settings[1])
                new_amount = st.number_input("Fixed Amount to Collect (₹)", value=float(current_settings[2]))
                
                st.markdown("**📧 Auto-Email Dispatch Settings**")
                new_email = st.text_input("Sender Gmail Address", value=current_settings[3], placeholder="e.g. admin@gmail.com")
                new_pass = st.text_input("16-Digit Gmail App Password", value=current_settings[4], type="password")
                
                st.markdown("**📱 Telegram Notification Settings**")
                new_bot_token = st.text_input("Telegram Bot Token", value=current_settings[5] if len(current_settings)>5 else "")
                new_chat_id = st.text_input("Telegram Chat ID", value=current_settings[6] if len(current_settings)>6 else "")
                
                if st.form_submit_button("Update All Settings", type="primary"):
                    with get_db_connection() as conn:
                        conn.cursor().execute("UPDATE app_settings SET upi_id=?, payee_name=?, amount=?, sender_email=?, sender_password=?, telegram_token=?, telegram_chat_id=? WHERE id=1", 
                                              (new_upi, new_name, new_amount, new_email, new_pass, new_bot_token, new_chat_id))
                        conn.commit()
                    st.success("System configurations updated successfully!")
                    st.rerun()
        except Exception as e:
            st.error("Error loading settings")

    with tab3:
        st.subheader("Detailed Financial Ledger")
        try:
            with get_db_connection() as conn:
                all_logs = conn.cursor().execute("SELECT timestamp, name, pan, utr, amount, payment_type, status, email FROM transaction_logs ORDER BY id DESC").fetchall()
                if all_logs:
                    st.dataframe([{"Date": r[0], "Name": r[1], "PAN": r[2], "UTR": r[3], "Amount": r[4], "Type": r[5], "Status": r[6], "Email": r[7]} for r in all_logs], use_container_width=True)
        except Exception as e:
            st.error("Error fetching ledger")
            
        if os.path.exists(DB_NAME):
            with open(DB_NAME, "rb") as fp:
                st.download_button(label="💾 Download Full Database Backup", data=fp, file_name=f"kosh_tax_backup_{date.today()}.sqlite", mime="application/x-sqlite3")

    with tab4:
        st.subheader("Manage Whitelisted PAN Numbers")
        
        # --- ADD TO WHITELIST ---
        new_pan = st.text_input("Add New PAN to Whitelist").upper()
        if st.button("Add to Whitelist") and re.match(PAN_REGEX, new_pan):
            with get_db_connection() as conn:
                conn.cursor().execute("INSERT OR IGNORE INTO whitelist_pans (pan) VALUES (?)", (new_pan,))
                conn.commit()
            st.session_state.whitelisted_pans.add(new_pan)
            st.success(f"✅ {new_pan} added to Whitelist!")
            st.rerun()
            
        st.markdown("---")
        
        # --- DELETE FROM WHITELIST ---
        st.subheader("Remove PAN from Whitelist")
        # Ensure session state is updated
        current_wl = list(st.session_state.whitelisted_pans)
        
        if current_wl:
            pan_to_remove = st.selectbox("Select PAN to remove", ["-- Select PAN --"] + current_wl)
            if st.button("❌ Remove from Whitelist"):
                if pan_to_remove != "-- Select PAN --":
                    with get_db_connection() as conn:
                        conn.cursor().execute("DELETE FROM whitelist_pans WHERE pan=?", (pan_to_remove,))
                        conn.commit()
                    st.session_state.whitelisted_pans.discard(pan_to_remove)
                    st.success(f"🗑️ {pan_to_remove} removed from Whitelist successfully!")
                    st.rerun()
                else:
                    st.warning("Please select a PAN to remove.")
        else:
            st.info("Whitelist is currently empty.")


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
        st.markdown("**Note: Enter exact 12-digit UPI UTR...**")
        
            # ==========================================
        # ADMIN CONTROLLED DYNAMIC QR CODE
        # ==========================================
        try:
            with get_db_connection() as conn:
                settings = conn.cursor().execute("SELECT upi_id, payee_name, amount FROM app_settings WHERE id=1").fetchone()
                if settings:
                    upi_id, payee_name, amount = settings[0], settings[1], settings[2]
                else:
                    upi_id, payee_name, amount = "admin@upi", "Admin", 150.0
        except:
            upi_id, payee_name, amount = "admin@upi", "Admin", 150.0

        col_qr, col_info = st.columns([1, 2])
        with col_qr:
            upi_url = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR"
            qr = qrcode.make(upi_url)
            img_buffer = BytesIO()
            qr.save(img_buffer, format="PNG")
            
            st.markdown(f"**Amount to Pay: ₹{amount}**")
            st.image(img_buffer, caption=f"Scan to Pay: {upi_id}", width=200)
                
        with col_info:
            st.markdown("### Payment Instructions:")
            st.markdown(f"1. Scan the QR code to pay **₹{amount}**.")
            st.markdown("2. After successful payment, copy the **12-Digit UTR / Transaction ID**.")
            st.markdown("3. Paste it below. Your PDF will be emailed to you upon verification.")
            st.info(f"📧 PDF will be sent to: **{user_data.get('email', 'Your Email')}**")
        # ==========================================

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
                            # Generate PDF right now and save temporarily
                            os.makedirs("temp_pdfs", exist_ok=True)
                            pdf_bytes = generate_form16_pdf(user_data, is_trial=False)
                            temp_pdf_path = f"temp_pdfs/{user_data['pan']}_{utr_cleaned}.pdf"
                            with open(temp_pdf_path, "wb") as f:
                                f.write(pdf_bytes)

                            # Save transaction info including AMOUNT and EMAIL
                            c.execute("INSERT INTO transaction_logs (pan, name, utr, payment_type, timestamp, status, amount, email) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                      (user_data['pan'], user_data['name'], utr_cleaned, "Manual_UPI", str(date.today()), "pending", amount, user_data.get('email', '')))
                            conn.commit()
                                                    
                            # --- STRIKE 4: YE LINE ADD KARNI HAI ---
                            send_telegram_alert(user_data['name'], user_data['pan'], utr_cleaned, amount)
                            # ---------------------------------------
                            
                            st.session_state.payment_status = 'awaiting_approval'
                            
                            st.success("✅ UTR Submitted! You will receive your PDF via email once approved. You can close this page now.")
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

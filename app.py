import streamlit as st
from utils.salary_parser import parse_salary_slip
from utils.pdf_generator import generate_form16_pdf
from utils.tax_calculator import calculate_tax
from utils.trial_watermark import is_trial_mode
import os
from datetime import datetime

# Page Config
st.set_page_config(
    page_title="Kosh-Tax | Form 16 Generator",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Session State
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'home'
if 'user_data' not in st.session_state:
    st.session_state.user_data = {}
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None
if 'payment_status' not in st.session_state:
    st.session_state.payment_status = 'pending'

# Navigation Functions
def go_home():
    st.session_state.current_page = 'home'
    st.rerun()

def go_upload():
    st.session_state.current_page = 'upload'
    st.rerun()

def go_review():
    st.session_state.current_page = 'review'
    st.rerun()

def go_payment():
    st.session_state.current_page = 'payment'
    st.rerun()

def go_download():
    st.session_state.current_page = 'download'
    st.rerun()

# Home Page
def show_home():
    st.markdown("""
    # 🏛️ Kosh-Tax Form 16 Generator
    ## Generate Form 16 Online Instantly with Auto TDS Calculation
    ### For Jharkhand Government Employees
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Generate Form 16 Free", use_container_width=True, type="primary"):
            go_upload()
    with col2:
        if st.button("🎁 Start Free Trial", use_container_width=True):
            st.session_state.mode = 'trial'
            go_upload()

    # Features
    st.markdown("## ✨ Features")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        ### 📄 Form 16 Part A & B
        - Auto-generated
        - Professional format
        - PDF download
        """)
    with col2:
        st.markdown("""
        ### 🤖 Auto Scanner
        - Upload PDF
        - Auto-extract
        - CPC Pay Level
        """)
    with col3:
        st.markdown("""
        ### 💰 Payment Options
        - UPI QR Code
        - Cash to Admin
        - Free Trial
        """)
    with col4:
        st.markdown("""
        ### 📧 Email Delivery
        - Instant email
        - Download anytime
        - Trial watermarked
        """)

    # How It Works
    st.markdown("## 🎯 How It Works")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        **1. Upload**
        Upload salary slip PDF
        """)
    with col2:
        st.markdown("""
        **2. Review**
        Auto-extracted data
        """)
    with col3:
        st.markdown("""
        **3. Payment**
        UPI/Cash/Trial
        """)
    with col4:
        st.markdown("""
        **4. Download**
        Get Form 16 PDF
        """)

# Upload Page
def show_upload():
    st.title("📎 Upload Salary Slip")
    st.write("Upload your PDF salary slip. We'll auto-extract all details!")

    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=['pdf'],
        help="Maximum file size: 5MB"
    )

    if uploaded_file:
        with st.spinner("⏳ Extracting data from salary slip..."):
            # Parse salary slip
            extracted_data = parse_salary_slip(uploaded_file)
            st.session_state.extracted_data = extracted_data

            if extracted_data.get('confidence', 0) > 50:
                st.success("✅ Data extracted successfully!")

                # Show summary
                st.markdown("### 📊 Extracted Summary")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Name", extracted_data.get('name', 'N/A'))
                with col2:
                    st.metric("PAN", extracted_data.get('pan', 'N/A'))
                with col3:
                    st.metric("Basic Pay", f"₹{extracted_data.get('basic', 0):,}")

                if st.button("Review Data →", type="primary"):
                    go_review()
            else:
                st.warning("⚠️ Could not extract data. Please enter manually.")
                if st.button("Enter Manually"):
                    go_review()

    if st.button("← Back to Home"):
        go_home()

# Review Page
def show_review():
    st.title("📋 Review Your Data")

    data = st.session_state.extracted_data or {}

    with st.form("review_form"):
        # Personal Details
        st.subheader("👤 Personal Details")
        col1, col2 = st.columns(2)
        with col1:
            pan = st.text_input("PAN *", value=data.get('pan', ''), pattern="[A-Z]{5}[0-9]{4}[A-Z]{1}")
            name = st.text_input("Full Name *", value=data.get('name', ''))
        with col2:
            mobile = st.text_input("Mobile Number *", value=data.get('mobile', ''), pattern="[0-9]{10}")
            email = st.text_input("Email Address *", value=data.get('email', ''))

        # Employment Details
        st.subheader("💼 Employment Details")
        col1, col2 = st.columns(2)
        with col1:
            designation = st.text_input("Designation", value=data.get('designation', ''))
            office_name = st.text_input("Office/School Name", value=data.get('office_name', ''))
        with col2:
            district = st.selectbox(
                "District",
                ["KHUNTI", "RANCHI", "EAST SINGHBHUM", "DHANBAD", "BOKARO", "HAZARIBAGH"],
                index=0 if data.get('district') == 'KHUNTI' else None
            )
            ddo_tan = st.text_input("DDO TAN Number", value=data.get('ddo_tan', ''))

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
                'mobile': mobile,
                'email': email,
                'designation': designation,
                'office_name': office_name,
                'district': district,
                'ddo_tan': ddo_tan,
                'basic': basic,
                'da': da,
                'hra': hra,
                'medical': medical,
                'gpf': gpf,
                'tds': tds,
                'assessment_year': assessment_year,
                'tax_regime': tax_regime
            }
            go_payment()

    if st.button("← Back"):
        go_upload()

# Payment Page
def show_payment():
    st.title("💰 Payment")

    mode = st.session_state.get('mode', 'paid')

    if mode == 'trial':
        st.success("🎁 Free Trial Mode")
        if st.button("Download Trial Copy", type="primary", use_container_width=True):
            st.session_state.payment_status = 'trial'
            go_download()
    else:
        st.markdown("### Choose Payment Method")

        tab1, tab2, tab3 = st.tabs(["📱 UPI Payment", "💵 Cash Payment", "🎁 Free Trial"])

        with tab1:
            st.markdown("""
            **Amount: ₹99**

            UPI ID: `nitinmallick111-1@okicici`

            [📋 Copy UPI ID](#)
            """)

            utr = st.text_input("Enter 12-digit UTR Number", max_chars=12, pattern="[0-9]{12}")

            if st.button("Verify & Download", type="primary", use_container_width=True):
                if len(utr) == 12:
                    st.session_state.payment_status = 'paid'
                    st.session_state.utr = utr
                    go_download()
                else:
                    st.error("UTR must be 12 digits")

        with tab2:
            st.markdown("""
            **Amount: ₹99**

            Pay cash at admin office.
            Form 16 will be sent after verification.
            """)

            if st.button("I Paid Cash", use_container_width=True):
                st.session_state.payment_status = 'cash'
                go_download()

        with tab3:
            st.markdown("""
            **FREE Trial Copy**

            - Watermarked PDF
            - For verification only
            - Not for official use
            """)

            if st.button("Download Trial", use_container_width=True):
                st.session_state.payment_status = 'trial'
                go_download()

    if st.button("← Back"):
        go_review()

# Download Page
def show_download():
    st.title("📄 Download Form 16")

    payment_status = st.session_state.get('payment_status', 'pending')

    if payment_status == 'trial':
        st.warning("⚠️ **TRIAL COPY** - FOR VERIFICATION ONLY")
        st.info("This is a free trial copy with watermark. Not valid for official use.")
    elif payment_status == 'pending':
        st.info("⏳ Payment verification in progress. You'll receive Form 16 on email once verified.")
    else:
        st.success("✅ Payment Verified!")

    # Generate Form 16
    with st.spinner("Generating Form 16 PDF..."):
        user_data = st.session_state.user_data

        # Generate PDF
        pdf_data = generate_form16_pdf(
            user_data,
            is_trial=(payment_status == 'trial')
        )

        # Download button
        st.download_button(
            label="📥 Download Form 16 PDF",
            data=pdf_data,
            file_name=f"Form16_{user_data.get('pan', 'UNKNOWN')}_AY2025-26.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )

    st.success(f"📧 Form 16 sent to: {user_data.get('email', 'N/A')}")

    if st.button("🔄 Generate Another Form 16", use_container_width=True):
        # Reset session
        st.session_state.user_data = {}
        st.session_state.extracted_data = None
        st.session_state.payment_status = 'pending'
        go_home()

# Main App
def main():
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/india-gate.png", width=80)
        st.title("Kosh-Tax")

        menu = st.radio(
            "Navigation",
            ["Home", "Upload", "Review", "Payment", "Download"],
            index=0
        )

        if menu == "Home":
            go_home()
        elif menu == "Upload":
            go_upload()
        elif menu == "Review":
            go_review()
        elif menu == "Payment":
            go_payment()
        elif menu == "Download":
            go_download()

        st.markdown("---")
        st.markdown("Made with ❤️ for Jharkhand Govt Employees")

    # Route to current page
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

if __name__ == "__main__":
    main()

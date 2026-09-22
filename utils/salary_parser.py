from pypdf import PdfReader
import re

def parse_salary_slip(file):
    """
    Extract all components including dynamic Ptax, GIS, and Medical from salary slip PDF
    """
    extracted = {
        'name': '', 'pan': '', 'designation': '',
        'basic': 0.0, 'da': 0.0, 'hra': 0.0, 'medical': 0.0,
        'gpf': 0.0, 'gis': 0.0, 'ptax': 0.0, 'gpf_no': '',
        'arrear_da': 0.0, 'arrear_pay': 0.0, 'confidence': 0
    }

    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        text_upper = text.upper()

        # 1. Extract PAN
        pan_match = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', text_upper)
        if pan_match:
            extracted['pan'] = pan_match.group(1).upper()
            extracted['confidence'] += 20

        # 2. Extract Designation
        found_des = ""
        for des in ["ASSISTANT TEACHER", "TEACHER", "CLERK", "LIPIK", "HEADMASTER", "PRINCIPAL", "ACCOUNTANT"]:
            if des in text_upper:
                found_des = des
                break
        extracted['designation'] = found_des.upper()

        # 3. Extract Name cleanly
        name_match = re.search(r'(?:EMPLOYEE\s*NAME|NAME)\s*[:\-]?\s*([A-Z\s\.]+)', text_upper)
        if name_match:
            raw_name = name_match.group(1)
            for keyword in ["DESIGNATION", "PAN", "GPF", "PRAN", "DDO", "BASIC"]:
                if keyword in raw_name:
                    raw_name = raw_name.split(keyword)[0]
            extracted['name'] = raw_name.strip().upper()
            extracted['confidence'] += 20

        if not extracted['name']:
            extracted['name'] = "VALUED EMPLOYEE"

        # 4. Extract GPF Number
        gpf_match = re.search(r'(?:GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', text_upper)
        if gpf_match:
            extracted['gpf_no'] = gpf_match.group(1).strip().upper()

        # 5. Numeric fields helper
        def get_val(labels):
            for l in labels:
                m = re.search(rf"{l}\s*[:\-]?\s*[₹Rs\.\s]*([0-9,]+(?:\.[0-9]+)?)", text_upper)
                if m:
                    try: return float(m.group(1).replace(',', ''))
                    except: pass
            return 0.0

        extracted['basic'] = get_val(["BASIC", "मूल वेतन"])
        extracted['da'] = get_val(["DA", "महंगाई भत्ता"])
        extracted['hra'] = get_val(["HRA"])
        extracted['medical'] = get_val(["MEDICAL", "MED ALLOWANCE", "MED"])
        extracted['gpf'] = get_val(["GPF", "NPS"])
        extracted['gis'] = get_val(["GIS", "GROUP INSURANCE"])
        extracted['ptax'] = get_val(["PTAX", "PROFESSIONAL TAX", "PROF TAX"])
        extracted['arrear_da'] = get_val(["ARREAR DA"])
        extracted['arrear_pay'] = get_val(["ARREAR PAY", "PAY ARREAR"])

    except Exception as e:
        print(f"Error parsing PDF: {e}")

    return extracted

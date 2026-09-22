from pypdf import PdfReader
import re

def parse_salary_slip(file):
    """
    Extract data cleanly from salary slip PDF avoiding text overlapping
    """
    extracted = {
        'name': '', 'pan': '', 'designation': '',
        'basic': 0.0, 'da': 0.0, 'hra': 0.0, 'medical': 1000.0,
        'gpf': 0.0, 'gis': 60.0, 'ptax': 200.0, 'gpf_no': '',
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

        # 2. Extract Name (Strictly stopping before DESIGNATION, PAN, etc.)
        name_match = re.search(r'(?:EMPLOYEE\s*NAME|NAME)\s*[:\-]?\s*([A-Z\s]+?)(?=\s+DESIGNATION|\s+PAN|\s+GPF|\s+DDO|\n|$)', text_upper)
        if name_match:
            clean_name = name_match.group(1).replace("DESIGN", "").strip()
            extracted['name'] = clean_name.upper()
            extracted['confidence'] += 20

        # 3. Extract Designation
        for des in ["ASSISTANT TEACHER", "TEACHER", "CLERK", "LIPIK", "HEADMASTER", "PRINCIPAL", "ACCOUNTANT"]:
            if des in text_upper:
                extracted['designation'] = des.upper()
                break

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
        extracted['gpf'] = get_val(["GPF", "NPS"])
        extracted['gis'] = get_val(["GIS"]) or 60.0
        extracted['ptax'] = get_val(["PTAX", "PROFESSIONAL TAX"]) or 200.0
        extracted['arrear_da'] = get_val(["ARREAR DA"])
        extracted['arrear_pay'] = get_val(["ARREAR PAY", "PAY ARREAR"])

    except Exception as e:
        print(f"Error parsing PDF: {e}")

    return extracted


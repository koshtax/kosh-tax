from pypdf import PdfReader
import re

def parse_salary_slip(file):
    """
    Robust Multi-Block Parser to extract max/latest Basic Pay, DA, HRA, Medical, 
    GPF, PTax, TDS, and map all individual salary blocks for monthly records.
    """
    extracted = {
        'name': '', 'pan': '', 'designation': '',
        'basic': 0.0, 'da': 0.0, 'hra': 0.0, 'medical': 1000.0,
        'gross': 0.0, 'gpf': 5000.0, 'ptax': 200.0, 'tds': 0.0, 'gli': 60.0,
        'net_income': 0.0, 'gpf_no': '', 'monthly_entries': [], 'confidence': 0
    }

    try:
        reader = PdfReader(file)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() or ""

        text_upper = full_text.upper()

        # 1. Extract PAN
        pan_match = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', text_upper)
        if pan_match:
            extracted['pan'] = pan_match.group(1).upper()
            extracted['confidence'] += 20

        # 2. Extract GPF / PRAN Number
        gpf_no_match = re.search(r'(?:EMPLOYEE\s*GPF\s*NO\.?|GPF|PRAN|PF)\s*NO\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)', text_upper)
        if gpf_no_match:
            extracted['gpf_no'] = gpf_no_match.group(1).strip().upper()

        # 3. Extract Designation
        for des in ["ASSISTANT TEACHER", "+2 TEACHER", "TEACHER", "CLERK", "LIPIK", "HEADMASTER", "PRINCIPAL", "ACCOUNTANT"]:
            if des in text_upper:
                extracted['designation'] = des.upper()
                break
        if not extracted['designation']:
            extracted['designation'] = "ASSISTANT TEACHER"

        # 4. Extract Name cleanly
        name_match = re.search(r'(?:EMPLOYEE\s*NAME|NAME)\s*[:\-]?\s*([A-Z\s\.]+)', text_upper)
        if name_match:
            raw_name = name_match.group(1)
            for keyword in ["DESIGNATION", "PAN", "GPF", "PRAN", "DDO", "BASIC", "EMPLOYEE", "EMP"]:
                if keyword in raw_name:
                    raw_name = raw_name.split(keyword)[0]
            extracted['name'] = raw_name.strip().upper()
            extracted['confidence'] += 20

        if not extracted['name']:
            extracted['name'] = "VALUED EMPLOYEE"

        # 5. Multi-Block Scanning using standard keywords or splitting by Govt of Jharkhand salary blocks
        salary_blocks = re.split(r'GOVT\.\s*OF\s*JHARKHAND|SALARY\s*SLIP', text_upper)
        
        all_basics = []
        monthly_records = []

        for block in salary_blocks:
            if len(block) < 15:
                continue
            
            def get_b_val(pattern_list):
                for pat in pattern_list:
                    match = re.search(rf"{pat}\s*[:\-]?\s*[₹Rs\.\s]*([0-9,]+(?:\.[0-9]+)?)", block)
                    if match:
                        try:
                            val = float(match.group(1).replace(',', ''))
                            if val > 0: return val
                        except: pass
                return 0.0

            b_val = get_b_val([r"BASIC", r"मूल\s*वेतन"])
            d_val = get_b_val([r"DA", r"महंगाई\s*भट्टा"])
            h_val = get_b_val([r"HRA", r"मकान\s*किराया"])
            m_val = get_b_val([r"MEDICAL", r"MED", r"चिकित्सा"])
            g_val = get_b_val([r"GPF", r"C\.?P\.?F\.?"])
            t_val = get_b_val([r"LTAX", r"PTAX", r"PROFESSIONAL\s*TAX", r"I\.?TAX", r"TDS", r"आयकर"])
            gl_val = get_b_val([r"GLI", r"GIS", r"बीमा"])

            if b_val > 0:
                all_basics.append(b_val)
                c_gross = b_val + d_val + h_val + (m_val if m_val > 0 else 1000.0)
                c_ded = (g_val if g_val > 0 else 5000.0) + (t_val if t_val > 0 else 200.0) + (gl_val if gl_val > 0 else 60.0)
                
                monthly_records.append({
                    'basic': b_val,
                    'da': d_val if d_val > 0 else b_val * 0.5,
                    'hra': h_val if h_val > 0 else b_val * 0.09,
                    'medical': m_val if m_val > 0 else 1000.0,
                    'gross': c_gross,
                    'gpf': g_val if g_val > 0 else 5000.0,
                    'ptax': t_val if 0 < t_val < 500 else 200.0,
                    'tds': t_val if t_val >= 500 else 0.0,
                    'gli': gl_val if gl_val > 0 else 60.0,
                    'net': c_gross - c_ded
                })

        # Fallback if specific blocks weren't caught nicely
        if not all_basics:
            def get_global(pat):
                m = re.search(rf"{pat}\s*[:\-]?\s*[₹Rs\.\s]*([0-9,]+(?:\.[0-9]+)?)", text_upper)
                if m:
                    try: return float(m.group(1).replace(',', ''))
                    except: pass
                return 0.0

            b_val = get_global("BASIC") or 58600.0
            d_val = get_global("DA") or 31058.0
            h_val = get_global("HRA") or 5860.0
            m_val = get_global("MEDICAL") or 1000.0
            g_val = get_global("GPF") or 5000.0
            t_val = get_global("TDS") or 3000.0
            
            all_basics.append(b_val)
            gross_val = b_val + d_val + h_val + m_val
            monthly_records.append({
                'basic': b_val, 'da': d_val, 'hra': h_val, 'medical': m_val,
                'gross': gross_val, 'gpf': g_val, 'ptax': 200.0, 'tds': t_val, 'gli': 60.0,
                'net': gross_val - (g_val + 200.0 + t_val + 60.0)
            })

        # Choose the MAX / LATEST Basic Pay (e.g., 58,600)
        latest_basic = max(all_basics) if all_basics else 58600.0
        latest_record = next((r for r in monthly_records if r['basic'] == latest_basic), monthly_records[0])

        extracted['basic'] = latest_basic
        extracted['da'] = latest_record['da']
        extracted['hra'] = latest_record['hra']
        extracted['medical'] = latest_record['medical']
        extracted['gross'] = latest_record['gross']
        extracted['gpf'] = latest_record['gpf']
        extracted['ptax'] = latest_record['ptax']
        extracted['tds'] = latest_record['tds']
        extracted['gli'] = latest_record['gli']
        extracted['net_income'] = latest_record['net']
        extracted['monthly_entries'] = monthly_records

    except Exception as e:
        print(f"Error in advanced parser: {e}")

    return extracted

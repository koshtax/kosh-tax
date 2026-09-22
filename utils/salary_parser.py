from pypdf import PdfReader
import re

def parse_salary_slip(file):
    """
    Extract data from salary slip PDF
    """
    extracted = {
        'name': '',
        'pan': '',
        'designation': '',
        'basic': 0,
        'da': 0,
        'hra': 0,
        'medical': 0,
        'gpf': 0,
        'tds': 0,
        'confidence': 0
    }

    try:
        reader = PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""

        text_upper = text.upper()

        # Extract PAN
        pan_match = re.search(r'([A-Z]{5}[0-9]{4}[A-Z]{1})', text_upper)
        if pan_match:
            extracted['pan'] = pan_match.group(1)
            extracted['confidence'] += 20

        # Extract Name
        name_match = re.search(r'EMPLOYEE\s*NAME\s*[:\-]?\s*([A-Z\s\.]+)', text_upper)
        if name_match:
            extracted['name'] = name_match.group(1).strip()
            extracted['confidence'] += 20

        # Extract Basic Pay
        basic_match = re.search(r'BASIC\s*[:\-]?\s*[₹Rs\.]?\s*([0-9,]+)', text_upper)
        if basic_match:
            extracted['basic'] = float(basic_match.group(1).replace(',', ''))
            extracted['confidence'] += 20

        # Extract DA
        da_match = re.search(r'DA\s*[:\-]?\s*[₹Rs\.]?\s*([0-9,]+)', text_upper)
        if da_match:
            extracted['da'] = float(da_match.group(1).replace(',', ''))
            extracted['confidence'] += 10

        # Extract HRA
        hra_match = re.search(r'HRA\s*[:\-]?\s*[₹Rs\.]?\s*([0-9,]+)', text_upper)
        if hra_match:
            extracted['hra'] = float(hra_match.group(1).replace(',', ''))
            extracted['confidence'] += 10

        # Extract GPF
        gpf_match = re.search(r'GPF\s*[:\-]?\s*[₹Rs\.]?\s*([0-9,]+)', text_upper)
        if gpf_match:
            extracted['gpf'] = float(gpf_match.group(1).replace(',', ''))
            extracted['confidence'] += 10

        # Extract TDS
        tds_match = re.search(r'(?:I\.?TAX|TDS)\s*[:\-]?\s*[₹Rs\.]?\s*([0-9,]+)', text_upper)
        if tds_match:
            extracted['tds'] = float(tds_match.group(1).replace(',', ''))
            extracted['confidence'] += 10

    except Exception as e:
        print(f"Error parsing PDF: {e}")

    return extracted

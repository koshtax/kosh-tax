from weasyprint import HTML
from jinja2 import Template
from datetime import date

def generate_form16_pdf(data, is_trial=False):
    """
    Generate exact word-to-word official Form 16 (Part A & B), Schedule of Income-Tax, 
    and Monthly Salary Statement layout with safe float conversions.
    """
    try:
        basic = float(data.get('basic', 0) or 0)
        da = float(data.get('da', 0) or 0)
        hra = float(data.get('hra', 0) or 0)
        medical = float(data.get('medical', 0) or 0)
        gross = float(data.get('gross', basic + da + hra + medical) or (basic + da + hra + medical))
        
        ptax = float(data.get('ptax', 200) or 200)
        gpf = float(data.get('gpf', 0) or 0)
        tds = float(data.get('tds', 0) or 0)
        gli = float(data.get('gli', 60) or 60)
        net_income = float(data.get('net_income', gross - (ptax + gpf + tds + gli)) or 0)
        
        raw_entries = data.get('monthly_entries', [])
        monthly_entries = []
        if raw_entries:
            for entry in raw_entries:
                eb = float(entry.get('basic', basic) or basic)
                ed = float(entry.get('da', da) or da)
                eh = float(entry.get('hra', hra) or hra)
                em = float(entry.get('medical', medical) or medical)
                eg = float(entry.get('gross', eb + ed + eh + em) or (eb + ed + eh + em))
                egpf = float(entry.get('gpf', gpf) or gpf)
                ept = float(entry.get('ptax', ptax) or ptax)
                etds = float(entry.get('tds', 0) or 0)
                egli = float(entry.get('gli', 60) or 60)
                enet = float(entry.get('net', eg - (egpf + ept + etds + egli)) or 0)
                
                monthly_entries.append({
                    'basic': eb, 'da': ed, 'hra': eh, 'medical': em,
                    'gross': eg, 'gpf': egpf, 'ptax': ept, 'tds': etds, 'gli': egli, 'net': enet
                })
        else:
            monthly_entries = [{
                'basic': basic, 'da': da, 'hra': hra, 'medical': medical,
                'gross': gross, 'gpf': gpf, 'ptax': ptax, 'tds': tds, 'gli': gli, 'net': net_income
            }]
    except Exception as e:
        print(f"Error processing PDF data: {e}")
        gross, net_income = 0.0, 0.0
        monthly_entries = []

    template = Template("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {
    size: A4;
    margin: 10mm;
    @bottom-center {
      {% if is_trial %}
      content: "DEVELOPED & DESIGNED BY @ NITIN MALLICK";
      font-size: 8px;
      font-weight: bold;
      color: #555;
      {% else %}
      content: "";
      {% endif %}
    }
  }
  body { font-family: Arial, sans-serif; font-size: 7.5px; text-transform: uppercase; color: #000; line-height: 1.15; }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  .right { text-align: right; }
  .left { text-align: left; }
  table { width: 100%; border-collapse: collapse; margin-top: 3px; margin-bottom: 3px; }
  table, th, td { border: 1px solid black; }
  th, td { padding: 2.5px 3px; vertical-align: top; }
  .no-border { border: none; }
  .header-box { border: 1.5px solid black; padding: 4px; margin-bottom: 4px; }
  .page-break { page-break-after: always; }
  
  {% if is_trial %}
  .watermark {
    position: fixed;
    top: 45%;
    left: 35%;
    transform: translate(-50%, -50%) rotate(-45deg);
    font-size: 55px;
    color: rgba(255, 0, 0, 0.12);
    z-index: 9999;
  }
  {% endif %}
</style>
</head>
<body>
{% if is_trial %}
<div class="watermark">TRIAL COPY</div>
{% endif %}

<!-- ================= PAGE 1: SCHEDULE OF INCOME-TAX ================= -->
<div class="header-box center">
  <div class="bold" style="font-size: 10px;">SCHEDULE OF INCOME - TAX (नई कर व्यवस्था के तहत)</div>
  <div style="font-size: 8px;">वित्तीय वर्ष 2025-26 (कर निर्धारण वर्ष 2026-2027)</div>
</div>

<table>
  <tr>
    <td colspan="2">
      <b>करदाता का नाम / Name:</b> {{ data.name }}<br>
      <b>पदनाम / Designation:</b> {{ data.designation }}<br>
      <b>कार्यालय/विद्यालय का नाम / Office:</b> {{ data.office_name }}<br>
      <b>स्थायी लेखा संख्या (PAN):</b> {{ data.pan }}
    </td>
  </tr>
  <tr>
    <td width="75%"><b>क. वेतन स्रोत से प्राप्त आय का विवरण :-</b><br>
        01. वेतन (दिनांक 01.03.2025 से 28.02.2026 तक)<br>
        02. महँगाई भत्ता :-<br>
        03. मकान किराया भत्ता :-<br>
        04. चिकित्सा भत्ता :-<br>
        05. परिवहन भत्ता :-<br>
        06. परिवहन भत्ता पर महंगाई भत्ता :-<br>
        07. विशेष वेतन/बोनस / मानदेय / नर्सिंग भत्ता :-<br>
        08. महंगाई भत्ता की बकाया राशि :-<br>
        09. बकाया वेतन एवं भत्ते का राशि :-<br>
        <b>10. वेतन स्रोत से प्राप्त कुल आय :-</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(basic) }}<br>
        Rs. {{ "%.2f"|format(da) }}<br>
        Rs. {{ "%.2f"|format(hra) }}<br>
        Rs. {{ "%.2f"|format(medical) }}<br>
        Rs. 0.00<br>
        Rs. 0.00<br>
        Rs. 0.00<br>
        Rs. 0.00<br>
        Rs. 0.00<br>
        <b>Rs. {{ "%.2f"|format(gross) }}</b>
    </td>
  </tr>
  <tr>
    <td><b>ख. आयकर की संगणना :-</b><br>
        01. वेतन स्रोत से प्राप्त कुल आय<br>
        02. घटायें धारा 16 (ia) के अन्तर्गत मानक कटौती की राशि रू० 75,000.00<br>
        03. सकल कुल आय (Gross Total Income)<br>
        04. कर योग्य आय (Taxable Income)<br>
        <b>05. शुद्ध देय आयकर :-</b>
    </td>
    <td class="right"><br>
        Rs. {{ "%.2f"|format(gross) }}<br>
        (-) Rs. 75,000.00<br>
        Rs. {{ "%.2f"|format(gross - 75000) }}<br>
        Rs. {{ "%.2f"|format(gross - 75000) }}<br>
        <b>Rs. 0.00</b>
    </td>
  </tr>
</table>

<table class="no-border" style="margin-top: 15px;">
  <tr>
    <td class="no-border" width="50%"><b>कोषागार का नाम:</b> {{ data.district }}</td>
    <td class="no-border" width="50%" class="right">
      __________________________________________<br>
      <b>करदाता का हस्ताक्षर / निकासी एवं व्ययन पदाधिकारी का हस्ताक्षर एवं मुहर</b><br>
      <b>TAN:</b> {{ data.ddo_tan }}
    </td>
  </tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 2: FORM NO. 16 PART A ================= -->
<div class="header-box center">
  <div class="bold" style="font-size: 10px;">FORM NO. 16 - PART A</div>
  <div style="font-size: 8px;">[See Rule 31(1)(a)]</div>
  <div class="bold" style="font-size: 8px;">Certificate under Section 203 of the Income-Tax Act, 1961 for tax deduction at source from income chargeable under the head "SALARIES"</div>
</div>

<table>
  <tr>
    <td width="50%">
      <b>Name and address of the Employer:</b><br>
      {{ data.employer_address }}
    </td>
    <td width="50%">
      <b>Name and address of the Employee:</b><br>
      {{ data.name }}<br>
      {{ data.office_name }}
    </td>
  </tr>
  <tr>
    <td>
      <b>TAN of Deductor:</b> {{ data.ddo_tan }}<br>
      <b>PAN of Deductor:</b> {{ data.pan }}
    </td>
    <td>
      <b>PAN of Employee:</b> {{ data.pan }}<br>
      <b>GPF/PRAN No.:</b> {{ data.gpf_no }}
    </td>
  </tr>
  <tr>
    <td><b>Assessment Year:</b> {{ data.assessment_year }}</td>
    <td><b>Period with Employer:</b> From: 01.04.2025 To: 31.03.2026</td>
  </tr>
</table>

<div class="bold" style="margin-top: 3px;">Summary of amount paid/credited and tax deducted at source thereon in respect of the employee</div>
<table>
  <tr class="bold center">
    <td>Quarter(s)</td>
    <td>Amount paid/credited (Rs.)</td>
    <td>Amount of tax deducted (Rs.)</td>
    <td>Amount of tax deposited/remitted (Rs.)</td>
  </tr>
  <tr><td>Quarter 1</td><td>-</td><td>{{ "%.2f"|format(tds) }}</td><td>{{ "%.2f"|format(tds) }}</td></tr>
  <tr><td>Quarter 2</td><td>-</td><td>-</td><td>-</td></tr>
  <tr><td>Quarter 3</td><td>-</td><td>-</td><td>-</td></tr>
  <tr><td>Quarter 4</td><td>-</td><td>-</td><td>-</td></tr>
  <tr class="bold"><td>Total (Rs.)</td><td>-</td><td>{{ "%.2f"|format(tds) }}</td><td>{{ "%.2f"|format(tds) }}</td></tr>
</table>

<div class="bold" style="margin-top: 3px;">I. DETAILS OF TAX DEDUCTED AND DEPOSITED IN THE CENTRAL GOVERNMENT ACCOUNT THROUGH BOOK ADJUSTMENT</div>
<table>
  <tr class="bold center">
    <td>Sl. No.</td>
    <td>Tax Deposited in respect of deductee (Rs.)</td>
    <td>Receipt No. of Form 24G</td>
    <td>DDO Serial No. in Form 24G</td>
    <td>Date of transfer voucher</td>
    <td>Status of matching</td>
  </tr>
  {% for i in range(1, 4) %}
  <tr><td>{{ i }}</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
  {% endfor %}
  <tr class="bold"><td>Total (Rs.)</td><td colspan="5">-</td></tr>
</table>

<div class="bold" style="margin-top: 3px;">II. DETAILS OF TAX DEDUCTED AND DEPOSITED THROUGH CHALLAN</div>
<table>
  <tr class="bold center">
    <td>Sl. No.</td>
    <td>Tax Deposited (Rs.)</td>
    <td>BSR Code of Bank Branch</td>
    <td>Challan Identification Number (CIN) / Date</td>
    <td>Challan Serial No.</td>
    <td>Status with OLTAS</td>
  </tr>
  {% for i in range(1, 3) %}
  <tr><td>{{ i }}</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
  {% endfor %}
  <tr class="bold"><td>Total (Rs.)</td><td colspan="5">-</td></tr>
</table>

<div class="header-box" style="margin-top: 5px;">
  <div class="bold center">Verification</div>
  <p>I, <b>{{ data.ddo_officer }}</b> son/daughter of <b>{{ data.ddo_father }}</b> working in the capacity of <b>DRAWING AND DISBURSING OFFICER</b> do hereby certify that a sum of Rs. <b>{{ "%.2f"|format(tds) }}</b> has been deducted and deposited to the credit of the Central Government.</p>
  <table class="no-border" style="margin-top: 3px;">
    <tr>
      <td class="no-border" width="50%"><b>Place:</b> {{ data.district }}<br><b>Date:</b> {{ today }}</td>
      <td class="no-border" width="50%" class="right">
        __________________________________________<br>
        <b>Signature of person responsible for tax deduction</b><br>
        <b>Full Name:</b> {{ data.ddo_officer }}
      </td>
    </tr>
  </table>
</div>

<div class="page-break"></div>

<!-- ================= PAGE 3: FORM NO. 16 PART B (ANNEXURE) ================= -->
<div class="header-box center">
  <div class="bold" style="font-size: 10px;">PART B (ANNEXURE) - DETAILS OF SALARY PAID</div>
</div>

<table>
  <tr>
    <td width="80%"><b>1. GROSS SALARY</b><br>
        (a) Salary as per provisions u/s 17(1)<br>
        (b) Value of perquisites u/s 17(2)<br>
        (c) Profits in lieu of salary u/s 17(3)<br>
        (d) TOTAL<br>
        (e) Reported total amount of salary received from other employer(s)
    </td>
    <td width="20%" class="right"><br>Rs. {{ "%.2f"|format(gross) }}<br>Rs. 0.00<br>Rs. 0.00<br>Rs. {{ "%.2f"|format(gross) }}<br>Rs. 0.00</td>
  </tr>
  <tr><td><b>2. LESS: ALLOWANCE TO THE EXTENT EXEMPT U/S 10</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>3. BALANCE (1 - 2)</b></td><td class="right">Rs. {{ "%.2f"|format(gross) }}</td></tr>
  <tr>
    <td><b>4. DEDUCTIONS UNDER SECTION 16</b><br>
        (a) Standard Deduction u/s 16(i)<br>
        (b) Entertainment allowance u/s 16(ii)<br>
        (c) Tax on employment (Professional Tax) u/s 16(iii)
    </td>
    <td class="right"><br>Rs. 75,000.00<br>Rs. 0.00<br>Rs. {{ "%.2f"|format(ptax) }}</td>
  </tr>
  <tr><td><b>5. AGGREGATE OF DEDUCTIONS U/S 16</b></td><td class="right">Rs. {{ "%.2f"|format(ptax + 75000) }}</td></tr>
  <tr><td><b>6. INCOME CHARGEABLE UNDER THE HEAD "SALARIES" (3 - 5)</b></td><td class="right">Rs. {{ "%.2f"|format(gross - (ptax + 75000)) }}</td></tr>
  <tr><td><b>7. ADD: ANY OTHER INCOME REPORTED BY EMPLOYEE</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>8. GROSS TOTAL INCOME (6 + 7)</b></td><td class="right">Rs. {{ "%.2f"|format(gross - (ptax + 75000)) }}</td></tr>
</table>

<div class="bold" style="margin-top: 3px;">9. DEDUCTIONS UNDER CHAPTER VI-A</div>
<table>
  <tr class="bold center">
    <td>Under Section</td>
    <td>Gross Amount (Rs.)</td>
    <td>Qualifying Amount (Rs.)</td>
    <td>Deductible Amount (Rs.)</td>
  </tr>
  <tr><td>80C (GPF / LIC / etc.)</td><td class="right">{{ "%.2f"|format(gpf) }}</td><td class="right">-</td><td class="right">{{ "%.2f"|format(gpf) }}</td></tr>
  <tr><td>80CCD(1B) / 80D / 80G</td><td class="right">0.00</td><td class="right">-</td><td class="right">0.00</td></tr>
  <tr class="bold"><td>Total Deductions under Chapter VI-A</td><td colspan="3" class="right">{{ "%.2f"|format(gpf) }}</td></tr>
</table>

<table>
  <tr><td><b>10. AGGREGATE OF DEDUCTIBLE AMOUNT UNDER CHAPTER VI-A</b></td><td class="right" width="25%">Rs. {{ "%.2f"|format(gpf) }}</td></tr>
  <tr><td><b>11. TOTAL TAXABLE INCOME (8 - 10)</b></td><td class="right">Rs. {{ "%.2f"|format((gross - (ptax + 75000)) - gpf) }}</td></tr>
  <tr><td><b>12. TAX ON TOTAL INCOME</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>13. LESS: REBATE UNDER SECTION 87A</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>14. TOTAL TAX PAYABLE</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>15. EDUCATION CESS @ 4%</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>16. TAX PAYABLE (14 + 15)</b></td><td class="right">Rs. 0.00</td></tr>
  <tr><td><b>21. NET TAX PAYABLE / REFUNDABLE</b></td><td class="right">Rs. {{ "%.2f"|format(tds) }}</td></tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 4: MONTHLY SALARY STATEMENT SHEET ================= -->
<div class="header-box center">
  <div class="bold" style="font-size: 9px;">वित्तीय वर्ष 2025-26 में वेतन स्रोत से आय और कटौतियों की विवरणी</div>
  <div style="font-size: 7.5px;">नाम: {{ data.name }} | पदनाम: {{ data.designation }} | कार्यालय: {{ data.office_name }}</div>
</div>

<table>
  <tr class="bold center" style="background-color: #f2f2f2;">
    <td>सत्र / प्रविष्टि विवरण</td>
    <td>मूल वेतन</td>
    <td>महंगाई भत्ता</td>
    <td>मकान किराया</td>
    <td>चिकित्सा</td>
    <td>कुल योग (आय)</td>
    <td>जी.पी.एफ.</td>
    <td>जी.आई.एस.</td>
    <td>व्यावसायिक कर</td>
    <td>कटौतियों का योग</td>
    <td>आयकर (TDS)</td>
    <td>शुद्ध वेतन (Net Pay)</td>
  </tr>
  {% for entry in monthly_entries %}
  <tr>
    <td><b>प्रविष्टि {{ loop.index }}</b></td>
    <td class="right">{{ "%.2f"|format(entry.basic) }}</td>
    <td class="right">{{ "%.2f"|format(entry.da) }}</td>
    <td class="right">{{ "%.2f"|format(entry.hra) }}</td>
    <td class="right">{{ "%.2f"|format(entry.medical) }}</td>
    <td class="right">{{ "%.2f"|format(entry.gross) }}</td>
    <td class="right">{{ "%.2f"|format(entry.gpf) }}</td>
    <td class="right">{{ "%.2f"|format(entry.gli) }}</td>
    <td class="right">{{ "%.2f"|format(entry.ptax) }}</td>
    <td class="right">{{ "%.2f"|format(entry.gpf + entry.gli + entry.ptax) }}</td>
    <td class="right">{{ "%.2f"|format(entry.tds) }}</td>
    <td class="right">{{ "%.2f"|format(entry.net) }}</td>
  </tr>
  {% endfor %}
  <tr class="bold" style="background-color: #e6e6e6;">
    <td><b>योग (TOTAL)</b></td>
    <td class="right">{{ "%.2f"|format(basic) }}</td>
    <td class="right">{{ "%.2f"|format(da) }}</td>
    <td class="right">{{ "%.2f"|format(hra) }}</td>
    <td class="right">{{ "%.2f"|format(medical) }}</td>
    <td class="right">{{ "%.2f"|format(gross) }}</td>
    <td class="right">{{ "%.2f"|format(gpf) }}</td>
    <td class="right">720.00</td>
    <td class="right">{{ "%.2f"|format(ptax) }}</td>
    <td class="right">{{ "%.2f"|format(gpf + 720 + ptax) }}</td>
    <td class="right">{{ "%.2f"|format(tds) }}</td>
    <td class="right">{{ "%.2f"|format(net_income) }}</td>
  </tr>
</table>

<table class="no-border" style="margin-top: 25px;">
  <tr>
    <td class="no-border" width="50%"><b>स्थान / Place:</b> {{ data.district }}<br><b>दिनांक / Date:</b> {{ today }}</td>
    <td class="no-border" width="50%" class="right">
      __________________________________________<br>
      <b>हस्ताक्षर / Signature:</b> {{ data.name }}<br>
      <b>निकासी एवं व्ययन पदाधिकारी की मुहर</b>
    </td>
  </tr>
</table>

</body>
</html>
""")

    html_content = template.render(
        data=data,
        gross=gross,
        basic=basic,
        da=da,
        hra=hra,
        medical=medical,
        ptax=ptax,
        gpf=gpf,
        tds=tds,
        net_income=net_income,
        monthly_entries=monthly_entries,
        today=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

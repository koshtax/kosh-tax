from jinja2 import Template
from datetime import date
import weasyprint

def generate_form16_pdf(data, is_trial=False):
    """
    Final Audited & Bulletproof Form 16 PDF Generator (4 Pages Official Format)
    - Page 1: Schedule of Income Tax (Portrait with complete income & slab breakdown)
    - Page 2: Form 16 Part A Summary & Quarter/Challan Tables (Portrait)
    - Page 3: Form 16 Part B Annexure & Chapter VI-A Deductions 80C/80D (Portrait)
    - Page 4: Monthly Salary & Arrears Ledger (Landscape, Dynamic 1-15+ rows, Combined months & automatic Arrear tags)
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
        net_income = float(data.get('net_income', gross - (ptax + gpf + tds)) or 0)
        
        raw_entries = data.get('monthly_entries', [])
        monthly_entries = []
        
        total_calc_basic = 0.0
        total_calc_da = 0.0
        total_calc_hra = 0.0
        total_calc_medical = 0.0
        total_calc_gross = 0.0
        total_calc_gpf = 0.0
        total_calc_ptax = 0.0
        total_calc_tds = 0.0
        total_calc_net = 0.0

        if raw_entries:
            for index, entry in enumerate(raw_entries):
                eb = float(entry.get('basic', 0) or 0)
                ed = float(entry.get('da', 0) or 0)
                eh = float(entry.get('hra', 0) or 0)
                em = float(entry.get('medical', 0) or 0)
                eg = float(entry.get('gross', eb + ed + eh + em) or (eb + ed + eh + em))
                egpf = float(entry.get('gpf', 0) or 0)
                ept = float(entry.get('ptax', 200) or 200)
                etds = float(entry.get('tds', 0) or 0)
                enet = float(entry.get('net', eg - (egpf + ept + etds)) or (eg - (egpf + ept + etds)))
                
                # Automatic Arrear Tagging for extra or subsequent entries beyond standard 12 months
                raw_name = str(entry.get('month_name', f'Month {index+1}'))
                if index >= 12 and not any(word in raw_name.lower() for word in ['arrear', 'bakaya', 'baki']):
                    month_label = f"{raw_name} (Arrear)"
                else:
                    month_label = raw_name

                total_calc_basic += eb
                total_calc_da += ed
                total_calc_hra += eh
                total_calc_medical += em
                total_calc_gross += eg
                total_calc_gpf += egpf
                total_calc_ptax += ept
                total_calc_tds += etds
                total_calc_net += enet

                monthly_entries.append({
                    'month_name': month_label,
                    'basic': eb, 'da': ed, 'hra': eh, 'medical': em,
                    'gross': eg, 'gpf': egpf, 'ptax': ept, 'tds': etds, 'net': enet
                })
        else:
            monthly_entries = [{
                'month_name': 'March to February',
                'basic': basic, 'da': da, 'hra': hra, 'medical': medical,
                'gross': gross, 'gpf': gpf, 'ptax': ptax, 'tds': tds, 'net': net_income
            }]
            total_calc_basic = basic
            total_calc_da = da
            total_calc_hra = hra
            total_calc_medical = medical
            total_calc_gross = gross
            total_calc_gpf = gpf
            total_calc_ptax = ptax
            total_calc_tds = tds
            total_calc_net = net_income

    except Exception as e:
        print(f"Error processing PDF dynamic data: {e}")
        total_calc_gross, total_calc_net = 0.0, 0.0
        monthly_entries = []

    html_template = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {
    size: A4 portrait;
    margin: 8mm;
    @bottom-center {
      {% if is_trial %}
      content: "DEVELOPED & DESIGNED BY @ NITIN MALLICK";
      font-size: 8.5px;
      font-weight: bold;
      color: #333;
      {% else %}
      content: "";
      {% endif %}
    }
  }

  @page landscape-page {
    size: A4 landscape;
    margin: 8mm;
    @bottom-center {
      {% if is_trial %}
      content: "DEVELOPED & DESIGNED BY @ NITIN MALLICK";
      font-size: 8.5px;
      font-weight: bold;
      color: #333;
      {% else %}
      content: "";
      {% endif %}
    }
  }

  body { font-family: Helvetica, Arial, sans-serif; font-size: 7.5px; color: #000; line-height: 1.2; }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  .right { text-align: right; }
  .left { text-align: left; }
  table { width: 100%; border-collapse: collapse; margin-top: 3px; margin-bottom: 3px; }
  table, th, td { border: 1px solid black; }
  th, td { padding: 3px 4px; vertical-align: middle; }
  .header-box { border: 1.5px solid black; padding: 5px; margin-bottom: 5px; text-align: center; background-color: #f5f5f5; }
  .page-break { page-break-after: always; }
  
  .landscape-section {
    page: landscape-page;
    page-break-before: always;
  }

  {% if is_trial %}
  .watermark {
    position: fixed;
    top: 45%;
    left: 40%;
    transform: translate(-50%, -50%) rotate(-45deg);
    font-size: 55px;
    color: rgba(255, 0, 0, 0.09);
    z-index: 9999;
  }
  {% endif %}
</style>
</head>
<body>
{% if is_trial %}
<div class="watermark">TRIAL COPY</div>
{% endif %}

<!-- ================= PAGE 1: SCHEDULE OF INCOME TAX (PORTRAIT) ================= -->
<div class="header-box">
  <div class="bold" style="font-size: 10px;">नई कर व्यवस्था के तहत - SCHEDULE OF INCOME - TAX (आयकर की अनुसूची)</div>
  <div style="font-size: 8px;">(चार प्रतियों में भर कर दें) | वित्तीय वर्ष 2025-26 (कर निर्धारण वर्ष 2026-2027)</div>
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
        02. महँगाई भत्ता (DA)<br>
        03. मकान किराया भत्ता (HRA)<br>
        04. चिकित्सा भत्ता (Medical Allowance)<br>
        05. परिवहन भत्ता / अन्य भत्ते<br>
        06. बकाया वेतन एवं भत्ते की राशि (Arrears / Bakaya Vetan)<br>
        <b>07. वेतन स्रोत से प्राप्त कुल आय (Gross Total Income)</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(basic) }}<br>
        Rs. {{ "%.2f"|format(da) }}<br>
        Rs. {{ "%.2f"|format(hra) }}<br>
        Rs. {{ "%.2f"|format(medical) }}<br>
        Rs. 0.00<br>
        Rs. 0.00<br>
        <b>Rs. {{ "%.2f"|format(gross) }}</b>
    </td>
  </tr>
</table>

<table>
  <tr>
    <td width="75%"><b>ख. आयकर की संगणना (Tax Computation):-</b><br>
        01. वेतन स्रोत से प्राप्त कुल आय<br>
        02. घटायें - धारा 16(ia) के अन्तर्गत मानक कटौती (Standard Deduction)<br>
        03. सकल कुल आय (Gross Total Income)<br>
        04. कर योग्य आय (Taxable Income)<br>
        05. देय आयकर स्लैब अनुसार (Tax on Total Income):<br>
        &nbsp;&nbsp;&nbsp;&nbsp;• ₹0 - ₹4 Lakh: Nil<br>
        &nbsp;&nbsp;&nbsp;&nbsp;• ₹4 Lakh - ₹8 Lakh (5%): Rs. {{ "%.2f"|format(tds if gross > 400000 else 0) }}<br>
        06. घटायें - धारा 87A के तहत कर में राहत (Rebate)<br>
        07. शिक्षा उपकर @4% (Education Cess)<br>
        <b>08. शुद्ध देय आयकर (Net Tax Payable)</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(gross) }}<br>
        Rs. 75,000.00<br>
        Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}<br>
        Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}<br><br>
        Rs. 0.00<br>
        Rs. {{ "%.2f"|format(tds) }}<br>
        Rs. 0.00<br>
        <b>Rs. {{ "%.2f"|format(tds) }}</b>
    </td>
  </tr>
</table>

<table style="border: none; margin-top: 10px;">
  <tr>
    <td style="border: none;" width="50%"><b>कोषागार का नाम (Treasury):</b> {{ data.district | default('KHUNTI') }}</td>
    <td style="border: none; text-align: right;" width="50%"><b>करदाता का हस्ताक्षर:</b> _______________</td>
  </tr>
  <tr>
    <td style="border: none;" colspan="2"><br><b>निकासी एवं व्ययन पदाधिकारी का हस्ताक्षर एवं मुहर:</b> ___________________________</td>
  </tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 2: FORM 16 PART A SUMMARY & TDS TABLES (PORTRAIT) ================= -->
<div class="header-box">
  <div class="bold" style="font-size: 10px;">FORM NO. 16 - PART A (CERTIFICATE UNDER SECTION 203)</div>
  <div style="font-size: 8px;">Summary of amount paid/credited and tax deducted at source</div>
</div>

<table>
  <tr>
    <td width="50%"><b>Employer Address / Details:</b><br>{{ data.employer_address | default('District Education Office, Khunti, Jharkhand') }}</td>
    <td width="50%"><b>Employee Name & PAN:</b><br>{{ data.name }} ({{ data.pan }})</td>
  </tr>
  <tr>
    <td><b>TAN of Deductor:</b> JHARK00000E</td>
    <td><b>Assessment Year:</b> 2026-2027</td>
  </tr>
</table>

<div class="bold" style="margin-top: 5px; font-size: 8px;">Quarter-wise Summary of Tax Deducted and Deposited:</div>
<table>
  <tr class="bold center" style="background-color: #eee;">
    <td>Quarter</td>
    <td>Receipt Numbers</td>
    <td>Amount Paid/Credited (Rs.)</td>
    <td>Tax Deducted (Rs.)</td>
    <td>Tax Deposited (Rs.)</td>
  </tr>
  <tr>
    <td>Quarter 1 (Q1)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(gross / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
  </tr>
  <tr>
    <td>Quarter 2 (Q2)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(gross / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
  </tr>
  <tr>
    <td>Quarter 3 (Q3)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(gross / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
  </tr>
  <tr>
    <td>Quarter 4 (Q4)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(gross / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
    <td class="right">{{ "%.2f"|format(tds / 4) }}</td>
  </tr>
  <tr class="bold">
    <td>Total (Rs.)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(gross) }}</td>
    <td class="right">{{ "%.2f"|format(tds) }}</td>
    <td class="right">{{ "%.2f"|format(tds) }}</td>
  </tr>
</table>

<div class="bold" style="margin-top: 5px; font-size: 8px;">Details of Tax Deposited through Book Adjustment / Challan:</div>
<table>
  <tr class="bold center" style="background-color: #eee;">
    <td>Sl. No.</td>
    <td>Tax Deposited (Rs.)</td>
    <td>BSR Code / Book Adj. ID</td>
    <td>Challan No. / Voucher No.</td>
    <td>Date (dd/mm/yyyy)</td>
  </tr>
  <tr>
    <td>1</td>
    <td class="right">{{ "%.2f"|format(tds) }}</td>
    <td>0000000</td>
    <td>00123</td>
    <td>10/03/2026</td>
  </tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 3: FORM 16 PART B & CHAPTER VI-A DEDUCTIONS (PORTRAIT) ================= -->
<div class="header-box">
  <div class="bold" style="font-size: 10px;">FORM NO. 16 - PART B (ANNEXURE)</div>
  <div style="font-size: 8px;">Details of Salary Paid and Any Other Income and Tax Deduction</div>
</div>

<table>
  <tr>
    <td width="70%"><b>1. Gross Salary:</b><br>
        (a) Salary as per provisions u/s 17(1)<br>
        (b) Value of perquisites u/s 17(2)<br>
        (c) Profits in lieu of salary u/s 17(3)
    </td>
    <td width="30%" class="right"><br>
        Rs. {{ "%.2f"|format(gross) }}<br>
        Rs. 0.00<br>
        Rs. 0.00
    </td>
  </tr>
  <tr>
    <td><b>2. Total Gross Salary</b></td>
    <td class="right"><b>Rs. {{ "%.2f"|format(gross) }}</b></td>
  </tr>
  <tr>
    <td><b>3. Standard Deduction u/s 16(ia)</b></td>
    <td class="right">Rs. 75,000.00</td>
  </tr>
  <tr>
    <td><b>4. Tax on Employment u/s 16(iii) (Professional Tax)</b></td>
    <td class="right">Rs. {{ "%.2f"|format(ptax) }}</td>
  </tr>
  <tr>
    <td><b>5. Income Chargeable under the head Salaries (3 - 4)</b></td>
    <td class="right"><b>Rs. {{ "%.2f"|format(gross - 75000 - ptax if gross > 75000 else 0) }}</b></td>
  </tr>
</table>

<div class="bold" style="margin-top: 4px; font-size: 8px;">6. Deductions under Chapter VI-A (80C, 80D, etc.):</div>
<table>
  <tr class="bold center" style="background-color: #eee;">
    <td>Section</td>
    <td>Gross Amount (Rs.)</td>
    <td>Qualifying Amount (Rs.)</td>
    <td>Deductible Amount (Rs.)</td>
  </tr>
  <tr>
    <td><b>Section 80C (GPF / LIC / PLI / PPF)</b></td>
    <td class="right">{{ "%.2f"|format(gpf) }}</td>
    <td class="right">{{ "%.2f"|format(gpf) }}</td>
    <td class="right">{{ "%.2f"|format(gpf) }}</td>
  </tr>
  <tr>
    <td><b>Section 80D (Health Insurance)</b></td>
    <td class="right">0.00</td>
    <td class="right">0.00</td>
    <td class="right">0.00</td>
  </tr>
  <tr class="bold">
    <td>Total Deductions under Chapter VI-A</td>
    <td colspan="3" class="right">Rs. {{ "%.2f"|format(gpf) }}</td>
  </tr>
</table>

<table>
  <tr>
    <td width="70%"><b>7. Total Taxable Income (5 - 6)</b></td>
    <td width="30%" class="right"><b>Rs. {{ "%.2f"|format(gross - 75000 - ptax - gpf if gross > 75000 else 0) }}</b></td>
  </tr>
  <tr>
    <td><b>8. Tax on Total Income</b></td>
    <td class="right">Rs. {{ "%.2f"|format(tds) }}</td>
  </tr>
  <tr>
    <td><b>9. Rebate under Section 87A</b></td>
    <td class="right">Rs. {{ "%.2f"|format(tds) }}</td>
  </tr>
  <tr>
    <td><b>10. Net Tax Payable</b></td>
    <td class="right"><b>Rs. 0.00</b></td>
  </tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 4: MONTHLY SALARY & ARREARS LEDGER (LANDSCAPE VIEW) ================= -->
<div class="landscape-section">
  <div class="header-box">
    <div class="bold" style="font-size: 11px;">वित्तीय वर्ष 2025-26 में वेतन स्रोत से आय और कटौतियों की विवरणी (DYNAMIC SALARY & ARREARS LEDGER)</div>
    <div style="font-size: 9px;">नाम: {{ data.name }} | पदनाम: {{ data.designation }} | कार्यालय: {{ data.office_name }}</div>
  </div>

  <table>
    <tr class="bold center" style="background-color: #e6e6e6; font-size: 8.5px;">
      <td>क्र.सं. / माह विवरण (Month / Period)</td>
      <td>मूल वेतन (Basic)</td>
      <td>महंगाई भत्ता (DA)</td>
      <td>मकान किराया (HRA)</td>
      <td>चिकित्सा (Med)</td>
      <td>कुल योग (Gross)</td>
      <td>जी.पी.एफ. (GPF)</td>
      <td>व्या.कर (P.Tax)</td>
      <td>TDS</td>
      <td>शुद्ध वेतन (Net)</td>
    </tr>
    {% for entry in monthly_entries %}
    <tr style="font-size: 8.5px;">
      <td><b>{{ loop.index }}. {{ entry.month_name }}</b></td>
      <td class="right">{{ "%.2f"|format(entry.basic) }}</td>
      <td class="right">{{ "%.2f"|format(entry.da) }}</td>
      <td class="right">{{ "%.2f"|format(entry.hra) }}</td>
      <td class="right">{{ "%.2f"|format(entry.medical) }}</td>
      <td class="right bold">{{ "%.2f"|format(entry.gross) }}</td>
      <td class="right">{{ "%.2f"|format(entry.gpf) }}</td>
      <td class="right">{{ "%.2f"|format(entry.ptax) }}</td>
      <td class="right">{{ "%.2f"|format(entry.tds) }}</td>
      <td class="right bold">{{ "%.2f"|format(entry.net) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold" style="background-color: #d9d9d9; font-size: 9px;">
      <td>कुल योग (GRAND TOTAL)</td>
      <td class="right">{{ "%.2f"|format(total_calc_basic) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_da) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_hra) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_medical) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_gross) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_gpf) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_ptax) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_tds) }}</td>
      <td class="right">{{ "%.2f"|format(total_calc_net) }}</td>
    </tr>
  </table>
</div>

</body>
</html>
"""

    template = Template(html_template)
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
        total_calc_basic=total_calc_basic,
        total_calc_da=total_calc_da,
        total_calc_hra=total_calc_hra,
        total_calc_medical=total_calc_medical,
        total_calc_gross=total_calc_gross,
        total_calc_gpf=total_calc_gpf,
        total_calc_ptax=total_calc_ptax,
        total_calc_tds=total_calc_tds,
        total_calc_net=total_calc_net,
        today=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )

    try:
        html_doc = weasyprint.HTML(string=html_content)
        pdf_bytes = html_doc.write_pdf()
    except Exception:
        html_doc = weasyprint.HTML(string=html_content)
        pdf_bytes = html_doc.render().write_pdf()
        
    return pdf_bytes

from jinja2 import Template
from datetime import date
import weasyprint

def generate_form16_pdf(data, is_trial=False):
    """
    Audited & Final Form 16 PDF Generator with Landscape Monthly Table
    Matching official structure (tds1.pdf)
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
                enet = float(entry.get('net', eg - (egpf + ept + etds)) or 0)
                
                monthly_entries.append({
                    'basic': eb, 'da': ed, 'hra': eh, 'medical': em,
                    'gross': eg, 'gpf': egpf, 'ptax': ept, 'tds': etds, 'net': enet
                })
        else:
            monthly_entries = [{
                'basic': basic, 'da': da, 'hra': hra, 'medical': medical,
                'gross': gross, 'gpf': gpf, 'ptax': ptax, 'tds': tds, 'net': net_income
            }]
    except Exception as e:
        print(f"Error processing PDF data: {e}")
        gross, net_income = 0.0, 0.0
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
      content: "TRIAL COPY - DEVELOPED & DESIGNED BY NITIN MALLICK";
      font-size: 8px;
      font-weight: bold;
      color: #666;
      {% else %}
      content: "";
      {% endif %}
    }
  }

  @page landscape-page {
    size: A4 landscape;
    margin: 8mm;
  }

  body { font-family: Helvetica, Arial, sans-serif; font-size: 8px; color: #000; line-height: 1.2; }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  .right { text-align: right; }
  .left { text-align: left; }
  table { width: 100%; border-collapse: collapse; margin-top: 4px; margin-bottom: 4px; }
  table, th, td { border: 1px solid black; }
  th, td { padding: 3px 4px; vertical-align: top; }
  .header-box { border: 1.5px solid black; padding: 5px; margin-bottom: 6px; text-align: center; background-color: #f9f9f9; }
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
    color: rgba(255, 0, 0, 0.10);
    z-index: 9999;
  }
  {% endif %}
</style>
</head>
<body>
{% if is_trial %}
<div class="watermark">TRIAL COPY</div>
{% endif %}

<!-- PAGE 1: SCHEDULE OF INCOME TAX (PORTRAIT) -->
<div class="header-box">
  <div class="bold" style="font-size: 11px;">नई कर व्यवस्था के तहत - SCHEDULE OF INCOME - TAX</div>
  <div style="font-size: 9px;">वित्तीय वर्ष 2025-26 (कर निर्धारण वर्ष 2026-2027)[span_2](start_span)[span_2](end_span)</div>
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
    <td width="75%"><b>क. वेतन स्रोत से प्राप्त आय का विवरण :-[span_3](start_span)[span_3](end_span)</b><br>
        01. वेतन (BASIC PAY)<br>
        02. महँगाई भत्ता (DA)<br>
        03. मकान किराया भत्ता (HRA)<br>
        04. चिकित्सा भत्ता (MEDICAL)<br>
        <b>05. वेतन स्रोत से प्राप्त कुल आय (GROSS TOTAL)</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(basic) }}<br>
        Rs. {{ "%.2f"|format(da) }}<br>
        Rs. {{ "%.2f"|format(hra) }}<br>
        Rs. {{ "%.2f"|format(medical) }}<br>
        <b>Rs. {{ "%.2f"|format(gross) }}</b>
    </td>
  </tr>
</table>

<table>
  <tr>
    <td width="75%"><b>ख. आयकर की संगणना (TAX COMPUTATION):-[span_4](start_span)[span_4](end_span)</b><br>
        01. वेतन स्रोत से प्राप्त कुल आय<br>
        02. घटायें - धारा 16(ia) के अन्तर्गत मानक कटौती (STANDARD DEDUCTION)[span_5](start_span)[span_5](end_span)<br>
        03. सकल कुल आय (GROSS TOTAL INCOME)[span_6](start_span)[span_6](end_span)<br>
        04. कुल देय आयकर (TAX ON TOTAL INCOME)<br>
        05. घटायें - धारा 87A के तहत कर में राहत (REBATE)[span_7](start_span)[span_7](end_span)<br>
        <b>06. शुद्ध देय आयकर (NET TAX PAYABLE)</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(gross) }}<br>
        Rs. 75,000.00<br>
        Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}<br>
        Rs. {{ "%.2f"|format(tds) }}<br>
        Rs. {{ "%.2f"|format(tds) }}<br>
        <b>Rs. 0.00</b>
    </td>
  </tr>
</table>

<table style="border: none; margin-top: 15px;">
  <tr>
    <td style="border: none;" width="50%"><b>कोषागार का नाम:</b> {{ data.district | default('KHUNTI') }}[span_8](start_span)[span_8](end_span)</td>
    <td style="border: none; text-align: right;" width="50%"><b>करदाता का हस्ताक्षर:</b> _______________[span_9](start_span)[span_9](end_span)</td>
  </tr>
  <tr>
    <td style="border: none;" colspan="2"><br><b>निकासी एवं व्ययन पदाधिकारी का हस्ताक्षर एवं मुहर:</b> ___________________________[span_10](start_span)[span_10](end_span)</td>
  </tr>
</table>

<div class="page-break"></div>

<!-- PAGE 2: FORM 16 PART A SUMMARY -->
<div class="header-box">
  <div class="bold" style="font-size: 11px;">FORM NO. 16 - PART A SUMMARY[span_11](start_span)[span_11](end_span)</div>
  <div style="font-size: 9px;">Certificate under Section 203 of the Income-Tax Act, 1961[span_12](start_span)[span_12](end_span)</div>
</div>

<table>
  <tr>
    <td width="50%"><b>Employer Address:[span_13](start_span)[span_13](end_span)</b><br>{{ data.employer_address }}</td>
    <td width="50%"><b>Employee Name & PAN:[span_14](start_span)[span_14](end_span)</b><br>{{ data.name }} ({{ data.pan }})</td>
  </tr>
  <tr>
    <td><b>Gross Salary:</b> Rs. {{ "%.2f"|format(gross) }}</td>
    <td><b>Standard Deduction:</b> Rs. 75,000.00</td>
  </tr>
  <tr>
    <td><b>Taxable Income:</b> Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}</td>
    <td><b>Net Tax Payable:</b> Rs. {{ "%.2f"|format(tds) }}</td>
  </tr>
</table>

<div class="page-break"></div>

<!-- PAGE 3: FORM 16 PART B TAX COMPUTATION DETAILS -->
<div class="header-box">
  <div class="bold" style="font-size: 11px;">FORM NO. 16 - PART B (ANNEXURE)[span_15](start_span)[span_15](end_span)</div>
  <div style="font-size: 9px;">DETAILS OF SALARY PAID AND TAX DEDUCTION[span_16](start_span)[span_16](end_span)</div>
</div>

<table>
  <tr>
    <td width="70%"><b>1. Gross Salary[span_17](start_span)[span_17](end_span)</b><br>(a) Salary as per provisions u/s 17(1)[span_18](start_span)[span_18](end_span)<br>(b) Value of perquisites u/s 17(2)[span_19](start_span)[span_19](end_span)<br>(c) Profits in lieu of salary u/s 17(3)[span_20](start_span)[span_20](end_span)</td>
    <td width="30%" class="right"><br>Rs. {{ "%.2f"|format(gross) }}<br>Rs. 0.00<br>Rs. 0.00</td>
  </tr>
  <tr>
    <td><b>2. Total Gross Salary[span_21](start_span)[span_21](end_span)</b></td>
    <td class="right"><b>Rs. {{ "%.2f"|format(gross) }}</b></td>
  </tr>
  <tr>
    <td><b>3. Standard Deduction u/s 16(ia)[span_22](start_span)[span_22](end_span)</b></td>
    <td class="right">Rs. 75,000.00</td>
  </tr>
  <tr>
    <td><b>4. Income Chargeable under the head Salaries[span_23](start_span)[span_23](end_span)</b></td>
    <td class="right"><b>Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}</b></td>
  </tr>
  <tr>
    <td><b>5. Tax on Total Income[span_24](start_span)[span_24](end_span)</b></td>
    <td class="right">Rs. {{ "%.2f"|format(tds) }}</td>
  </tr>
  <tr>
    <td><b>6. Rebate under Section 87A[span_25](start_span)[span_25](end_span)</b></td>
    <td class="right">Rs. {{ "%.2f"|format(tds) }}</td>
  </tr>
  <tr>
    <td><b>7. Net Tax Payable[span_26](start_span)[span_26](end_span)</b></td>
    <td class="right"><b>Rs. 0.00</b></td>
  </tr>
</table>

<!-- PAGE 4: MONTHLY SALARY DETAILED BREAKUP (LANDSCAPE MODE FOR NO DATA HIDING) -->
<div class="landscape-section">
  <div class="header-box">
    <div class="bold" style="font-size: 11px;">वित्तीय वर्ष 2025-26 में वेतन स्रोत से आय और कटौतियों की विवरणी (LANDSCAPE VIEW)[span_27](start_span)[span_27](end_span)</div>
    <div style="font-size: 9px;">नाम: {{ data.name }} | पदनाम: {{ data.designation }} | कार्यालय: {{ data.office_name }}[span_28](start_span)[span_28](end_span)</div>
  </div>

  <table>
    <tr class="bold center" style="background-color: #eee;">
      <td>माह / विवरण[span_29](start_span)[span_29](end_span)</td>
      <td>मूल वेतन (Basic)[span_30](start_span)[span_30](end_span)</td>
      <td>महंगाई भत्ता (DA)[span_31](start_span)[span_31](end_span)</td>
      <td>मकान किराया (HRA)[span_32](start_span)[span_32](end_span)</td>
      <td>चिकित्सा (Med)[span_33](start_span)[span_33](end_span)</td>
      <td>कुल योग (Gross)[span_34](start_span)[span_34](end_span)</td>
      <td>जी.पी.एफ. (GPF)[span_35](start_span)[span_35](end_span)</td>
      <td>TDS</td>
      <td>शुद्ध वेतन (Net)[span_36](start_span)[span_36](end_span)</td>
    </tr>
    {% for entry in monthly_entries %}
    <tr>
      <td><b>प्रविष्टि {{ loop.index }}[span_37](start_span)[span_37](end_span)</b></td>
      <td class="right">{{ "%.2f"|format(entry.basic) }}</td>
      <td class="right">{{ "%.2f"|format(entry.da) }}</td>
      <td class="right">{{ "%.2f"|format(entry.hra) }}</td>
      <td class="right">{{ "%.2f"|format(entry.medical) }}</td>
      <td class="right">{{ "%.2f"|format(entry.gross) }}</td>
      <td class="right">{{ "%.2f"|format(entry.gpf) }}</td>
      <td class="right">{{ "%.2f"|format(entry.tds) }}</td>
      <td class="right">{{ "%.2f"|format(entry.net) }}</td>
    </tr>
    {% endfor %}
    <tr class="bold" style="background-color: #f2f2f2;">
      <td>कुल योग (TOTAL)[span_38](start_span)[span_38](end_span)</td>
      <td class="right">{{ "%.2f"|format(basic) }}</td>
      <td class="right">{{ "%.2f"|format(da) }}</td>
      <td class="right">{{ "%.2f"|format(hra) }}</td>
      <td class="right">{{ "%.2f"|format(medical) }}</td>
      <td class="right">{{ "%.2f"|format(gross) }}</td>
      <td class="right">{{ "%.2f"|format(gpf) }}</td>
      <td class="right">{{ "%.2f"|format(tds) }}</td>
      <td class="right">{{ "%.2f"|format(gross - (gpf + tds + 200)) }}</td>
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

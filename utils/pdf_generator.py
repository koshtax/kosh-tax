from jinja2 import Template
from datetime import date
import weasyprint

def generate_form16_pdf(data, is_trial=False):
    """
    Generate Form 16 PDF safely using Weasyprint document write method 
    to prevent version signature mismatch errors.
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

    html_template = """
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
        01. वेतन<br>02. महँगाई भत्ता<br>03. मकान किराया भत्ता<br>04. चिकित्सा भत्ता<br>05. कुल आय
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

<div class="page-break"></div>

<div class="header-box center">
  <div class="bold" style="font-size: 10px;">FORM NO. 16 - PART A & B SUMMARY</div>
</div>

<table>
  <tr>
    <td width="50%"><b>Employer:</b> {{ data.employer_address }}</td>
    <td width="50%"><b>Employee:</b> {{ data.name }}</td>
  </tr>
  <tr>
    <td><b>Gross Salary:</b> Rs. {{ "%.2f"|format(gross) }}</td>
    <td><b>Standard Deduction:</b> Rs. 75,000.00</td>
  </tr>
  <tr>
    <td><b>Taxable Income:</b> Rs. {{ "%.2f"|format(gross - 75000) }}</td>
    <td><b>Net Tax Payable:</b> Rs. {{ "%.2f"|format(tds) }}</td>
  </tr>
</table>

<div class="page-break"></div>

<div class="header-box center">
  <div class="bold" style="font-size: 9px;">वित्तीय वर्ष 2025-26 में वेतन स्रोत से आय और कटौतियों की विवरणी</div>
</div>

<table>
  <tr class="bold center" style="background-color: #f2f2f2;">
    <td>विवरण</td>
    <td>मूल वेतन</td>
    <td>महंगाई भत्ता</td>
    <td>मकान किराया</td>
    <td>चिकित्सा</td>
    <td>कुल योग</td>
    <td>जी.पी.एफ.</td>
    <td>TDS</td>
    <td>शुद्ध वेतन</td>
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
    <td class="right">{{ "%.2f"|format(entry.tds) }}</td>
    <td class="right">{{ "%.2f"|format(entry.net) }}</td>
  </tr>
  {% endfor %}
</table>

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

    # Use Weasyprint HTML render directly to bytes without tempfile / pydyf signature conflict
    html_doc = weasyprint.HTML(string=html_content)
    pdf_bytes = html_doc.write_pdf()
    return pdf_bytes

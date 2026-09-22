from weasyprint import HTML
from jinja2 import Template
from datetime import date

def generate_form16_pdf(data, is_trial=False):
    """
    Generate Form 16 PDF strictly in uppercase
    """
    try:
        gross_total = float(data.get('basic', 0)) + float(data.get('da', 0)) + float(data.get('hra', 0)) + float(data.get('medical', 0)) + float(data.get('arrear_da', 0)) + float(data.get('arrear_pay', 0))
    except:
        gross_total = 0.0

    template = Template("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 10px; text-transform: uppercase; }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  table, th, td { border: 1px solid black; }
  th, td { padding: 5px; }
  {% if is_trial %}
  .watermark {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-45deg);
    font-size: 60px;
    color: rgba(255, 0, 0, 0.2);
    z-index: 9999;
  }
  {% endif %}
</style>
</head>
<body>
{% if is_trial %}
<div class="watermark">TRIAL COPY</div>
{% endif %}

<div class="center">
  <h2>FORM NO. 16 - PART A & B</h2>
  <p>ASSESSMENT YEAR: {{ data.assessment_year }}</p>
</div>

<table>
  <tr>
    <td><b>EMPLOYER / DDO ADDRESS:</b><br>{{ data.employer_address }}<br><b>TAN:</b> {{ data.ddo_tan }}</td>
    <td><b>EMPLOYEE NAME:</b><br>{{ data.name }}<br><b>PAN:</b> {{ data.pan }}<br><b>DESIGNATION:</b> {{ data.designation }}</td>
  </tr>
  <tr>
    <td><b>OFFICE / SCHOOL:</b><br>{{ data.office_name }}</td>
    <td><b>DISTRICT:</b> {{ data.district }} | <b>GPF NO:</b> {{ data.gpf_no }}</td>
  </tr>
</table>

<h3>SALARY COMPONENTS</h3>
<table>
  <tr class="bold">
    <th>COMPONENT</th>
    <th>AMOUNT (RS)</th>
  </tr>
  <tr><td>BASIC PAY</td><td>{{ data.basic }}</td></tr>
  <tr><td>DA</td><td>{{ data.da }}</td></tr>
  <tr><td>HRA</td><td>{{ data.hra }}</td></tr>
  <tr><td>MEDICAL</td><td>{{ data.medical }}</td></tr>
  <tr><td>ARREAR DA</td><td>{{ data.arrear_da }}</td></tr>
  <tr><td>ARREAR PAY</td><td>{{ data.arrear_pay }}</td></tr>
  <tr class="bold"><td>GROSS SALARY</td><td>{{ gross_total }}</td></tr>
</table>

<div style="margin-top: 30px;">
  <p>CERTIFIED THAT THE INFORMATION PROVIDED ABOVE IS TRUE AND CORRECT.</p>
  <div style="margin-top: 40px; text-align: right;">
    ________________________<br>
    DDO OFFICER: {{ data.ddo_officer }}<br>
    FATHER NAME: {{ data.ddo_father }}<br>
    DRAWING AND DISBURSING OFFICER<br>
    DATE: {{ today }}
  </div>
</div>

{% if is_trial %}
<div style="margin-top: 30px; padding: 10px; background: #fff3cd; border: 2px solid red; text-align: center; color: red;">
  <b>TRIAL COPY - FOR VERIFICATION ONLY<br>DO NOT USE FOR OFFICIAL PURPOSES</b>
</div>
{% endif %}

</body>
</html>
""")

    html_content = template.render(
        data=data,
        gross_total=gross_total,
        today=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

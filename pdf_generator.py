from weasyprint import HTML
from jinja2 import Template
from datetime import date

def generate_form16_pdf(data, is_trial=False):
    """
    Generate Form 16 PDF
    """
    template = Template("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; font-size: 10px; }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  table { width: 100%; border-collapse: collapse; }
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
  <h2>FORM NO. 16 - PART A</h2>
</div>

<table>
  <tr>
    <td><b>Employer:</b><br>{{ data.office_name }}</td>
    <td><b>Employee:</b><br>{{ data.name }}<br>PAN: {{ data.pan }}</td>
  </tr>
  <tr>
    <td><b>Assessment Year:</b><br>{{ data.assessment_year }}</td>
    <td><b>Period:</b><br>01.04.2024 - 31.03.2025</td>
  </tr>
</table>

<h3>Salary Details</h3>
<table>
  <tr class="bold">
    <th>Component</th>
    <th>Amount (₹)</th>
  </tr>
  <tr><td>Basic Pay</td><td>{{ data.basic }}</td></tr>
  <tr><td>DA</td><td>{{ data.da }}</td></tr>
  <tr><td>HRA</td><td>{{ data.hra }}</td></tr>
  <tr><td>Medical</td><td>{{ data.medical }}</td></tr>
  <tr class="bold"><td>Gross</td><td>{{ data.basic + data.da + data.hra + data.medical }}</td></tr>
</table>

<div style="margin-top: 30px;">
  <p>Certified that the information above is true and correct.</p>
  <div style="margin-top: 40px; text-align: right;">
    ________________________<br>
    DDO Signature<br>
    Date: {{ today }}
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
        today=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

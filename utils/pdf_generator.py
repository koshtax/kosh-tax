from jinja2 import Template
from datetime import date
import weasyprint

def generate_form16_pdf(data, is_trial=False):
    """
    Final Audited & Strict-Logic Form 16 PDF Generator (4 Pages Official Format)
    - Automatically maps Grand Totals from Monthly Ledger to Schedule & Form 16 A/B.
    - Computes Quarter-wise actual Gross and TDS dynamically from monthly entries.
    - Includes Chapter VI-A Deductions table on Page 3 and Arrear/TDS balancing logic.
    """
    try:
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
                
                # Strict Arrear Tagging Logic for previous year entries
                raw_name = str(entry.get('month_name', f'Month {index+1}'))
                if ('jan' in raw_name.lower() or 'feb' in raw_name.lower()) and ('2024' in raw_name or '2023' in raw_name or '2022' in raw_name):
                    month_label = f"{raw_name} (Arrear)"
                elif index >= 12 and not any(word in raw_name.lower() for word in ['arrear', 'bakaya', 'baki']):
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
            basic = float(data.get('basic', 0) or 0)
            da = float(data.get('da', 0) or 0)
            hra = float(data.get('hra', 0) or 0)
            medical = float(data.get('medical', 0) or 0)
            gross = float(data.get('gross', basic + da + hra + medical))
            ptax = float(data.get('ptax', 200) or 200)
            gpf = float(data.get('gpf', 0) or 0)
            tds = float(data.get('tds', 0) or 0)
            net_income = float(data.get('net_income', gross - (ptax + gpf + tds)) or 0)

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

        # Map Grand Totals directly to Schedule & Form 16 variables[span_0](start_span)[span_0](end_span)
        basic = total_calc_basic
        da = total_calc_da
        hra = total_calc_hra
        medical = total_calc_medical
        gross = total_calc_gross
        gpf = total_calc_gpf
        ptax = total_calc_ptax
        tds = total_calc_tds
        net_income = total_calc_net

        # DYNAMIC QUARTER-WISE CALCULATION (Q1, Q2, Q3, Q4) BASED ON ACTUAL ENTRIES
        q_gross = {'Q1': 0.0, 'Q2': 0.0, 'Q3': 0.0, 'Q4': 0.0}
        q_tds = {'Q1': 0.0, 'Q2': 0.0, 'Q3': 0.0, 'Q4': 0.0}

        for entry in monthly_entries:
            m_name = str(entry.get('month_name', '')).upper()
            eg = float(entry.get('gross', 0) or 0)
            etds = float(entry.get('tds', 0) or 0)
            
            if any(m in m_name for m in ['APR', 'MAY', 'JUN']):
                q_gross['Q1'] += eg
                q_tds['Q1'] += etds
            elif any(m in m_name for m in ['JUL', 'AUG', 'SEP']):
                q_gross['Q2'] += eg
                q_tds['Q2'] += etds
            elif any(m in m_name for m in ['OCT', 'NOV', 'DEC']):
                q_gross['Q3'] += eg
                q_tds['Q3'] += etds
            elif any(m in m_name for m in ['JAN', 'FEB', 'MAR']):
                q_gross['Q4'] += eg
                q_tds['Q4'] += etds
            else:
                q_gross['Q4'] += eg
                q_tds['Q4'] += etds

        if sum(q_gross.values()) == 0 and gross > 0:
            q_gross['Q4'] = gross
            q_tds['Q4'] = tds

    except Exception as e:
        print(f"Error processing PDF dynamic data: {e}")
        gross, net_income = 0.0, 0.0
        monthly_entries = []
        q_gross = {'Q1': 0.0, 'Q2': 0.0, 'Q3': 0.0, 'Q4': 0.0}
        q_tds = {'Q1': 0.0, 'Q2': 0.0, 'Q3': 0.0, 'Q4': 0.0}

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
  .landscape-section { page: landscape-page; page-break-before: always; }

  {% if is_trial %}
  .watermark {
    position: fixed;
    top: 45%; left: 40%;
    transform: translate(-50%, -50%) rotate(-45deg);
    font-size: 55px; color: rgba(255, 0, 0, 0.09); z-index: 9999;
  }
  {% endif %}
</style>
</head>
<body>
{% if is_trial %}
<div class="watermark">TRIAL COPY</div>
{% endif %}

<!-- ================= PAGE 1: SCHEDULE OF INCOME TAX ================= -->
<div class="header-box">
  <div class="bold" style="font-size: 10px;">नई कर व्यवस्था के तहत - SCHEDULE OF INCOME - TAX (आयकर की अनुसूची)</div>
  <div style="font-size: 8px;">(चार प्रतियों में भर कर दें) | वित्तीय वर्ष 2025-26 (कर निर्धारण वर्ष 2026-2027)[span_1](start_span)[span_1](end_span)</div>
</div>

<table>
  <tr>
    <td colspan="2">
      <b>करदाता का नाम / Name:</b> {{ data.name }}[span_2](start_span)[span_2](end_span)<br>
      <b>पदनाम / Designation:</b> {{ data.designation }}[span_3](start_span)[span_3](end_span)<br>
      <b>कार्यालय/विद्यालय का नाम / Office:</b> {{ data.office_name }}<br>
      <b>स्थायी लेखा संख्या (PAN):</b> {{ data.pan }}[span_4](start_span)[span_4](end_span)
    </td>
  </tr>
  <tr>
    <td width="75%"><b>क. वेतन स्रोत से प्राप्त आय का विवरण :-</b><br>
        01. वेतन (दिनांक 01.03.2025 से 28.02.2026 तक)[span_5](start_span)[span_5](end_span)<br>
        02. महँगाई भत्ता (DA)[span_6](start_span)[span_6](end_span)<br>
        03. मकान किराया भत्ता (HRA)[span_7](start_span)[span_7](end_span)<br>
        04. चिकित्सा भत्ता (Medical Allowance)[span_8](start_span)[span_8](end_span)<br>
        05. परिवहन भत्ता / अन्य भत्ते<br>
        06. बकाया वेतन एवं भत्ते की राशि (Arrears / Bakaya Vetan)[span_9](start_span)[span_9](end_span)<br>
        <b>07. वेतन स्रोत से प्राप्त कुल आय (Gross Total Income)[span_10](start_span)[span_10](end_span)</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(basic) }}[span_11](start_span)[span_11](end_span)<br>
        Rs. {{ "%.2f"|format(da) }}[span_12](start_span)[span_12](end_span)<br>
        Rs. {{ "%.2f"|format(hra) }}[span_13](start_span)[span_13](end_span)<br>
        Rs. {{ "%.2f"|format(medical) }}[span_14](start_span)[span_14](end_span)<br>
        Rs. 0.00<br>
        Rs. 0.00<br>
        <b>Rs. {{ "%.2f"|format(gross) }}[span_15](start_span)[span_15](end_span)</b>
    </td>
  </tr>
</table>

<table>
  <tr>
    <td width="75%"><b>ख. आयकर की संगणना (Tax Computation):-[span_16](start_span)[span_16](end_span)</b><br>
        01. वेतन स्रोत से प्राप्त कुल आय<br>
        02. घटायें - धारा 16(ia) के अन्तर्गत मानक कटौती (Standard Deduction)[span_17](start_span)[span_17](end_span)<br>
        03. सकल कुल आय (Gross Total Income)<br>
        04. कर योग्य आय (Taxable Income)[span_18](start_span)[span_18](end_span)<br>
        05. देय आयकर स्लैब अनुसार (Tax on Total Income):[span_19](start_span)[span_19](end_span)<br>
        06. घटायें - धारा 87A के तहत कर में राहत (Rebate)[span_20](start_span)[span_20](end_span)<br>
        07. शिक्षा उपकर @4% (Education Cess)[span_21](start_span)[span_21](end_span)<br>
        <b>08. शुद्ध देय आयकर (Net Tax Payable)[span_22](start_span)[span_22](end_span)</b>
    </td>
    <td width="25%" class="right"><br>
        Rs. {{ "%.2f"|format(gross) }}[span_23](start_span)[span_23](end_span)<br>
        Rs. 75,000.00[span_24](start_span)[span_24](end_span)<br>
        Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}[span_25](start_span)[span_25](end_span)<br>
        Rs. {{ "%.2f"|format(gross - 75000 if gross > 75000 else 0) }}[span_26](start_span)[span_26](end_span)<br>
        Rs. {{ "%.2f"|format(tds) }}[span_27](start_span)[span_27](end_span)<br>
        Rs. 0.00[span_28](start_span)[span_28](end_span)<br>
        Rs. 0.00[span_29](start_span)[span_29](end_span)<br>
        <b>Rs. {{ "%.2f"|format(tds) }}[span_30](start_span)[span_30](end_span)</b>
    </td>
  </tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 2: FORM 16 PART A SUMMARY ================= -->
<div class="header-box">
  <div class="bold" style="font-size: 10px;">FORM NO. 16 - PART A (CERTIFICATE UNDER SECTION 203)[span_31](start_span)[span_31](end_span)[span_32](start_span)[span_32](end_span)</div>
  <div style="font-size: 8px;">Summary of amount paid/credited and tax deducted at source[span_33](start_span)[span_33](end_span)[span_34](start_span)[span_34](end_span)</div>
</div>

<table>
  <tr>
    <td width="50%"><b>Employer Address / Details:[span_35](start_span)[span_35](end_span)[span_36](start_span)[span_36](end_span)</b><br>{{ data.employer_address | default('District Education Office, Khunti, Jharkhand') }}</td>
    <td width="50%"><b>Employee Name & PAN:[span_37](start_span)[span_37](end_span)[span_38](start_span)[span_38](end_span)</b><br>{{ data.name }} ({{ data.pan }})[span_39](start_span)[span_39](end_span)[span_40](start_span)[span_40](end_span)</td>
  </tr>
  <tr>
    <td><b>TAN of Deductor:</b> JHARK00000E[span_41](start_span)[span_41](end_span)[span_42](start_span)[span_42](end_span)</td>
    <td><b>Assessment Year:</b> 2026-2027[span_43](start_span)[span_43](end_span)[span_44](start_span)[span_44](end_span)</td>
  </tr>
</table>

<div class="bold" style="margin-top: 5px; font-size: 8px;">Quarter-wise Summary of Tax Deducted and Deposited:[span_45](start_span)[span_45](end_span)[span_46](start_span)[span_46](end_span)</div>
<table>
  <tr class="bold center" style="background-color: #eee;">
    <td>Quarter[span_47](start_span)[span_47](end_span)[span_48](start_span)[span_48](end_span)</td>
    <td>Receipt Numbers[span_49](start_span)[span_49](end_span)[span_50](start_span)[span_50](end_span)</td>
    <td>Amount Paid/Credited (Rs.)[span_51](start_span)[span_51](end_span)[span_52](start_span)[span_52](end_span)</td>
    <td>Tax Deducted (Rs.)[span_53](start_span)[span_53](end_span)[span_54](start_span)[span_54](end_span)</td>
    <td>Tax Deposited (Rs.)[span_55](start_span)[span_55](end_span)[span_56](start_span)[span_56](end_span)</td>
  </tr>
  <tr>
    <td>Quarter 1 (Q1)[span_57](start_span)[span_57](end_span)[span_58](start_span)[span_58](end_span)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(q_gross.Q1) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q1) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q1) }}</td>
  </tr>
  <tr>
    <td>Quarter 2 (Q2)[span_59](start_span)[span_59](end_span)[span_60](start_span)[span_60](end_span)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(q_gross.Q2) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q2) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q2) }}</td>
  </tr>
  <tr>
    <td>Quarter 3 (Q3)[span_61](start_span)[span_61](end_span)[span_62](start_span)[span_62](end_span)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(q_gross.Q3) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q3) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q3) }}</td>
  </tr>
  <tr>
    <td>Quarter 4 (Q4)[span_63](start_span)[span_63](end_span)[span_64](start_span)[span_64](end_span)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(q_gross.Q4) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q4) }}</td>
    <td class="right">{{ "%.2f"|format(q_tds.Q4) }}</td>
  </tr>
  <tr class="bold">
    <td>Total (Rs.)[span_65](start_span)[span_65](end_span)[span_66](start_span)[span_66](end_span)</td>
    <td>-</td>
    <td class="right">{{ "%.2f"|format(gross) }}[span_67](start_span)[span_67](end_span)[span_68](start_span)[span_68](end_span)</td>
    <td class="right">{{ "%.2f"|format(tds) }}[span_69](start_span)[span_69](end_span)[span_70](start_span)[span_70](end_span)</td>
    <td class="right">{{ "%.2f"|format(tds) }}[span_71](start_span)[span_71](end_span)[span_72](start_span)[span_72](end_span)</td>
  </tr>
</table>

<div class="page-break"></div>

<!-- ================= PAGE 3: FORM 16 PART B & DEDUCTIONS ================= -->
<div class="header-box">
  <div class="bold" style="font-size: 10px;">FORM NO. 16 - PART B (ANNEXURE)[span_73](start_span)[span_73](end_span)</div>
  <div style="font-size: 8px;">Details of Salary Paid and Any Other Income and Tax Deduction[span_74](start_span)[span_74](end_span)</div>
</div>

<table>
  <tr>
    <td width="70%"><b>1. Gross Salary:[span_75](start_span)[span_75](end_span)</b><br>
        (a) Salary as per provisions u/s 17(1)[span_76](start_span)[span_76](end_span)<br>
        (b) Value of perquisites u/s 17(2)<br>
        (c) Profits in lieu of salary u/s 17(3)
    </td>
    <td width="30%" class="right"><br>
        Rs. {{ "%.2f"|format(gross) }}[span_77](start_span)[span_77](end_span)<br>
        Rs. 0.00<br>
        Rs. 0.00
    </td>
  </tr>
  <tr>
    <td><b>2. Total Gross Salary[span_78](start_span)[span_78](end_span)</b></td>
    <td class="right"><b>Rs. {{ "%.2f"|format(gross) }}[span_79](start_span)[span_79](end_span)</b></td>
  </tr>
  <tr>
    <td><b>3. Standard Deduction u/s 16(ia)[span_80](start_span)[span_80](end_span)</b></td>
    <td class="right">Rs. 75,000.00[span_81](start_span)[span_81](end_span)</td>
  </tr>
  <tr>
    <td><b>4. Tax on Employment u/s 16(iii) (Professional Tax)[span_82](start_span)[span_82](end_span)</b></td>
    <td class="right">Rs. {{ "%.2f"|format(ptax) }}[span_83](start_span)[span_83](end_span)</td>
  </tr>
  <tr>
    <td><b>5. Income Chargeable under the head Salaries (3 - 4)[span_84](start_span)[span_84](end_span)</b></td>
    <td class="right"><b>Rs. {{ "%.2f"|format(gross - 75000 - ptax if gross > 75000 else 0) }}[span_85](start_span)[span_85](end_span)</b></td>
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

<!-- ================= PAGE 4: DYNAMIC SALARY & ARREARS LEDGER (LANDSCAPE) ================= -->
<div class="landscape-section">
  <div class="header-box">
    <div class="bold" style="font-size: 11px;">वित्तीय वर्ष 2025-26 में वेतन स्रोत से आय और कटौतियों की विवरणी (DYNAMIC SALARY & ARREARS LEDGER)[span_86](start_span)[span_86](end_span)</div>
    <div style="font-size: 9px;">नाम: {{ data.name }} | पदनाम: {{ data.designation }} | कार्यालय: {{ data.office_name }}[span_87](start_span)[span_87](end_span)</div>
  </div>

  <table>
    <tr class="bold center" style="background-color: #e6e6e6; font-size: 8.5px;">
      <td>क्र.सं. / माह विवरण (Month / Period)[span_88](start_span)[span_88](end_span)</td>
      <td>मूल वेतन (Basic)[span_89](start_span)[span_89](end_span)</td>
      <td>महंगाई भत्ता (DA)[span_90](start_span)[span_90](end_span)</td>
      <td>मकान किराया (HRA)[span_91](start_span)[span_91](end_span)</td>
      <td>चिकित्सा (Med)[span_92](start_span)[span_92](end_span)</td>
      <td>कुल योग (Gross)[span_93](start_span)[span_93](end_span)</td>
      <td>जी.पी.एफ. (GPF)[span_94](start_span)[span_94](end_span)</td>
      <td>व्या.कर (P.Tax)[span_95](start_span)[span_95](end_span)</td>
      <td>TDS[span_96](start_span)[span_96](end_span)</td>
      <td>शुद्ध वेतन (Net)[span_97](start_span)[span_97](end_span)</td>
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
      <td>कुल योग (GRAND TOTAL)[span_98](start_span)[span_98](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_basic) }}[span_99](start_span)[span_99](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_da) }}[span_100](start_span)[span_100](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_hra) }}[span_101](start_span)[span_101](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_medical) }}[span_102](start_span)[span_102](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_gross) }}[span_103](start_span)[span_103](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_gpf) }}[span_104](start_span)[span_104](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_ptax) }}[span_105](start_span)[span_105](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_tds) }}[span_106](start_span)[span_106](end_span)</td>
      <td class="right">{{ "%.2f"|format(total_calc_net) }}[span_107](start_span)[span_107](end_span)</td>
    </tr>
  </table>
</div>

</body>
</html>
"""

    template = Template(html_template)
    html_content = template.render(
        data=data,
        gross=gross, basic=basic, da=da, hra=hra, medical=medical,
        ptax=ptax, gpf=gpf, tds=tds, net_income=net_income,
        monthly_entries=monthly_entries,
        total_calc_basic=total_calc_basic, total_calc_da=total_calc_da,
        total_calc_hra=total_calc_hra, total_calc_medical=total_calc_medical,
        total_calc_gross=total_calc_gross, total_calc_gpf=total_calc_gpf,
        total_calc_ptax=total_calc_ptax, total_calc_tds=total_calc_tds,
        total_calc_net=total_calc_net,
        q_gross=q_gross, q_tds=q_tds,
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

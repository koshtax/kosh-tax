"""
pdf_generator.py
Audited dynamic PDF generator for Schedule of Income + Form 16 Part A/B + Salary Ledger.

Design goals
------------
1. Does NOT persist PDF/reference data. It only renders the `data` argument.
2. Keeps monthly-ledger totals as the source of truth.
3. Uses A4 portrait for normal sections and A4 landscape for wide salary ledgers.
4. Tables are fluid: columns use percentages, text wraps, long tables continue across pages,
   and table headers repeat automatically.
5. FY, AY, standard deduction, TAN, employer details and tax-rule values are configurable
   through `data["pdf_config"]`; no hard-coded employee/reference-PDF data is required.
6. Avoids the old "catch everything and silently return zeros" behaviour.
7. Supports arbitrary extra salary-ledger columns through `data["monthly_entries"]`.

Dependencies:
    pip install jinja2 weasyprint
    # Recommended for salary-slip year detection:
    pip install pymupdf
    # Fallback extractor:
    pip install pypdf

Expected data shape (minimum):
{
    "name": "...",
    "designation": "...",
    "office_name": "...",
    "pan": "...",
    "monthly_entries": [
        {
            "month_name": "Apr 2025",
            "basic": 0,
            "da": 0,
            "hra": 0,
            "medical": 0,
            "gross": 0,          # optional; calculated if omitted
            "gpf": 0,
            "ptax": 200,
            "tds": 0,
            "net": 0             # optional; calculated if omitted
        }
    ],
    "pdf_config": {
        "financial_year": None,
        "assessment_year": None,
        "tax_year": None,
        "standard_deduction": 75000,
        "tan": "...",
        "employer_address": "...",
        "place": "KHUNTI",
        "tax_rules": {...}
    }
}
"""

from datetime import date, datetime
from html import escape
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Template
import weasyprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num(value: Any, default: float = 0.0) -> float:
    """Safe numeric conversion without silently converting malformed values."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid numeric value: {value!r}")


def _money(value: Any) -> float:
    return round(_num(value), 2)


def _fmt(value: Any) -> str:
    return f"{_num(value):,.2f}"


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _month_quarter(month_name: str) -> str:
    """
    Month detection is deliberately token-based rather than substring-only,
    so values such as 'March 2026 (Arrear)' remain correctly classified.
    """
    s = _clean(month_name).lower()

    month_map = {
        "apr": "Q1", "april": "Q1",
        "may": "Q1",
        "jun": "Q1", "june": "Q1",
        "jul": "Q2", "july": "Q2",
        "aug": "Q2", "august": "Q2",
        "sep": "Q2", "sept": "Q2", "september": "Q2",
        "oct": "Q3", "october": "Q3",
        "nov": "Q3", "november": "Q3",
        "dec": "Q3", "december": "Q3",
        "jan": "Q4", "january": "Q4",
        "feb": "Q4", "february": "Q4",
        "mar": "Q4", "march": "Q4",
    }
    for token, quarter in month_map.items():
        if token in s:
            return quarter
    return "Q4"


def _is_arrear(month_name: str, index: int, explicit: Any = None) -> bool:
    if explicit is not None:
        return bool(explicit)

    s = _clean(month_name).lower()
    arrear_words = ("arrear", "bakaya", "baki", "à¤¬à¤à¤¾à¤¯à¤¾")
    if any(word in s for word in arrear_words):
        return True

    # Preserve the original generator's practical convention:
    # entries after the normal 12-month sequence are arrears.
    return index >= 12


def _normalise_entries(raw_entries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    entries: List[Dict[str, Any]] = []
    totals = {
        "basic": 0.0,
        "da": 0.0,
        "hra": 0.0,
        "medical": 0.0,
        "gross": 0.0,
        "gpf": 0.0,
        "ptax": 0.0,
        "tds": 0.0,
        "net": 0.0,
        "arrear_gross": 0.0,
        "arrear_tds": 0.0,
    }

    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"monthly_entries[{index}] must be a dictionary")

        basic = _money(raw.get("basic", 0))
        da = _money(raw.get("da", 0))
        hra = _money(raw.get("hra", 0))
        medical = _money(raw.get("medical", 0))

        # Gross is calculated when missing, but an explicitly supplied gross
        # remains authoritative because the calling ledger may contain other allowances.
        gross = _money(raw["gross"]) if raw.get("gross") not in (None, "") else _money(
            basic + da + hra + medical
        )

        gpf = _money(raw.get("gpf", 0))
        ptax = _money(raw.get("ptax", 200))
        tds = _money(raw.get("tds", 0))

        net = _money(raw["net"]) if raw.get("net") not in (None, "") else _money(
            gross - gpf - ptax - tds
        )

        month_name = _clean(raw.get("month_name"), f"Month {index + 1}")
        arrear = _is_arrear(month_name, index, raw.get("is_arrear"))

        row = {
            "month_name": month_name,
            "is_arrear": arrear,
            "basic": basic,
            "da": da,
            "hra": hra,
            "medical": medical,
            "gross": gross,
            "gpf": gpf,
            "ptax": ptax,
            "tds": tds,
            "net": net,
            # Preserve optional/custom fields without storing them anywhere.
            "extra": {
                k: v for k, v in raw.items()
                if k not in {
                    "month_name", "is_arrear", "basic", "da", "hra",
                    "medical", "gross", "gpf", "ptax", "tds", "net"
                }
            },
        }
        entries.append(row)

        for key in ("basic", "da", "hra", "medical", "gross", "gpf", "ptax", "tds", "net"):
            totals[key] += row[key]

        if arrear:
            totals["arrear_gross"] += gross
            totals["arrear_tds"] += tds

    return entries, {k: _money(v) for k, v in totals.items()}


def _build_quarters(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    q = {
        "Q1": {"gross": 0.0, "tds": 0.0},
        "Q2": {"gross": 0.0, "tds": 0.0},
        "Q3": {"gross": 0.0, "tds": 0.0},
        "Q4": {"gross": 0.0, "tds": 0.0},
    }
    for row in entries:
        quarter = _month_quarter(row["month_name"])
        q[quarter]["gross"] += row["gross"]
        q[quarter]["tds"] += row["tds"]
    for quarter in q:
        q[quarter]["gross"] = _money(q[quarter]["gross"])
        q[quarter]["tds"] = _money(q[quarter]["tds"])
    return q



_YEAR_RANGE_RE = re.compile(r"\b(?:FY|F\.Y\.|Financial\s+Year|Tax\s+Year|Assessment\s+Year|AY)\s*[:\-]?\s*(20\d{2})\s*[-/]\s*(\d{2}|20\d{2})\b", re.I)
_MONTH_YEAR_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s*[-/,]?\s*(20\d{2})\b",
    re.I,
)
_NUMERIC_DATE_RE = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])[\-/](0?[1-9]|1[0-2])[\-/](20\d{2})\b"
)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _normalise_year_range(start_year: int, end_part: str) -> str:
    """Return YYYY-YY for a financial/tax year range."""
    end_year = int(end_part)
    if end_year < 100:
        end_year += 2000
    if end_year != start_year + 1:
        raise ValueError(f"Invalid year range: {start_year}-{end_part}")
    return f"{start_year}-{str(end_year)[-2:]}"


def _fy_from_month_year(month: int, year: int) -> str:
    """Indian FY: Apr-Dec belongs to current year; Jan-Mar to previous year."""
    start = year if month >= 4 else year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _extract_pdf_text(pdf_path: str) -> str:
    """Extract text without storing or persisting the source PDF."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Salary-slip PDF not found: {pdf_path}")

    errors = []

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        try:
            return "\n".join(page.get_text("text") or "" for page in doc)
        finally:
            doc.close()
    except Exception as exc:
        errors.append(f"PyMuPDF: {exc}")

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        errors.append(f"pypdf: {exc}")

    raise RuntimeError(
        "Could not extract salary-slip PDF text. Install PyMuPDF "
        "(recommended) or pypdf. " + " | ".join(errors)
    )


def detect_year_info_from_text(text: str, filename: str = "") -> Dict[str, Any]:
    """
    Detect FY / AY / Tax Year from salary-slip text.

    Priority:
      1. Explicit FY / Tax Year / AY labels.
      2. Salary month + year.
      3. Filename as supporting evidence only.

    Conflicts are reported instead of silently selecting one year.
    """
    raw = text or ""
    name = str(filename or "")
    combined = f"{raw}\n{name}"

    explicit = []
    for match in _YEAR_RANGE_RE.finditer(combined):
        label = match.group(0)
        start = int(match.group(1))
        end_part = match.group(2)
        try:
            yr = _normalise_year_range(start, end_part)
        except ValueError:
            continue

        low = label.lower()
        kind = "assessment_year" if ("assessment" in low or re.search(r"\bay\b", low)) else (
            "tax_year" if "tax" in low else "financial_year"
        )
        explicit.append((kind, yr, "pdf_text" if match.start() < len(raw) else "filename"))

    month_years = []
    for match in _MONTH_YEAR_RE.finditer(raw):
        month = _MONTHS[match.group(1).lower()]
        year = int(match.group(2))
        month_years.append((month, year))

    for match in _NUMERIC_DATE_RE.finditer(raw):
        day, month, year = map(int, match.groups())
        # Only use plausible salary-period dates.
        if 1 <= month <= 12:
            month_years.append((month, year))

    # Deduplicate month/year observations.
    month_years = list(dict.fromkeys(month_years))
    month_fys = list(dict.fromkeys(_fy_from_month_year(m, y) for m, y in month_years))

    # Resolve explicit values.
    fy_candidates = []
    ay_candidates = []
    ty_candidates = []
    for kind, yr, _source in explicit:
        if kind == "financial_year":
            fy_candidates.append(yr)
        elif kind == "assessment_year":
            ay_candidates.append(yr)
            # AY N+1 corresponds to FY N-N+1.
            start = int(yr[:4]) - 1
            fy_candidates.append(f"{start}-{str(start + 1)[-2:]}")
        elif kind == "tax_year":
            ty_candidates.append(yr)
            fy_candidates.append(yr)

    fy_candidates = list(dict.fromkeys(fy_candidates))
    ay_candidates = list(dict.fromkeys(ay_candidates))
    ty_candidates = list(dict.fromkeys(ty_candidates))

    warnings = []

    if len(fy_candidates) > 1:
        warnings.append(f"Conflicting explicit financial/tax years detected: {fy_candidates}")
    if len(month_fys) > 1:
        warnings.append(f"Salary-slip months span multiple FYs: {month_fys}")

    explicit_fy = fy_candidates[0] if len(fy_candidates) == 1 else None
    month_fy = month_fys[0] if len(month_fys) == 1 else None

    if explicit_fy and month_fy and explicit_fy != month_fy:
        warnings.append(
            f"Explicit year {explicit_fy} conflicts with salary month/year evidence {month_fy}"
        )

    # Do not use filename-only year as authoritative.
    filename_fys = []
    for m in re.finditer(r"\b(20\d{2})\s*[-_/]\s*(\d{2}|20\d{2})\b", name):
        try:
            filename_fys.append(_normalise_year_range(int(m.group(1)), m.group(2)))
        except ValueError:
            pass
    filename_fys = list(dict.fromkeys(filename_fys))

    if filename_fys and explicit_fy and explicit_fy not in filename_fys:
        warnings.append(f"Filename year {filename_fys} conflicts with PDF year {explicit_fy}")
    if filename_fys and month_fy and month_fy not in filename_fys:
        warnings.append(f"Filename year {filename_fys} conflicts with salary month/year {month_fy}")

    resolved_fy = explicit_fy or month_fy
    confidence = "high" if explicit_fy and not warnings else (
        "medium" if month_fy and not warnings else "low"
    )

    if not resolved_fy:
        return {
            "financial_year": None,
            "assessment_year": None,
            "tax_year": None,
            "period_start": None,
            "period_end": None,
            "confidence": "low",
            "source": "none",
            "warnings": warnings or ["Could not confidently detect FY from salary-slip PDF."],
            "requires_manual_confirmation": True,
        }

    start_year = int(resolved_fy[:4])
    end_year = start_year + 1

    # Under the official transition, FY 2025-26 remains AY 2026-27;
    # FY 2026-27 onward uses Tax Year under the 2025 Act.
    if start_year < 2026:
        assessment_year = f"{end_year}-{str(end_year + 1)[-2:]}"
        tax_year = None
        legal_year_label = f"FY {resolved_fy} / AY {assessment_year}"
    else:
        assessment_year = None
        tax_year = resolved_fy
        legal_year_label = f"FY {resolved_fy} / Tax Year {tax_year}"

    return {
        "financial_year": resolved_fy,
        "assessment_year": assessment_year,
        "tax_year": tax_year,
        "period_start": f"{start_year}-04-01",
        "period_end": f"{end_year}-03-31",
        "confidence": confidence,
        "source": "pdf_text" if explicit_fy else "salary_month",
        "legal_year_label": legal_year_label,
        "warnings": warnings,
        "requires_manual_confirmation": bool(warnings) or confidence == "low",
    }


def detect_year_info_from_salary_pdf(pdf_path: str) -> Dict[str, Any]:
    """Detect year information from a salary-slip PDF without persisting its contents."""
    text = _extract_pdf_text(pdf_path)
    return detect_year_info_from_text(text, filename=Path(pdf_path).name)


def _resolve_year_config(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve year information before rendering.

    `data["year_info"]` can be supplied by the application after PDF detection.
    `data["salary_pdf_path"]` is supported as a convenience fallback.
    """
    supplied = data.get("year_info")
    if isinstance(supplied, dict) and supplied.get("financial_year"):
        detected = dict(supplied)
    elif data.get("salary_pdf_path"):
        detected = detect_year_info_from_salary_pdf(data["salary_pdf_path"])
    else:
        detected = {}

    if detected.get("financial_year"):
        config["financial_year"] = detected["financial_year"]
        config["assessment_year"] = detected.get("assessment_year")
        config["tax_year"] = detected.get("tax_year")
        config["year_info"] = detected

    return config


def _default_config() -> Dict[str, Any]:
    return {
        "financial_year": "2025-26",
        "assessment_year": "2026-27",
        "standard_deduction": 75000.0,
        "tan": "",
        "employer_address": "",
        "place": "",
        "employer_designation": "",
        "tax_rules": {},
    }


def _merge_config(data: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _default_config()
    supplied = data.get("pdf_config") or {}
    if isinstance(supplied, dict):
        cfg.update(supplied)
    return cfg


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">

<style>
@page {
    size: A4 portrait;
    margin: 7mm 7mm 8mm 7mm;

    @bottom-center {
        content: "{{ footer_text }}";
        font-size: 7.5pt;
        font-weight: bold;
    }
}

@page landscape {
    size: A4 landscape;
    margin: 6mm 6mm 7mm 6mm;

    @bottom-center {
        content: "{{ footer_text }}";
        font-size: 7.5pt;
        font-weight: bold;
    }
}

* { box-sizing: border-box; }

html, body {
    margin: 0;
    padding: 0;
}

body {
    font-family: "Noto Sans Devanagari", "Noto Sans", "DejaVu Sans",
                 Arial, Helvetica, sans-serif;
    color: #000;
    font-size: 7.4pt;
    line-height: 1.15;
}

.page {
    width: 100%;
}

.landscape-page {
    page: landscape;
    page-break-before: always;
}

.page-break {
    break-after: page;
    page-break-after: always;
}

.keep {
    break-inside: avoid;
    page-break-inside: avoid;
}

h1, h2, h3, p { margin: 0; padding: 0; }

.title-box {
    border: 1.2pt solid #000;
    padding: 4pt 5pt;
    margin-bottom: 4pt;
    text-align: center;
    break-inside: avoid;
}

.title {
    font-size: 10pt;
    font-weight: 700;
}

.subtitle {
    font-size: 7.5pt;
    margin-top: 2pt;
}

.section-title {
    font-weight: 700;
    font-size: 8pt;
    margin: 4pt 0 2pt;
}

table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    margin: 2.5pt 0 4pt;
}

thead { display: table-header-group; }
tfoot { display: table-footer-group; }

tr {
    break-inside: avoid;
    page-break-inside: avoid;
}

th, td {
    border: 0.55pt solid #000;
    padding: 2.4pt 3pt;
    vertical-align: middle;
    overflow-wrap: anywhere;
    word-break: normal;
}

th {
    font-weight: 700;
    text-align: center;
}

.shade { background: #eeeeee; }
.total { font-weight: 700; background: #e5e5e5; }

.left { text-align: left; }
.center { text-align: center; }
.right { text-align: right; }
.bold { font-weight: 700; }

.small { font-size: 6.7pt; }
.tiny { font-size: 6pt; }

.no-border td {
    border: 0;
}

.signature-row {
    margin-top: 10pt;
}

.watermark {
    position: fixed;
    top: 42%;
    left: 32%;
    transform: rotate(-42deg);
    font-size: 48pt;
    color: rgba(220, 0, 0, 0.09);
    z-index: -1;
}

/* Prevent a table from being wider than the printable A4 area. */
.auto-fit {
    max-width: 100%;
}

/* Wide monthly ledger */
.ledger {
    font-size: 6.8pt;
}

.ledger th, .ledger td {
    padding: 2pt 2.4pt;
}

.ledger .month-col { width: 17%; }
.ledger .num-col { width: 9.22%; }

@media print {
    .page-break { break-after: page; }
}
</style>
</head>

<body>

{% if is_trial %}
<div class="watermark">TRIAL COPY</div>
{% endif %}

<!-- ============================================================= -->
<!-- PAGE 1: SCHEDULE OF INCOME TAX                               -->
<!-- ============================================================= -->
<div class="page">

<div class="title-box">
    <div class="title">à¤¨à¤ à¤à¤° à¤µà¥à¤¯à¤µà¤¸à¥à¤¥à¤¾ à¤à¥ à¤¤à¤¹à¤¤ - SCHEDULE OF INCOME - TAX (à¤à¤¯à¤à¤° à¤à¥ à¤à¤¨à¥à¤¸à¥à¤à¥)</div>
    <div class="subtitle">
        (à¤à¤¾à¤° à¤ªà¥à¤°à¤¤à¤¿à¤¯à¥à¤ à¤®à¥à¤ à¤­à¤° à¤à¤° à¤¦à¥à¤) |
        à¤µà¤¿à¤¤à¥à¤¤à¥à¤¯ à¤µà¤°à¥à¤· {{ config.financial_year }}
        {% if config.tax_year %}
            (à¤à¤° à¤µà¤°à¥à¤· {{ config.tax_year }})
        {% elif config.assessment_year %}
            (à¤à¤° à¤¨à¤¿à¤°à¥à¤§à¤¾à¤°à¤£ à¤µà¤°à¥à¤· {{ config.assessment_year }})
        {% endif %}
    </div>
</div>

<table class="auto-fit">
    <tbody>
    <tr>
        <td colspan="2">
            <b>à¤à¤°à¤¦à¤¾à¤¤à¤¾ à¤à¤¾ à¤¨à¤¾à¤® / Name:</b> {{ data.name }}<br>
            <b>à¤ªà¤¦à¤¨à¤¾à¤® / Designation:</b> {{ data.designation }}<br>
            <b>à¤à¤¾à¤°à¥à¤¯à¤¾à¤²à¤¯/à¤µà¤¿à¤¦à¥à¤¯à¤¾à¤²à¤¯ à¤à¤¾ à¤¨à¤¾à¤® / Office:</b> {{ data.office_name }}<br>
            <b>à¤¸à¥à¤¥à¤¾à¤¯à¥ à¤²à¥à¤à¤¾ à¤¸à¤à¤à¥à¤¯à¤¾ (PAN):</b> {{ data.pan }}
        </td>
    </tr>
    <tr>
        <td style="width:75%">
            <b>à¤. à¤µà¥à¤¤à¤¨ à¤¸à¥à¤°à¥à¤¤ à¤¸à¥ à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤ à¤à¤¯ à¤à¤¾ à¤µà¤¿à¤µà¤°à¤£ :-</b><br>
            01. à¤µà¥à¤¤à¤¨<br>
            02. à¤®à¤¹à¤à¤à¤¾à¤ à¤­à¤¤à¥à¤¤à¤¾ (DA)<br>
            03. à¤®à¤à¤¾à¤¨ à¤à¤¿à¤°à¤¾à¤¯à¤¾ à¤­à¤¤à¥à¤¤à¤¾ (HRA)<br>
            04. à¤à¤¿à¤à¤¿à¤¤à¥à¤¸à¤¾ à¤­à¤¤à¥à¤¤à¤¾ (Medical Allowance)<br>
            05. à¤ªà¤°à¤¿à¤µà¤¹à¤¨ à¤­à¤¤à¥à¤¤à¤¾ / à¤à¤¨à¥à¤¯ à¤­à¤¤à¥à¤¤à¥<br>
            06. à¤¬à¤à¤¾à¤¯à¤¾ à¤µà¥à¤¤à¤¨ à¤à¤µà¤ à¤­à¤¤à¥à¤¤à¥ à¤à¥ à¤°à¤¾à¤¶à¤¿ (Arrears / Bakaya Vetan)<br>
            <b>07. à¤µà¥à¤¤à¤¨ à¤¸à¥à¤°à¥à¤¤ à¤¸à¥ à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤ à¤à¥à¤² à¤à¤¯ (Gross Total Income)</b>
        </td>
        <td style="width:25%" class="right">
            <br>
            Rs. {{ money(basic) }}<br>
            Rs. {{ money(da) }}<br>
            Rs. {{ money(hra) }}<br>
            Rs. {{ money(medical) }}<br>
            Rs. 0.00<br>
            Rs. {{ money(arrear_gross) }}<br>
            <b>Rs. {{ money(gross) }}</b>
        </td>
    </tr>
    </tbody>
</table>

<table class="auto-fit">
    <tbody>
    <tr>
        <td style="width:75%">
            <b>à¤. à¤à¤¯à¤à¤° à¤à¥ à¤¸à¤à¤à¤£à¤¨à¤¾ (Tax Computation):-</b><br>
            01. à¤µà¥à¤¤à¤¨ à¤¸à¥à¤°à¥à¤¤ à¤¸à¥ à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤ à¤à¥à¤² à¤à¤¯<br>
            02. à¤à¤à¤¾à¤¯à¥à¤ - à¤§à¤¾à¤°à¤¾ 16(ia) à¤à¥ à¤à¤¨à¥à¤¤à¤°à¥à¤à¤¤ à¤®à¤¾à¤¨à¤ à¤à¤à¥à¤¤à¥ (Standard Deduction)<br>
            03. à¤¸à¤à¤² à¤à¥à¤² à¤à¤¯ (Gross Total Income)<br>
            04. à¤à¤° à¤¯à¥à¤à¥à¤¯ à¤à¤¯ (Taxable Income)<br>
            05. à¤¦à¥à¤¯ à¤à¤¯à¤à¤° (Tax on Total Income)<br>
            06. à¤à¤à¤¾à¤¯à¥à¤ - à¤§à¤¾à¤°à¤¾ 87A à¤à¥ à¤¤à¤¹à¤¤ à¤à¤° à¤®à¥à¤ à¤°à¤¾à¤¹à¤¤ (Rebate)<br>
            07. à¤¶à¤¿à¤à¥à¤·à¤¾ à¤à¤ªà¤à¤° / Cess<br>
            <b>08. à¤¶à¥à¤¦à¥à¤§ à¤¦à¥à¤¯ à¤à¤¯à¤à¤° (Net Tax Payable)</b>
        </td>
        <td style="width:25%" class="right">
            <br>
            Rs. {{ money(gross) }}<br>
            Rs. {{ money(standard_deduction) }}<br>
            Rs. {{ money(taxable_before_chapter) }}<br>
            Rs. {{ money(taxable_income) }}<br>
            Rs. {{ money(tax_on_total_income) }}<br>
            Rs. {{ money(rebate) }}<br>
            Rs. {{ money(cess) }}<br>
            <b>Rs. {{ money(net_tax_payable) }}</b>
        </td>
    </tr>
    </tbody>
</table>

{% if config.tax_rules %}
<div class="section-title">Configured Tax Rules / à¤à¤° à¤¨à¤¿à¤¯à¤®</div>
<table class="small">
    <thead>
    <tr class="shade">
        <th>Sl.</th><th>Rule / Slab</th><th>Rate / Value</th>
    </tr>
    </thead>
    <tbody>
    {% for rule in tax_rules %}
    <tr>
        <td class="center">{{ loop.index }}</td>
        <td>{{ rule.label }}</td>
        <td class="right">{{ rule.value }}</td>
    </tr>
    {% endfor %}
    </tbody>
</table>
{% endif %}

</div>

<div class="page-break"></div>

<!-- ============================================================= -->
<!-- PAGE 2: FORM 16 PART A                                       -->
<!-- ============================================================= -->
<div class="page">

<div class="title-box">
    <div class="title">FORM NO. 16 - PART A</div>
    <div class="subtitle">Certificate under Section 203 â Summary of amount paid/credited and tax deducted at source</div>
</div>

<table>
    <tbody>
    <tr>
        <td style="width:50%">
            <b>Name and address of the Employer</b><br>
            {{ config.employer_address or data.office_name }}
        </td>
        <td style="width:50%">
            <b>Name and address of the Employee</b><br>
            {{ data.name }}<br>
            {{ data.office_name }}
        </td>
    </tr>
    <tr>
        <td>
            <b>PAN of the Deductor:</b> {{ config.tan }}
        </td>
        <td>
            <b>PAN of the Employee:</b> {{ data.pan }}
        </td>
    </tr>
    <tr>
        <td>
            {% if config.assessment_year %}
                <b>Assessment Year:</b> {{ config.assessment_year }}
            {% else %}
                <b>Tax Year:</b> {{ config.tax_year }}
            {% endif %}
        </td>
        <td><b>Employee Reference No.:</b> {{ data.employee_reference_no or "-" }}</td>
    </tr>
    <tr>
        <td><b>Period with Employer:</b> {{ data.period_from or "-" }} to {{ data.period_to or "-" }}</td>
        <td><b>Designation:</b> {{ data.designation }}</td>
    </tr>
    </tbody>
</table>

<div class="section-title">Quarter-wise Summary of Tax Deducted and Deposited</div>

<table>
    <thead>
    <tr class="shade">
        <th style="width:15%">Quarter</th>
        <th style="width:24%">Receipt Numbers</th>
        <th style="width:20%">Amount Paid/Credited (Rs.)</th>
        <th style="width:20%">Tax Deducted (Rs.)</th>
        <th style="width:21%">Tax Deposited (Rs.)</th>
    </tr>
    </thead>
    <tbody>
    {% for qname in ["Q1","Q2","Q3","Q4"] %}
    <tr>
        <td class="center">Quarter {{ loop.index }} ({{ qname }})</td>
        <td class="center">{{ quarter_receipts.get(qname, "-") }}</td>
        <td class="right">{{ money(quarters[qname].gross) }}</td>
        <td class="right">{{ money(quarters[qname].tds) }}</td>
        <td class="right">{{ money(quarters[qname].tds) }}</td>
    </tr>
    {% endfor %}
    <tr class="total">
        <td>Total (Rs.)</td>
        <td class="center">-</td>
        <td class="right">{{ money(gross) }}</td>
        <td class="right">{{ money(tds) }}</td>
        <td class="right">{{ money(tds) }}</td>
    </tr>
    </tbody>
</table>

<div class="section-title">I. Details of Tax Deducted and Deposited through Book Adjustment</div>
<table class="small">
    <thead>
    <tr class="shade">
        <th>BIN / 24G No.</th>
        <th>DDO Serial No.</th>
        <th>Date of Transfer Voucher</th>
        <th>Amount of Tax Deducted (Rs.)</th>
        <th>Amount of Tax Deposited (Rs.)</th>
        <th>Status</th>
    </tr>
    </thead>
    <tbody>
    {% for row in book_adjustment_rows %}
    <tr>
        <td>{{ row.bin }}</td>
        <td>{{ row.ddo_serial }}</td>
        <td>{{ row.date }}</td>
        <td class="right">{{ money(row.tax_deducted) }}</td>
        <td class="right">{{ money(row.tax_deposited) }}</td>
        <td>{{ row.status }}</td>
    </tr>
    {% else %}
    <tr><td colspan="6" class="center">No book-adjustment entries supplied</td></tr>
    {% endfor %}
    </tbody>
</table>

<div class="section-title">II. Details of Tax Deducted and Deposited through Challan</div>
<table class="small">
    <thead>
    <tr class="shade">
        <th>BIN</th>
        <th>Transfer Voucher / Challan Serial No.</th>
        <th>Date</th>
        <th>Amount of Tax Deposited (Rs.)</th>
        <th>Matching Status</th>
    </tr>
    </thead>
    <tbody>
    {% for row in challan_rows %}
    <tr>
        <td>{{ row.bin }}</td>
        <td>{{ row.serial_no }}</td>
        <td>{{ row.date }}</td>
        <td class="right">{{ money(row.tax_deposited) }}</td>
        <td>{{ row.status }}</td>
    </tr>
    {% else %}
    <tr><td colspan="5" class="center">No challan entries supplied</td></tr>
    {% endfor %}
    </tbody>
</table>

<table>
    <tbody>
    <tr>
        <td style="width:50%">
            <b>Verification</b><br>
            I {{ data.name }} certify that the information given above is true,
            complete and correct to the best of the information supplied.
        </td>
        <td style="width:50%">
            <b>Amount of tax deducted:</b> Rs. {{ money(tds) }}<br>
            <b>Amount of tax deposited:</b> Rs. {{ money(tds) }}<br>
            <b>Place:</b> {{ config.place }}<br>
            <b>Date:</b> {{ today }}
        </td>
    </tr>
    </tbody>
</table>

</div>

<div class="page-break"></div>

<!-- ============================================================= -->
<!-- PAGE 3: FORM 16 PART B                                       -->
<!-- ============================================================= -->
<div class="page">

<div class="title-box">
    <div class="title">FORM NO. 16 - PART B (ANNEXURE)</div>
    <div class="subtitle">Details of Salary Paid and Any Other Income and Tax Deduction</div>
</div>

<table>
    <tbody>
    <tr>
        <td style="width:75%">
            <b>1. GROSS SALARY</b><br>
            (A) Salary as per provisions contained in sec. 17(1)<br>
            (B) Value of perquisites u/s 17(2)<br>
            (C) Profits in lieu of salary u/s 17(3)<br>
            (D) TOTAL
        </td>
        <td style="width:25%" class="right">
            <br>
            Rs. {{ money(gross) }}<br>
            Rs. 0.00<br>
            Rs. 0.00<br>
            <b>Rs. {{ money(gross) }}</b>
        </td>
    </tr>
    <tr>
        <td>2. LESS: Allowance to the extent exempt u/s 10</td>
        <td class="right">Rs. 0.00</td>
    </tr>
    <tr>
        <td>3. BALANCE (1 - 2)</td>
        <td class="right"><b>Rs. {{ money(gross) }}</b></td>
    </tr>
    <tr>
        <td>4(a). Standard Deduction</td>
        <td class="right">Rs. {{ money(standard_deduction) }}</td>
    </tr>
    <tr>
        <td>4(b). Tax on Employment</td>
        <td class="right">Rs. {{ money(ptax) }}</td>
    </tr>
    <tr>
        <td>5. AGGREGATE OF 4(a) AND 4(b)</td>
        <td class="right"><b>Rs. {{ money(standard_deduction + ptax) }}</b></td>
    </tr>
    <tr>
        <td>6. INCOME CHARGEABLE UNDER THE HEAD SALARY (3 - 5)</td>
        <td class="right"><b>Rs. {{ money(salary_income) }}</b></td>
    </tr>
    <tr>
        <td>7. ADD: ANY OTHER INCOME REPORTED BY THE EMPLOYEE</td>
        <td class="right">Rs. {{ money(other_income) }}</td>
    </tr>
    <tr>
        <td>8. GROSS TOTAL INCOME (6 + 7)</td>
        <td class="right"><b>Rs. {{ money(gross_total_income) }}</b></td>
    </tr>
    </tbody>
</table>

<div class="section-title">9. DEDUCTIONS UNDER CHAPTER VI-A</div>

<table class="small">
    <thead>
    <tr class="shade">
        <th style="width:39%">Section / Particular</th>
        <th style="width:20%">Gross Amount (Rs.)</th>
        <th style="width:20%">Qualifying Amount (Rs.)</th>
        <th style="width:21%">Deductible Amount (Rs.)</th>
    </tr>
    </thead>
    <tbody>
    {% for row in deductions %}
    <tr>
        <td><b>{{ row.section }}</b></td>
        <td class="right">{{ money(row.gross) }}</td>
        <td class="right">{{ money(row.qualifying) }}</td>
        <td class="right">{{ money(row.deductible) }}</td>
    </tr>
    {% endfor %}
    <tr class="total">
        <td>Total deductible amount under Chapter VI-A</td>
        <td></td>
        <td></td>
        <td class="right">Rs. {{ money(chapter_via_total) }}</td>
    </tr>
    </tbody>
</table>

<table>
    <tbody>
    <tr>
        <td style="width:75%">10. AGGREGATE OF DEDUCTIBLE AMOUNT UNDER CHAPTER VI-A</td>
        <td style="width:25%" class="right">Rs. {{ money(chapter_via_total) }}</td>
    </tr>
    <tr>
        <td>11. TOTAL INCOME (8 - 10)</td>
        <td class="right"><b>Rs. {{ money(total_income) }}</b></td>
    </tr>
    <tr>
        <td>12. TAX ON TOTAL INCOME</td>
        <td class="right">Rs. {{ money(tax_on_total_income) }}</td>
    </tr>
    <tr>
        <td>13. LESS: REBATE UNDER SECTION 87A</td>
        <td class="right">Rs. {{ money(rebate) }}</td>
    </tr>
    <tr>
        <td>14. TOTAL TAX PAYABLE (12 - 13)</td>
        <td class="right"><b>Rs. {{ money(tax_after_rebate) }}</b></td>
    </tr>
    <tr>
        <td>15. EDUCATION CESS / HEALTH & EDUCATION CESS</td>
        <td class="right">Rs. {{ money(cess) }}</td>
    </tr>
    <tr>
        <td>16. TAX PAYABLE (14 + 15)</td>
        <td class="right"><b>Rs. {{ money(tax_after_cess) }}</b></td>
    </tr>
    <tr>
        <td>17. LESS: RELIEF UNDER SECTION 89</td>
        <td class="right">Rs. {{ money(relief_89) }}</td>
    </tr>
    <tr>
        <td>18. TAX PAYABLE (16 - 17)</td>
        <td class="right"><b>Rs. {{ money(net_tax_payable) }}</b></td>
    </tr>
    </tbody>
</table>

<div class="small">
    <b>Note:</b> Deduction limits and tax treatment are taken from the supplied
    <code>pdf_config</code>/input rules. This generator does not independently certify
    statutory correctness for a particular assessment year.
</div>

<table class="no-border signature-row">
    <tbody>
    <tr>
        <td style="width:50%; height:35pt">Place: {{ config.place }}<br>Date: {{ today }}</td>
        <td style="width:50%; text-align:right; height:35pt">
            Signature of person responsible for deduction of tax<br>
            Working in the capacity of {{ config.employer_designation or data.designation }}
        </td>
    </tr>
    </tbody>
</table>

</div>

<div class="page-break"></div>

<!-- ============================================================= -->
<!-- PAGE 4+: DYNAMIC SALARY & ARREARS LEDGER                    -->
<!-- ============================================================= -->
<div class="landscape-page">

<div class="title-box">
    <div class="title">
        à¤µà¤¿à¤¤à¥à¤¤à¥à¤¯ à¤µà¤°à¥à¤· {{ config.financial_year }} à¤®à¥à¤ à¤µà¥à¤¤à¤¨ à¤¸à¥à¤°à¥à¤¤ à¤¸à¥ à¤à¤¯ à¤à¤° à¤à¤à¥à¤¤à¤¿à¤¯à¥à¤ à¤à¥ à¤µà¤¿à¤µà¤°à¤£à¥
    </div>
    <div class="subtitle">
        à¤¨à¤¾à¤®: {{ data.name }} |
        à¤ªà¤¦à¤¨à¤¾à¤®: {{ data.designation }} |
        à¤à¤¾à¤°à¥à¤¯à¤¾à¤²à¤¯: {{ data.office_name }}
    </div>
</div>

<table class="ledger">
    <thead>
    <tr class="shade">
        <th class="month-col">à¤à¥à¤°.à¤¸à¤. / à¤®à¤¾à¤¹ à¤µà¤¿à¤µà¤°à¤£</th>
        <th class="num-col">à¤®à¥à¤² à¤µà¥à¤¤à¤¨<br>(Basic)</th>
        <th class="num-col">à¤®à¤¹à¤à¤à¤¾à¤ à¤­à¤¤à¥à¤¤à¤¾<br>(DA)</th>
        <th class="num-col">à¤®à¤à¤¾à¤¨ à¤à¤¿à¤°à¤¾à¤¯à¤¾<br>(HRA)</th>
        <th class="num-col">à¤à¤¿à¤à¤¿à¤¤à¥à¤¸à¤¾<br>(Med)</th>
        <th class="num-col">à¤à¥à¤² à¤¯à¥à¤<br>(Gross)</th>
        <th class="num-col">GPF</th>
        <th class="num-col">P.Tax</th>
        <th class="num-col">TDS</th>
        <th class="num-col">à¤¶à¥à¤¦à¥à¤§ à¤µà¥à¤¤à¤¨<br>(Net)</th>
    </tr>
    </thead>

    <tbody>
    {% for entry in monthly_entries %}
    <tr>
        <td>
            <b>{{ loop.index }}. {{ entry.month_name }}</b>
            {% if entry.is_arrear %}<br><span class="small">(Arrear)</span>{% endif %}
        </td>
        <td class="right">{{ money(entry.basic) }}</td>
        <td class="right">{{ money(entry.da) }}</td>
        <td class="right">{{ money(entry.hra) }}</td>
        <td class="right">{{ money(entry.medical) }}</td>
        <td class="right bold">{{ money(entry.gross) }}</td>
        <td class="right">{{ money(entry.gpf) }}</td>
        <td class="right">{{ money(entry.ptax) }}</td>
        <td class="right">{{ money(entry.tds) }}</td>
        <td class="right bold">{{ money(entry.net) }}</td>
    </tr>
    {% endfor %}

    {% if not monthly_entries %}
    <tr><td colspan="10" class="center">No monthly ledger entries supplied.</td></tr>
    {% endif %}

    <tr class="total">
        <td>à¤à¥à¤² à¤¯à¥à¤ (GRAND TOTAL)</td>
        <td class="right">{{ money(totals.basic) }}</td>
        <td class="right">{{ money(totals.da) }}</td>
        <td class="right">{{ money(totals.hra) }}</td>
        <td class="right">{{ money(totals.medical) }}</td>
        <td class="right">{{ money(totals.gross) }}</td>
        <td class="right">{{ money(totals.gpf) }}</td>
        <td class="right">{{ money(totals.ptax) }}</td>
        <td class="right">{{ money(totals.tds) }}</td>
        <td class="right">{{ money(totals.net) }}</td>
    </tr>
    </tbody>
</table>

{% if totals.arrear_gross > 0 %}
<table class="ledger">
    <tbody>
    <tr class="total">
        <td style="width:50%">Arrear Gross Total</td>
        <td style="width:50%" class="right">Rs. {{ money(totals.arrear_gross) }}</td>
    </tr>
    <tr>
        <td>Arrear TDS</td>
        <td class="right">Rs. {{ money(totals.arrear_tds) }}</td>
    </tr>
    </tbody>
</table>
{% endif %}

</div>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_form16_pdf(data: Dict[str, Any], is_trial: bool = False) -> bytes:
    """
    Generate an in-memory PDF.

    Important:
    - No database/file persistence happens here.
    - `data` is read-only from the generator's point of view.
    - Returns PDF bytes, so the caller can save/download/send them as required.
    """
    if not isinstance(data, dict):
        raise TypeError("data must be a dictionary")

    config = _merge_config(data)
    config = _resolve_year_config(data, config)

    if not config.get("financial_year"):
        raise ValueError(
            "Financial year could not be determined. Supply data['year_info'] "
            "or data['salary_pdf_path'], or manually set pdf_config['financial_year']."
        )

    raw_entries = data.get("monthly_entries") or []

    if raw_entries:
        monthly_entries, totals = _normalise_entries(raw_entries)
    else:
        # Backward compatibility with the old single-summary input.
        basic = _money(data.get("basic", 0))
        da = _money(data.get("da", 0))
        hra = _money(data.get("hra", 0))
        medical = _money(data.get("medical", 0))
        gross = _money(data["gross"]) if data.get("gross") not in (None, "") else _money(
            basic + da + hra + medical
        )
        gpf = _money(data.get("gpf", 0))
        ptax = _money(data.get("ptax", 200))
        tds = _money(data.get("tds", 0))
        net = _money(data["net_income"]) if data.get("net_income") not in (None, "") else _money(
            gross - gpf - ptax - tds
        )

        monthly_entries = [{
            "month_name": "March to February",
            "is_arrear": False,
            "basic": basic,
            "da": da,
            "hra": hra,
            "medical": medical,
            "gross": gross,
            "gpf": gpf,
            "ptax": ptax,
            "tds": tds,
            "net": net,
            "extra": {},
        }]
        totals = {
            "basic": basic, "da": da, "hra": hra, "medical": medical,
            "gross": gross, "gpf": gpf, "ptax": ptax, "tds": tds,
            "net": net, "arrear_gross": 0.0, "arrear_tds": 0.0,
        }

    quarters = _build_quarters(monthly_entries)

    standard_deduction = _money(config.get("standard_deduction", 75000))
    other_income = _money(data.get("other_income", 0))

    # Keep tax computation input-driven. If your application already calculates
    # TDS/tax, that amount remains available as the ledger's TDS figure.
    salary_income = max(0.0, totals["gross"] - standard_deduction - totals["ptax"])
    gross_total_income = _money(salary_income + other_income)

    # Chapter VI-A input is intentionally configurable. GPF is retained as the
    # backward-compatible default for the old application.
    deduction_source = data.get("chapter_via_deductions")
    if not deduction_source:
        deduction_source = [
            {
                "section": "Section 80C (GPF / LIC / PLI / PPF)",
                "gross": totals["gpf"],
                "qualifying": totals["gpf"],
                "deductible": totals["gpf"],
            }
        ]

    deductions = []
    for row in deduction_source:
        if not isinstance(row, dict):
            raise ValueError("chapter_via_deductions entries must be dictionaries")
        deductions.append({
            "section": _clean(row.get("section"), "Other deduction"),
            "gross": _money(row.get("gross", 0)),
            "qualifying": _money(row.get("qualifying", row.get("gross", 0))),
            "deductible": _money(row.get("deductible", row.get("qualifying", 0))),
        })

    chapter_via_total = _money(sum(r["deductible"] for r in deductions))
    total_income = max(0.0, gross_total_income - chapter_via_total)

    # Values used by Page 1. These must always be passed to Jinja; otherwise
    # Jinja creates an Undefined object and the money() formatter attempts
    # float(Undefined), causing the production UndefinedError seen in Streamlit.
    taxable_before_chapter = max(0.0, gross_total_income - chapter_via_total)
    taxable_income = total_income

    # If the calling application supplies a computed tax, use it.
    # Otherwise use the supplied tds as a conservative compatibility value.
    tax_on_total_income = _money(
        data.get("tax_on_total_income", totals["tds"])
    )

    rebate = _money(data.get("rebate_87a", 0))
    cess_rate = _num(data.get("cess_rate", 0))
    cess = _money(data.get("cess", max(0.0, tax_on_total_income - rebate) * cess_rate))
    tax_after_rebate = max(0.0, tax_on_total_income - rebate)
    tax_after_cess = _money(tax_after_rebate + cess)
    relief_89 = _money(data.get("relief_89", 0))
    net_tax_payable = max(0.0, tax_after_cess - relief_89)

    # The actual monthly TDS total remains visible and auditable.
    # It is NOT overwritten by the derived tax value.
    tax_rules = []
    for key, value in (config.get("tax_rules") or {}).items():
        tax_rules.append({"label": str(key), "value": str(value)})

    quarter_receipts = data.get("quarter_receipts") or {}
    book_adjustment_rows = data.get("book_adjustment_rows") or []
    challan_rows = data.get("challan_rows") or []

    template = Template(HTML_TEMPLATE)

    html_content = template.render(
        data=data,
        config=config,
        year_info=config.get("year_info") or {},
        year_warnings=(config.get("year_info") or {}).get("warnings", []),
        monthly_entries=monthly_entries,
        totals=totals,
        quarters=quarters,

        basic=totals["basic"],
        da=totals["da"],
        hra=totals["hra"],
        medical=totals["medical"],
        gross=totals["gross"],
        gpf=totals["gpf"],
        ptax=totals["ptax"],
        tds=totals["tds"],
        net_income=totals["net"],

        arrear_gross=totals["arrear_gross"],
        standard_deduction=standard_deduction,
        salary_income=salary_income,
        other_income=other_income,
        gross_total_income=gross_total_income,
        taxable_before_chapter=taxable_before_chapter,
        taxable_income=taxable_income,
        chapter_via_total=chapter_via_total,
        total_income=total_income,

        tax_on_total_income=tax_on_total_income,
        rebate=rebate,
        cess=cess,
        tax_after_rebate=tax_after_rebate,
        tax_after_cess=tax_after_cess,
        relief_89=relief_89,
        net_tax_payable=net_tax_payable,

        deductions=deductions,
        tax_rules=tax_rules,
        quarter_receipts=quarter_receipts,
        book_adjustment_rows=book_adjustment_rows,
        challan_rows=challan_rows,

        today=date.today().strftime("%d.%m.%Y"),
        is_trial=is_trial,
        footer_text="DEVELOPED & DESIGNED BY @ NITIN MALLICK" if is_trial else "",
        money=_fmt,
    )

    # WeasyPrint performs the actual pagination. The CSS above deliberately
    # uses A4 portrait + named A4 landscape pages, repeated table headers,
    # fixed table layout and wrapping to prevent overflow.
    try:
        return weasyprint.HTML(string=html_content).write_pdf()
    except Exception as first_error:
        try:
            return weasyprint.HTML(string=html_content).render().write_pdf()
        except Exception as second_error:
            raise RuntimeError(
                "PDF generation failed. "
                f"write_pdf error: {first_error}; render/write_pdf error: {second_error}"
            ) from second_error

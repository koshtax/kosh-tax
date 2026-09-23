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
from calendar import monthrange
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Template
import weasyprint


MODULE_DIR = Path(__file__).resolve().parent
BUNDLED_FONT_DIR = MODULE_DIR / "fonts"
DEVANAGARI_FONT = BUNDLED_FONT_DIR / "NotoSansDevanagari-Regular.ttf"
DEVANAGARI_BOLD_FONT = BUNDLED_FONT_DIR / "NotoSansDevanagari-Bold.ttf"


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

    # Never infer arrears merely from row position. A user can upload slips in
    # any order, and an out-of-order list must not change the tax treatment.
    return False


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


def _infer_year_info_from_ledger(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Best-effort backward-compatible FY inference from legacy ledger rows.

    Older app.py versions did not pass ``year_info`` or ``salary_pdf_path`` to
    the generator.  In that case we can still recover the FY from the dated
    salary rows.  Explicit/non-arrear rows are preferred; arrear rows are
    treated as historical evidence only.  The result is marked as inferred so
    the UI/application can warn the user rather than treating it as authoritative.
    """
    if not entries:
        return {}

    counts: Dict[str, int] = {}
    examples: Dict[str, List[str]] = {}
    for row in entries:
        if bool(row.get("is_arrear")):
            continue
        parsed = _parse_month_year_label(str(row.get("month_name", "")))
        if not parsed:
            continue
        month, year = parsed
        fy = _fy_from_month_year(month, year)
        counts[fy] = counts.get(fy, 0) + 1
        examples.setdefault(fy, []).append(str(row.get("month_name", "")))

    # If every dated normal row is historical/arrear, fall back to all rows.
    if not counts:
        for row in entries:
            parsed = _parse_month_year_label(str(row.get("month_name", "")))
            if not parsed:
                continue
            month, year = parsed
            fy = _fy_from_month_year(month, year)
            counts[fy] = counts.get(fy, 0) + 1
            examples.setdefault(fy, []).append(str(row.get("month_name", "")))

    if not counts:
        return {}

    # Most represented FY wins; latest FY breaks ties.
    resolved_fy = sorted(counts, key=lambda fy: (counts[fy], int(fy[:4])))[-1]
    start = int(resolved_fy[:4])
    end = start + 1
    if start < 2026:
        ay = f"{end}-{str(end + 1)[-2:]}"
        tax_year = None
        label = f"FY {resolved_fy} / AY {ay}"
    else:
        ay = None
        tax_year = resolved_fy
        label = f"FY {resolved_fy} / Tax Year {tax_year}"

    warnings = []
    if len(counts) > 1:
        warnings.append(
            "Ledger rows span multiple financial years: " + ", ".join(
                f"{fy} ({counts[fy]} row(s))" for fy in sorted(counts)
            )
        )
    warnings.append(
        f"Financial year {resolved_fy} was inferred from legacy salary-ledger rows because app data did not supply year_info."
    )
    return {
        "financial_year": resolved_fy,
        "assessment_year": ay,
        "tax_year": tax_year,
        "period_start": f"{start}-04-01",
        "period_end": f"{end}-03-31",
        "confidence": "medium" if len(counts) == 1 else "low",
        "source": "monthly_entries",
        "legal_year_label": label,
        "warnings": warnings,
        "requires_manual_confirmation": True,
    }


def _resolve_year_config(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve year information before rendering, including legacy app inputs."""
    supplied = data.get("year_info")
    detected: Dict[str, Any] = {}

    if isinstance(supplied, dict) and supplied.get("financial_year"):
        detected = dict(supplied)
    elif data.get("salary_pdf_path"):
        detected = detect_year_info_from_salary_pdf(data["salary_pdf_path"])
    else:
        # Backward compatibility: older app.py may pass year fields directly.
        direct_fy = data.get("financial_year") or data.get("fy")
        direct_ay = data.get("assessment_year") or data.get("ay")
        direct_ty = data.get("tax_year")
        if direct_fy:
            detected = {"financial_year": str(direct_fy)}
            if direct_ay:
                detected["assessment_year"] = str(direct_ay)
            if direct_ty:
                detected["tax_year"] = str(direct_ty)
            detected["source"] = "data_field"
        elif direct_ty:
            detected = {
                "financial_year": str(direct_ty),
                "tax_year": str(direct_ty),
                "assessment_year": None,
                "source": "data_field",
            }

    # Last-resort compatibility path: infer from the ledger itself.
    if not detected.get("financial_year") and data.get("monthly_entries"):
        detected = _infer_year_info_from_ledger(data.get("monthly_entries") or [])

    if detected.get("financial_year"):
        config["financial_year"] = detected["financial_year"]
        config["assessment_year"] = detected.get("assessment_year")
        config["tax_year"] = detected.get("tax_year")
        config["year_info"] = detected
    elif config.get("financial_year"):
        # Manual FY is allowed; derive the legal label fields if the caller
        # did not supply them. FY 2025-26 is still AY 2026-27.
        start = int(str(config["financial_year"])[:4])
        if start < 2026:
            config["assessment_year"] = config.get("assessment_year") or f"{start + 1}-{str(start + 2)[-2:]}"
            config["tax_year"] = None
        else:
            config["tax_year"] = config.get("tax_year") or config["financial_year"]
            config["assessment_year"] = None

    return config


def _default_config() -> Dict[str, Any]:
    # No silent FY fallback. A tax document must never inherit a stale year.
    return {
        "financial_year": None,
        "assessment_year": None,
        "tax_year": None,
        "standard_deduction": 75000.0,
        "tan": "",
        "employer_address": "",
        "place": "",
        "employer_designation": "",
        "tax_regime": "new",
        "tax_rules": {},
        "strict_period_validation": True,
    }


def _parse_month_year_label(label: str) -> Optional[Tuple[int, int]]:
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*[-/,]?\s*(20\d{2})\b",
        _clean(label), re.I,
    )
    if not m:
        return None
    return _MONTHS[m.group(1).lower()], int(m.group(2))


def _infer_arrear_flags(entries: List[Dict[str, Any]], financial_year: Optional[str]) -> None:
    """Infer arrears only from strong evidence, never from arbitrary row position."""
    # Explicit flags / text markers already win.
    for row in entries:
        if row.get("is_arrear"):
            continue
        label = _clean(row.get("month_name"), "").lower()
        if any(word in label for word in ("arrear", "bakaya", "baki", "à¤¬à¤à¤¾à¤¯à¤¾")):
            row["is_arrear"] = True
        elif re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s*20\d{2}\s*[-/]\s*", label):
            row["is_arrear"] = True

    if not financial_year:
        return

    # If a complete Apr-Mar set exists for the selected FY, any remaining
    # non-explicit rows are treated as arrears. This preserves the useful old
    # behaviour without depending on list position.
    start = int(financial_year[:4])
    expected = {(m, start if m >= 4 else start + 1) for m in range(1, 13)}
    seen_normal = set()
    for row in entries:
        if row.get("is_arrear"):
            continue
        parsed = _parse_month_year_label(row.get("month_name", ""))
        if parsed and parsed in expected:
            seen_normal.add(parsed)
    if len(seen_normal) >= 12:
        for row in entries:
            if row.get("is_arrear"):
                continue
            parsed = _parse_month_year_label(row.get("month_name", ""))
            if not parsed or parsed not in expected or parsed in seen_normal:
                if parsed not in seen_normal or not parsed:
                    row["is_arrear"] = True


def _ledger_sort_key(entry: Dict[str, Any], target_fy: Optional[str] = None) -> Tuple[int, int, int, str]:
    """Sort normal salary months Apr-Mar; arrears after normal months."""
    parsed = _parse_month_year_label(entry.get("month_name", ""))
    arrear = bool(entry.get("is_arrear"))
    if not parsed:
        return (1 if arrear else 0, 9999, 99, _clean(entry.get("month_name")))
    month, year = parsed
    if target_fy:
        start = int(target_fy[:4])
        # Fiscal sequence: Apr-Dec of start year, Jan-Mar of next year.
        fy_month = month - 3 if month >= 4 else month + 9
        expected_year = start if month >= 4 else start + 1
        year_penalty = 0 if year == expected_year else 1
        return (1 if arrear else 0, year_penalty, fy_month, _clean(entry.get("month_name")))
    return (1 if arrear else 0, year, month, _clean(entry.get("month_name")))


def _validate_ledger_period(entries: List[Dict[str, Any]], financial_year: Optional[str]) -> List[str]:
    if not financial_year:
        return []
    start = int(financial_year[:4])
    end = start + 1
    warnings = []
    for row in entries:
        if row.get("is_arrear"):
            continue
        parsed = _parse_month_year_label(row.get("month_name", ""))
        if not parsed:
            continue
        month, year = parsed
        expected_year = start if month >= 4 else end
        if year != expected_year:
            warnings.append(
                f"Normal salary row '{row.get('month_name')}' falls outside FY {financial_year}. "
                f"Expected year {expected_year} for that month."
            )
    return warnings


DEFAULT_NEW_REGIME_SLABS_AY_2026_27 = [
    (400000, 0.00),
    (800000, 0.05),
    (1200000, 0.10),
    (1600000, 0.15),
    (2000000, 0.20),
    (2400000, 0.25),
    (float("inf"), 0.30),
]


def _slab_tax(income: float, slabs: List[Tuple[float, float]]) -> float:
    tax = 0.0
    previous = 0.0
    for upper, rate in slabs:
        if income <= previous:
            break
        taxable = min(income, upper) - previous
        if taxable > 0:
            tax += taxable * rate
        previous = upper
        if upper == float("inf"):
            break
    return _money(tax)


def _calculate_tax_from_rules(total_income: float, config: Dict[str, Any], data: Dict[str, Any]) -> Tuple[float, float, float]:
    """Return income-tax, rebate, cess before relief. Explicit app values win."""
    if "tax_on_total_income" in data and data.get("tax_on_total_income") not in (None, ""):
        tax = _money(data.get("tax_on_total_income"))
    else:
        regime = _clean(config.get("tax_regime"), "new").lower()
        rules = config.get("tax_rules") or {}
        slabs = rules.get("slabs") if isinstance(rules, dict) else None
        if slabs:
            parsed_slabs = []
            for item in slabs:
                if isinstance(item, dict):
                    upper = item.get("upper")
                    rate = item.get("rate")
                else:
                    upper, rate = item
                upper = float("inf") if str(upper).lower() in {"inf", "infinity", "none"} else _num(upper)
                parsed_slabs.append((upper, _num(rate)))
            tax = _slab_tax(total_income, parsed_slabs)
        elif regime == "new" and config.get("financial_year") == "2025-26":
            # Official AY 2026-27 new-regime slabs. Kept here as a fallback only;
            # future years should provide their own configurable tax_rules.
            tax = _slab_tax(total_income, DEFAULT_NEW_REGIME_SLABS_AY_2026_27)
        else:
            tax = _money(data.get("tds", 0.0))

    if "rebate_87a" in data and data.get("rebate_87a") not in (None, ""):
        rebate = _money(data.get("rebate_87a"))
    else:
        rules = config.get("tax_rules") or {}
        rebate_limit = _num(rules.get("rebate_income_limit", 1200000)) if isinstance(rules, dict) else 1200000
        rebate_max = _num(rules.get("rebate_max", 60000)) if isinstance(rules, dict) else 60000
        rebate = _money(min(tax, rebate_max) if total_income <= rebate_limit else 0.0)

    if "cess" in data and data.get("cess") not in (None, ""):
        cess = _money(data.get("cess"))
    else:
        rules = config.get("tax_rules") or {}
        cess_rate = _num(data.get("cess_rate", rules.get("cess_rate", 0.04) if isinstance(rules, dict) else 0.04))
        cess = _money(max(0.0, tax - rebate) * cess_rate)

    return tax, rebate, cess


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

@font-face {
    font-family: "NotoSansDevanagariLocal";
    src: url("{{ regular_font_url }}") format("truetype");
    font-weight: 400;
}

@font-face {
    font-family: "NotoSansDevanagariLocal";
    src: url("{{ bold_font_url }}") format("truetype");
    font-weight: 700;
}

* { box-sizing: border-box; }

html, body {
    margin: 0;
    padding: 0;
}

body {
    font-family: "NotoSansDevanagariLocal", "Noto Sans Devanagari", "Noto Sans", "DejaVu Sans",
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

.auto-fit {
    max-width: 100%;
}

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
    <div class="title">{{ "नई कर व्यवस्था" if tax_regime == "new" else "पुरानी कर व्यवस्था" }} - SCHEDULE OF INCOME - TAX (आयकर की अनुसूची)</div>
    <div class="subtitle">
        (चार प्रतियों में भर कर दें) |
        वित्तीय वर्ष {{ config.financial_year }}
        {% if config.tax_year %}
            (कर वर्ष {{ config.tax_year }})
        {% elif config.assessment_year %}
            (कर निर्धारण वर्ष {{ config.assessment_year }})
        {% endif %}
    </div>
</div>

<table class="auto-fit">
    <tbody>
    <tr>
        <td colspan="2">
            <b>करदाता का नाम / Name:</b> {{ data.name }}<br>
            <b>पदनाम / Designation:</b> {{ data.designation }}<br>
            <b>कार्यालय/विद्यालय का नाम / Office:</b> {{ data.office_name }}<br>
            <b>स्थायी लेखा संख्या (PAN):</b> {{ data.pan }}
        </td>
    </tr>
    <tr>
        <td style="width:75%">
            <b>क. वेतन स्रोत से प्राप्त आय का विवरण :-</b><br>
            01. वेतन<br>
            02. महँगाई भत्ता (DA)<br>
            03. मकान किराया भत्ता (HRA)<br>
            04. चिकित्सा भत्ता (Medical Allowance)<br>
            05. परिवहन भत्ता / अन्य भत्ते<br>
            06. बकाया वेतन एवं भत्ते की राशि (Arrears / Bakaya Vetan)<br>
            <b>07. वेतन स्रोत से प्राप्त कुल आय (Gross Total Income)</b>
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
            <b>ख. आयकर की संगणना (Tax Computation):-</b><br>
            01. वेतन स्रोत से प्राप्त कुल आय<br>
            02. घटायें - धारा 16(ia) के अन्तर्गत मानक कटौती (Standard Deduction)<br>
            03. सकल कुल आय (Gross Total Income)<br>
            04. कर योग्य आय (Taxable Income)<br>
            05. देय आयकर (Tax on Total Income)<br>
            06. घटायें - धारा 87A के तहत कर में राहत (Rebate)<br>
            07. शिक्षा उपकर / Cess<br>
            <b>08. शुद्ध देय आयकर (Net Tax Payable)</b>
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
<div class="section-title">Configured Tax Rules / कर नियम</div>
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
    <div class="subtitle">Certificate under Section 203 — Summary of amount paid/credited and tax deducted at source</div>
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
        वित्तीय वर्ष {{ config.financial_year }} में वेतन स्रोत से आय और कटौतियों की विवरणी
    </div>
    <div class="subtitle">
        नाम: {{ data.name }} |
        पदनाम: {{ data.designation }} |
        कार्यालय: {{ data.office_name }}
    </div>
</div>

<table class="ledger">
    <thead>
    <tr class="shade">
        <th class="month-col">क्र.सं. / माह विवरण</th>
        <th class="num-col">मूल वेतन<br>(Basic)</th>
        <th class="num-col">महंगाई भत्ता<br>(DA)</th>
        <th class="num-col">मकान किराया<br>(HRA)</th>
        <th class="num-col">चिकित्सा<br>(Med)</th>
        <th class="num-col">कुल योग<br>(Gross)</th>
        <th class="num-col">GPF</th>
        <th class="num-col">P.Tax</th>
        <th class="num-col">TDS</th>
        <th class="num-col">शुद्ध वेतन<br>(Net)</th>
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
        <td>कुल योग (GRAND TOTAL)</td>
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
        _infer_arrear_flags(monthly_entries, config.get("financial_year"))
        # Sort by fiscal chronology without changing any numeric values.
        monthly_entries.sort(key=lambda row: _ledger_sort_key(row, config.get("financial_year")))
        period_warnings = _validate_ledger_period(monthly_entries, config.get("financial_year"))
        year_info = config.setdefault("year_info", {})
        year_info.setdefault("warnings", [])
        year_info["warnings"] = list(dict.fromkeys(year_info.get("warnings", []) + period_warnings))
        year_info["requires_manual_confirmation"] = bool(year_info.get("warnings"))
        year_info = config.get("year_info") or {}
        inferred_from_ledger = year_info.get("source") == "monthly_entries"
        if period_warnings and config.get("strict_period_validation", True) and not inferred_from_ledger:
            raise ValueError(
                "Salary ledger period does not match the selected financial year. "
                + " | ".join(period_warnings[:5])
                + (" | More period mismatches exist." if len(period_warnings) > 5 else "")
            )
        # Recompute arrear totals after sorting/validation; values themselves are unchanged.
        totals = {
            **totals,
            "arrear_gross": _money(sum(r["gross"] for r in monthly_entries if r.get("is_arrear"))),
            "arrear_tds": _money(sum(r["tds"] for r in monthly_entries if r.get("is_arrear"))),
        }
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
    regime = _clean(config.get("tax_regime"), "new").lower()
    for row in deduction_source:
        if not isinstance(row, dict):
            raise ValueError("chapter_via_deductions entries must be dictionaries")
        section = _clean(row.get("section"), "Other deduction")
        gross_amount = _money(row.get("gross", 0))
        qualifying_amount = _money(row.get("qualifying", row.get("gross", 0)))
        deductible_amount = _money(row.get("deductible", row.get("qualifying", 0)))
        # Section 80C is not available under the new regime. Do not silently
        # claim GPF/LIC/PLI/PPF as a Chapter VI-A deduction there.
        is_80c = bool(re.search(r"\b80C\b", section, re.I))
        allowed_new = bool(row.get("allowed_in_new_regime", False))
        if regime == "new" and is_80c and not allowed_new:
            deductible_amount = 0.0
        deductions.append({
            "section": section,
            "gross": gross_amount,
            "qualifying": qualifying_amount,
            "deductible": deductible_amount,
        })

    chapter_via_total = _money(sum(r["deductible"] for r in deductions))
    total_income = max(0.0, gross_total_income - chapter_via_total)

    # Values used by Page 1. These must always be passed to Jinja; otherwise
    # Jinja creates an Undefined object and the money() formatter attempts
    # float(Undefined), causing the production UndefinedError seen in Streamlit.
    taxable_before_chapter = max(0.0, gross_total_income - chapter_via_total)
    taxable_income = total_income

    # Tax liability must never silently fall back to TDS. TDS is a deduction
    # already made; it is not the tax computation. Use an explicitly supplied
    # tax amount, otherwise calculate from configured/default slabs.
    tax_on_total_income, rebate, cess = _calculate_tax_from_rules(
        total_income, config, data
    )
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
        tax_regime=_clean(config.get("tax_regime"), "new").lower(),
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
        return weasyprint.HTML(string=html_content, base_url=str(MODULE_DIR)).write_pdf()
    except Exception as first_error:
        try:
            return weasyprint.HTML(string=html_content, base_url=str(MODULE_DIR)).render().write_pdf()
        except Exception as second_error:
            raise RuntimeError(
                "PDF generation failed. "
                f"write_pdf error: {first_error}; render/write_pdf error: {second_error}"
            ) from second_error

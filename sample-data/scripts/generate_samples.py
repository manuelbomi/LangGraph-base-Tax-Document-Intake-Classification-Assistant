"""Generates the synthetic demo tax documents used throughout this repo.

These are **synthetic recreations** of real IRS forms (W-2, 1099-NEC,
1099-INT, 1099-DIV, Schedule K-1), built with reportlab -- NOT copies of the
actual IRS PDFs. Box numbers and labels match the real forms exactly (all
public, government-published numbering -- e.g. W-2 box 1 is "Wages, tips,
other compensation" on every real W-2 ever issued), but the visual layout
(fonts, borders, spacing) is our own simplified recreation rather than a
pixel-for-pixel reproduction of the official form. See
`sample-data/README.md` for the full rationale.

Produces:
  sample-data/w2/*.pdf              -- 2 W-2s, different fictitious employers
  sample-data/1099/*.pdf            -- 1099-NEC, 1099-INT, 1099-DIV
  sample-data/k1/*.pdf              -- 1 Schedule K-1 (Form 1065)
  sample-data/bank-statements/*.pdf -- 1 plain bank interest statement
                                        (NOT an official tax form)

Everything here is entirely fictitious (employers, banks, people, SSNs,
EINs, amounts) -- see sample-data/README.md for why these are synthesized
rather than sourced from any real filing.

Run with (from repo root):
    python sample-data/scripts/generate_samples.py

Requires: reportlab (already in backend/requirements.txt via
sample-data-scripts extra; for regenerating outside the backend venv,
`pip install reportlab`).
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DATA_DIR = os.path.dirname(HERE)
W2_DIR = os.path.join(SAMPLE_DATA_DIR, "w2")
NEC_1099_DIR = os.path.join(SAMPLE_DATA_DIR, "1099")
K1_DIR = os.path.join(SAMPLE_DATA_DIR, "k1")
BANK_DIR = os.path.join(SAMPLE_DATA_DIR, "bank-statements")

styles = getSampleStyleSheet()
NAVY = colors.HexColor("#1a3c6e")
GRAY = colors.HexColor("#555555")

_title_style = ParagraphStyle("FormTitle", parent=styles["Heading1"], fontSize=15, textColor=NAVY)
_note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=8, textColor=GRAY, alignment=TA_LEFT)
_center_style = ParagraphStyle("Center", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER)


def _party_block(lines: list[str]) -> Table:
    text = "<br/>".join(lines)
    t = Table([[Paragraph(text, ParagraphStyle("Party", parent=styles["Normal"], fontSize=9.5))]], colWidths=[3.4 * inch])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _box_table(rows: list[tuple[str, str]], *, col_widths=(0.55 * inch, 3.7 * inch, 2.15 * inch)) -> Table:
    """A form-style box grid: (box number, label, value)."""
    data = [[num, Paragraph(f"<font size=8>{label}</font>", styles["Normal"]), Paragraph(f"<b>{value}</b>", styles["Normal"])] for num, label, value in rows]
    t = Table(data, colWidths=list(col_widths))
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ]
        )
    )
    return t


def _footer_note(text: str) -> Paragraph:
    return Paragraph(f"<i>{text}</i>", _note_style)


def _base_doc(path: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.7 * inch, rightMargin=0.7 * inch)


# ---------------------------------------------------------------------------
# Form W-2, Wage and Tax Statement
# ---------------------------------------------------------------------------
def build_w2(path: str, *, employer_name, employer_ein, employer_address, employee_name, employee_ssn, employee_address, tax_year, wages, fed_wh, ss_wages, ss_wh, medicare_wages, medicare_wh, state, state_wages, state_tax) -> None:
    doc = _base_doc(path)
    story = [
        Paragraph(f"Form W-2 (Recreation) &mdash; Wage and Tax Statement &mdash; Tax Year {tax_year}", _title_style),
        _footer_note("This is a synthetic recreation for demo purposes, not an IRS-issued document. See sample-data/README.md."),
        Spacer(1, 10),
        HRFlowable(width="100%", color=NAVY, thickness=1.2),
        Spacer(1, 10),
    ]
    header = Table(
        [[_party_block([f"<b>b Employer EIN:</b> {employer_ein}", f"<b>c Employer name, address:</b>", employer_name, employer_address]),
          _party_block([f"<b>a Employee SSN:</b> {employee_ssn}", f"<b>e Employee name, address:</b>", employee_name, employee_address])]],
        colWidths=[3.4 * inch, 3.4 * inch],
    )
    story.append(header)
    story.append(Spacer(1, 12))
    story.append(
        _box_table(
            [
                ("1", "Wages, tips, other compensation", f"${wages:,.2f}"),
                ("2", "Federal income tax withheld", f"${fed_wh:,.2f}"),
                ("3", "Social security wages", f"${ss_wages:,.2f}"),
                ("4", "Social security tax withheld", f"${ss_wh:,.2f}"),
                ("5", "Medicare wages and tips", f"${medicare_wages:,.2f}"),
                ("6", "Medicare tax withheld", f"${medicare_wh:,.2f}"),
                ("15", "State", state),
                ("16", "State wages, tips, etc.", f"${state_wages:,.2f}"),
                ("17", "State income tax", f"${state_tax:,.2f}"),
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(_footer_note("Copy B - To Be Filed With Employee's FEDERAL Tax Return."))
    doc.build(story)


# ---------------------------------------------------------------------------
# Form 1099-NEC, Nonemployee Compensation
# ---------------------------------------------------------------------------
def build_1099nec(path: str, *, payer_name, payer_tin, payer_address, recipient_name, recipient_tin, recipient_address, tax_year, nonemployee_comp, fed_wh) -> None:
    doc = _base_doc(path)
    story = [
        Paragraph(f"Form 1099-NEC (Recreation) &mdash; Nonemployee Compensation &mdash; Tax Year {tax_year}", _title_style),
        _footer_note("This is a synthetic recreation for demo purposes, not an IRS-issued document. See sample-data/README.md."),
        Spacer(1, 10),
        HRFlowable(width="100%", color=NAVY, thickness=1.2),
        Spacer(1, 10),
    ]
    header = Table(
        [[_party_block([f"<b>PAYER'S TIN:</b> {payer_tin}", "<b>PAYER'S name, address:</b>", payer_name, payer_address]),
          _party_block([f"<b>RECIPIENT'S TIN:</b> {recipient_tin}", "<b>RECIPIENT'S name, address:</b>", recipient_name, recipient_address])]],
        colWidths=[3.4 * inch, 3.4 * inch],
    )
    story.append(header)
    story.append(Spacer(1, 12))
    story.append(
        _box_table(
            [
                ("1", "Nonemployee compensation", f"${nonemployee_comp:,.2f}"),
                ("4", "Federal income tax withheld", f"${fed_wh:,.2f}"),
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(_footer_note("Copy B - For Recipient."))
    doc.build(story)


# ---------------------------------------------------------------------------
# Form 1099-INT, Interest Income
# ---------------------------------------------------------------------------
def build_1099int(path: str, *, payer_name, payer_tin, payer_address, recipient_name, recipient_tin, recipient_address, tax_year, interest_income, fed_wh) -> None:
    doc = _base_doc(path)
    story = [
        Paragraph(f"Form 1099-INT (Recreation) &mdash; Interest Income &mdash; Tax Year {tax_year}", _title_style),
        _footer_note("This is a synthetic recreation for demo purposes, not an IRS-issued document. See sample-data/README.md."),
        Spacer(1, 10),
        HRFlowable(width="100%", color=NAVY, thickness=1.2),
        Spacer(1, 10),
    ]
    header = Table(
        [[_party_block([f"<b>PAYER'S TIN:</b> {payer_tin}", "<b>PAYER'S name, address:</b>", payer_name, payer_address]),
          _party_block([f"<b>RECIPIENT'S TIN:</b> {recipient_tin}", "<b>RECIPIENT'S name, address:</b>", recipient_name, recipient_address])]],
        colWidths=[3.4 * inch, 3.4 * inch],
    )
    story.append(header)
    story.append(Spacer(1, 12))
    story.append(
        _box_table(
            [
                ("1", "Interest income", f"${interest_income:,.2f}"),
                ("4", "Federal income tax withheld", f"${fed_wh:,.2f}"),
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(_footer_note("Copy B - For Recipient."))
    doc.build(story)


# ---------------------------------------------------------------------------
# Form 1099-DIV, Dividends and Distributions
# ---------------------------------------------------------------------------
def build_1099div(path: str, *, payer_name, payer_tin, payer_address, recipient_name, recipient_tin, recipient_address, tax_year, ordinary_div, qualified_div, cap_gain, fed_wh) -> None:
    doc = _base_doc(path)
    story = [
        Paragraph(f"Form 1099-DIV (Recreation) &mdash; Dividends and Distributions &mdash; Tax Year {tax_year}", _title_style),
        _footer_note("This is a synthetic recreation for demo purposes, not an IRS-issued document. See sample-data/README.md."),
        Spacer(1, 10),
        HRFlowable(width="100%", color=NAVY, thickness=1.2),
        Spacer(1, 10),
    ]
    header = Table(
        [[_party_block([f"<b>PAYER'S TIN:</b> {payer_tin}", "<b>PAYER'S name, address:</b>", payer_name, payer_address]),
          _party_block([f"<b>RECIPIENT'S TIN:</b> {recipient_tin}", "<b>RECIPIENT'S name, address:</b>", recipient_name, recipient_address])]],
        colWidths=[3.4 * inch, 3.4 * inch],
    )
    story.append(header)
    story.append(Spacer(1, 12))
    story.append(
        _box_table(
            [
                ("1a", "Total ordinary dividends", f"${ordinary_div:,.2f}"),
                ("1b", "Qualified dividends", f"${qualified_div:,.2f}"),
                ("2a", "Total capital gain distributions", f"${cap_gain:,.2f}"),
                ("4", "Federal income tax withheld", f"${fed_wh:,.2f}"),
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(_footer_note("Copy B - For Recipient."))
    doc.build(story)


# ---------------------------------------------------------------------------
# Schedule K-1 (Form 1065), Partner's Share of Income
# ---------------------------------------------------------------------------
def build_k1(path: str, *, partnership_name, partnership_ein, partnership_address, partner_name, partner_ssn, partner_address, tax_year, ordinary_income, rental_income, se_earnings) -> None:
    doc = _base_doc(path)
    story = [
        Paragraph(f"Schedule K-1 (Form 1065) (Recreation) &mdash; Partner's Share of Income &mdash; Tax Year {tax_year}", _title_style),
        _footer_note("This is a synthetic recreation for demo purposes, not an IRS-issued document. See sample-data/README.md."),
        Spacer(1, 10),
        HRFlowable(width="100%", color=NAVY, thickness=1.2),
        Spacer(1, 10),
    ]
    header = Table(
        [[_party_block(["<b>Part I - Partnership</b>", f"<b>EIN:</b> {partnership_ein}", partnership_name, partnership_address]),
          _party_block(["<b>Part II - Partner</b>", f"<b>SSN/TIN:</b> {partner_ssn}", partner_name, partner_address])]],
        colWidths=[3.4 * inch, 3.4 * inch],
    )
    story.append(header)
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>Part III - Partner's Share of Current Year Income, Deductions, Credits</b>", _note_style))
    story.append(Spacer(1, 4))
    story.append(
        _box_table(
            [
                ("1", "Ordinary business income (loss)", f"${ordinary_income:,.2f}"),
                ("2", "Net rental real estate income (loss)", f"${rental_income:,.2f}"),
                ("14", "Self-employment earnings (loss), code A", f"${se_earnings:,.2f}"),
            ]
        )
    )
    story.append(Spacer(1, 16))
    story.append(_footer_note("Copy B - For Partner's records."))
    doc.build(story)


# ---------------------------------------------------------------------------
# Bank statement (NOT an official tax form -- supplementary document)
# ---------------------------------------------------------------------------
def build_bank_statement(path: str, *, bank_name, bank_address, account_holder, account_last4, period_start, period_end, total_interest) -> None:
    doc = _base_doc(path)
    story = [
        Paragraph(bank_name, ParagraphStyle("BankTitle", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#0f766e"))),
        Paragraph(bank_address, _note_style),
        Spacer(1, 10),
        HRFlowable(width="100%", color=colors.HexColor("#0f766e"), thickness=1.2),
        Spacer(1, 12),
        Paragraph(f"<b>Account Statement</b>", styles["Heading2"]),
        Paragraph(f"Account Holder: {account_holder}", _center_style if False else styles["Normal"]),
        Paragraph(f"Account Number: ****{account_last4}", styles["Normal"]),
        Paragraph(f"Statement Period: {period_start} to {period_end}", styles["Normal"]),
        Spacer(1, 14),
    ]
    story.append(
        _box_table(
            [("--", "Total interest earned this period", f"${total_interest:,.2f}")],
            col_widths=(0.4 * inch, 4.1 * inch, 1.9 * inch),
        )
    )
    story.append(Spacer(1, 18))
    story.append(_footer_note("This is a synthetic account statement for demo purposes only -- not a real bank record."))
    doc.build(story)


def main() -> None:
    os.makedirs(W2_DIR, exist_ok=True)
    os.makedirs(NEC_1099_DIR, exist_ok=True)
    os.makedirs(K1_DIR, exist_ok=True)
    os.makedirs(BANK_DIR, exist_ok=True)

    build_w2(
        os.path.join(W2_DIR, "W2_Cascade_Retail_Group_Jordan_Ellis.pdf"),
        employer_name="Cascade Retail Group",
        employer_ein="84-1234567",
        employer_address="2200 Harbor Blvd, Columbus, OH 43215",
        employee_name="Jordan Ellis",
        employee_ssn="412-34-5678",
        employee_address="14 Maple Court, Columbus, OH 43201",
        tax_year=2025,
        wages=28450.00,
        fed_wh=2100.00,
        ss_wages=28450.00,
        ss_wh=1763.90,
        medicare_wages=28450.00,
        medicare_wh=412.53,
        state="OH",
        state_wages=28450.00,
        state_tax=854.00,
    )
    build_w2(
        os.path.join(W2_DIR, "W2_Fenwick_Logistics_Inc_Morgan_Alvarez.pdf"),
        employer_name="Fenwick Logistics Inc",
        employer_ein="27-9876543",
        employer_address="88 Freightway Ave, Chicago, IL 60607",
        employee_name="Morgan Alvarez",
        employee_ssn="558-12-9034",
        employee_address="510 Lakeshore Dr, Chicago, IL 60611",
        tax_year=2025,
        wages=41200.00,
        fed_wh=3850.00,
        ss_wages=41200.00,
        ss_wh=2554.40,
        medicare_wages=41200.00,
        medicare_wh=597.40,
        state="IL",
        state_wages=41200.00,
        state_tax=1236.00,
    )
    build_1099nec(
        os.path.join(NEC_1099_DIR, "1099NEC_Bluepeak_Design_Studio_Jordan_Ellis.pdf"),
        payer_name="Bluepeak Design Studio",
        payer_tin="91-2345678",
        payer_address="77 Creative Way, Columbus, OH 43206",
        recipient_name="Jordan Ellis",
        recipient_tin="412-34-5678",
        recipient_address="14 Maple Court, Columbus, OH 43201",
        tax_year=2025,
        nonemployee_comp=6200.00,
        fed_wh=0.0,
    )
    build_1099int(
        os.path.join(NEC_1099_DIR, "1099INT_Harborview_Savings_Bank_Jordan_Ellis.pdf"),
        payer_name="Harborview Savings Bank",
        payer_tin="45-6789012",
        payer_address="1 Harborview Plaza, Columbus, OH 43215",
        recipient_name="Jordan Ellis",
        recipient_tin="412-34-5678",
        recipient_address="14 Maple Court, Columbus, OH 43201",
        tax_year=2025,
        interest_income=184.32,
        fed_wh=0.0,
    )
    build_1099div(
        os.path.join(NEC_1099_DIR, "1099DIV_Crestline_Investments_Morgan_Alvarez.pdf"),
        payer_name="Crestline Investments",
        payer_tin="36-1122334",
        payer_address="900 Market St, Suite 500, Chicago, IL 60602",
        recipient_name="Morgan Alvarez",
        recipient_tin="558-12-9034",
        recipient_address="510 Lakeshore Dr, Chicago, IL 60611",
        tax_year=2025,
        ordinary_div=912.44,
        qualified_div=780.00,
        cap_gain=145.10,
        fed_wh=0.0,
    )
    build_k1(
        os.path.join(K1_DIR, "K1_Alvarez_Family_Holdings_LLC_Morgan_Alvarez.pdf"),
        partnership_name="Alvarez Family Holdings LLC",
        partnership_ein="58-4433221",
        partnership_address="42 Investment Way, Chicago, IL 60603",
        partner_name="Morgan Alvarez",
        partner_ssn="558-12-9034",
        partner_address="510 Lakeshore Dr, Chicago, IL 60611",
        tax_year=2025,
        ordinary_income=3200.00,
        rental_income=0.0,
        se_earnings=0.0,
    )
    build_bank_statement(
        os.path.join(BANK_DIR, "Harborview_Savings_Bank_Statement_Jordan_Ellis.pdf"),
        bank_name="Harborview Savings Bank",
        bank_address="1 Harborview Plaza, Columbus, OH 43215",
        account_holder="Jordan Ellis",
        account_last4="7741",
        period_start="2025-01-01",
        period_end="2025-12-31",
        total_interest=184.32,
    )

    print("Sample tax documents generated in:", SAMPLE_DATA_DIR)


if __name__ == "__main__":
    main()

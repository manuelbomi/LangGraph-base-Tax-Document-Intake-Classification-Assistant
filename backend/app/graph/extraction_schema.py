"""Pydantic schemas used for LLM structured-output extraction, one per
supported tax document type. Passed to
`chat_model.with_structured_output(Schema)` in `extract_fields_node`
(`app/graph/nodes.py`), which picks the schema based on the classified
`doc_type` -- this is the "extraction schema/prompt depends on the
classified type" conditional routing this graph demonstrates.

Box numbers and labels mirror the real IRS forms (all publicly documented,
government-published numbering -- see `sample-data/README.md` for the
provenance of the sample documents these schemas are extracting from):
  - Form W-2: box 1 wages/tips/comp, box 2 federal tax withheld, box 3
    social security wages, box 4 social security tax withheld, box 5
    Medicare wages, box 6 Medicare tax withheld, box 16 state wages, box 17
    state income tax.
  - Form 1099-NEC: box 1 nonemployee compensation, box 4 federal tax
    withheld.
  - Form 1099-INT: box 1 interest income, box 4 federal tax withheld.
  - Form 1099-DIV: box 1a total ordinary dividends, box 1b qualified
    dividends, box 2a total capital gain distributions, box 4 federal tax
    withheld.
  - Schedule K-1 (Form 1065): box 1 ordinary business income (loss), box 2
    net rental real estate income (loss), box 14 self-employment earnings.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocClassification(BaseModel):
    doc_type: str = Field(
        description=(
            "One of: 'W-2', '1099-NEC', '1099-INT', '1099-DIV', 'K-1', "
            "'bank-statement', 'other-unknown'."
        )
    )
    confidence: float = Field(description="Confidence in this classification, 0.0-1.0.")
    reasoning: str = Field(description="One short sentence explaining the classification.")


class W2Fields(BaseModel):
    employer_name: str = Field(description="Employer's name (W-2 box c).")
    employer_ein: str = Field(default="", description="Employer Identification Number, box b.")
    employee_name: str = Field(description="Employee's name, box e.")
    employee_ssn: str = Field(default="", description="Employee's SSN, box a.")
    tax_year: int = Field(description="Tax year this W-2 covers.")
    box1_wages: float = Field(description="Box 1: Wages, tips, other compensation.")
    box2_federal_tax_withheld: float = Field(default=0.0, description="Box 2: Federal income tax withheld.")
    box3_social_security_wages: float = Field(default=0.0, description="Box 3: Social security wages.")
    box4_social_security_tax_withheld: float = Field(default=0.0, description="Box 4: Social security tax withheld.")
    box5_medicare_wages: float = Field(default=0.0, description="Box 5: Medicare wages and tips.")
    box6_medicare_tax_withheld: float = Field(default=0.0, description="Box 6: Medicare tax withheld.")
    box16_state_wages: float = Field(default=0.0, description="Box 16: State wages, tips, etc.")
    box17_state_income_tax: float = Field(default=0.0, description="Box 17: State income tax.")
    state: str = Field(default="", description="Box 15: State abbreviation.")


class Form1099NECFields(BaseModel):
    payer_name: str = Field(description="Payer's name.")
    payer_tin: str = Field(default="", description="Payer's TIN.")
    recipient_name: str = Field(description="Recipient's name.")
    recipient_tin: str = Field(default="", description="Recipient's TIN/SSN.")
    tax_year: int = Field(description="Tax year this 1099-NEC covers.")
    box1_nonemployee_compensation: float = Field(description="Box 1: Nonemployee compensation.")
    box4_federal_tax_withheld: float = Field(default=0.0, description="Box 4: Federal income tax withheld.")


class Form1099INTFields(BaseModel):
    payer_name: str = Field(description="Payer's name (bank/financial institution).")
    payer_tin: str = Field(default="", description="Payer's TIN.")
    recipient_name: str = Field(description="Recipient's name.")
    recipient_tin: str = Field(default="", description="Recipient's TIN/SSN.")
    tax_year: int = Field(description="Tax year this 1099-INT covers.")
    box1_interest_income: float = Field(description="Box 1: Interest income.")
    box4_federal_tax_withheld: float = Field(default=0.0, description="Box 4: Federal income tax withheld.")


class Form1099DIVFields(BaseModel):
    payer_name: str = Field(description="Payer's name (brokerage/fund).")
    payer_tin: str = Field(default="", description="Payer's TIN.")
    recipient_name: str = Field(description="Recipient's name.")
    recipient_tin: str = Field(default="", description="Recipient's TIN/SSN.")
    tax_year: int = Field(description="Tax year this 1099-DIV covers.")
    box1a_total_ordinary_dividends: float = Field(default=0.0, description="Box 1a: Total ordinary dividends.")
    box1b_qualified_dividends: float = Field(default=0.0, description="Box 1b: Qualified dividends.")
    box2a_total_capital_gain_distributions: float = Field(
        default=0.0, description="Box 2a: Total capital gain distributions."
    )
    box4_federal_tax_withheld: float = Field(default=0.0, description="Box 4: Federal income tax withheld.")


class K1Fields(BaseModel):
    partnership_name: str = Field(description="Partnership's name (Schedule K-1, Form 1065, Part I).")
    partnership_ein: str = Field(default="", description="Partnership's EIN.")
    partner_name: str = Field(description="Partner's name (Part II).")
    partner_ssn_or_tin: str = Field(default="", description="Partner's SSN or TIN.")
    tax_year: int = Field(description="Tax year this K-1 covers.")
    box1_ordinary_business_income: float = Field(
        default=0.0, description="Box 1: Ordinary business income (loss)."
    )
    box2_net_rental_real_estate_income: float = Field(
        default=0.0, description="Box 2: Net rental real estate income (loss)."
    )
    box14_self_employment_earnings: float = Field(
        default=0.0, description="Box 14: Self-employment earnings (loss), code A."
    )


class BankStatementFields(BaseModel):
    """Not an official IRS form -- a supplementary bank statement showing
    interest earned, useful for cross-checking a 1099-INT but not itself
    part of the expected-documents checklist for most clients."""

    bank_name: str = Field(description="Name of the bank.")
    account_holder_name: str = Field(description="Name on the account.")
    account_number_last4: str = Field(default="", description="Last 4 digits of the account number.")
    statement_period_start: str = Field(description="Statement period start date, ISO 'YYYY-MM-DD'.")
    statement_period_end: str = Field(description="Statement period end date, ISO 'YYYY-MM-DD'.")
    total_interest_earned: float = Field(default=0.0, description="Total interest earned in this period.")


class OtherDocumentFields(BaseModel):
    """Fallback schema for documents that don't match a known tax form."""

    apparent_document_type: str = Field(description="Your best guess at what this document actually is.")
    notes: str = Field(description="A short summary of what's on the document.")


EXTRACTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "W-2": W2Fields,
    "1099-NEC": Form1099NECFields,
    "1099-INT": Form1099INTFields,
    "1099-DIV": Form1099DIVFields,
    "K-1": K1Fields,
    "bank-statement": BankStatementFields,
    "other-unknown": OtherDocumentFields,
}

# Maps a doc_type to the (employer/payer/partnership/bank, tax-id) field
# names used generically by app/tools/organizer.py for checklist/duplicate
# matching, since the field names differ per schema above.
COUNTERPARTY_FIELDS: dict[str, tuple[str, str]] = {
    "W-2": ("employer_name", "employer_ein"),
    "1099-NEC": ("payer_name", "payer_tin"),
    "1099-INT": ("payer_name", "payer_tin"),
    "1099-DIV": ("payer_name", "payer_tin"),
    "K-1": ("partnership_name", "partnership_ein"),
    "bank-statement": ("bank_name", "account_number_last4"),
    "other-unknown": ("apparent_document_type", ""),
}

# Maps a doc_type to the prompt-name suffix used in the prompt registry
# (see app/prompts/seed_prompts.py -- "extract_{suffix}_text" / "_vision").
DOC_TYPE_PROMPT_KEY: dict[str, str] = {
    "W-2": "w2",
    "1099-NEC": "1099nec",
    "1099-INT": "1099int",
    "1099-DIV": "1099div",
    "K-1": "k1",
    "bank-statement": "bank_statement",
    "other-unknown": "other",
}

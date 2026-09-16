"""Seed version-1 prompts for the `classify` node (text + vision variants)
and the `extract_fields` node (one text + one vision variant per supported
document type).

Run with:
    python -m app.prompts.seed_prompts

Safe to re-run: it only inserts a new version if the active template text
for a given name has actually changed.
"""
from __future__ import annotations

from app.prompts.registry import add_prompt_version
from sqlalchemy import select

from app.db.models import Prompt
from app.db.session import SessionLocal

_CLASSIFY_INSTRUCTIONS = (
    "You are a tax document intake specialist at a small tax preparation firm. "
    "Classify the document into exactly one of: 'W-2', '1099-NEC', '1099-INT', "
    "'1099-DIV', 'K-1', 'bank-statement', 'other-unknown'. Base this on the "
    "document's actual content and layout (box numbers, form titles, issuer "
    "language) -- never on a filename. 'bank-statement' means an account "
    "statement from a bank showing transactions/interest, NOT an official "
    "IRS form. Use 'other-unknown' only if it genuinely matches none of the "
    "above. Give a confidence between 0 and 1 and one short sentence of "
    "reasoning."
)

_EXTRACTION_COMMON = (
    "You are a meticulous tax preparer's assistant performing data entry. "
    "Extract structured fields EXACTLY as they appear on the document -- do "
    "not guess, estimate, or invent values that aren't present. If a box is "
    "blank or shows 0.00, use 0. Normalize all dates to ISO 8601 "
    "'YYYY-MM-DD'. Preserve SSN/EIN/TIN formatting exactly as printed "
    "(e.g. 'XXX-XX-XXXX' or 'XX-XXXXXXX')."
)

_EXTRACTION_SPECIFICS: dict[str, str] = {
    "w2": (
        "This is a Form W-2, Wage and Tax Statement. Extract the employer's "
        "name and EIN (box b/c), the employee's name and SSN (box a/e), the "
        "tax year, and boxes 1, 2, 3, 4, 5, 6, 15 (state), 16, and 17."
    ),
    "1099nec": (
        "This is a Form 1099-NEC, Nonemployee Compensation. Extract the "
        "payer's name and TIN, the recipient's name and TIN, the tax year, "
        "box 1 (nonemployee compensation), and box 4 (federal tax withheld)."
    ),
    "1099int": (
        "This is a Form 1099-INT, Interest Income. Extract the payer's name "
        "and TIN, the recipient's name and TIN, the tax year, box 1 "
        "(interest income), and box 4 (federal tax withheld)."
    ),
    "1099div": (
        "This is a Form 1099-DIV, Dividends and Distributions. Extract the "
        "payer's name and TIN, the recipient's name and TIN, the tax year, "
        "box 1a (total ordinary dividends), box 1b (qualified dividends), "
        "box 2a (total capital gain distributions), and box 4 (federal tax "
        "withheld)."
    ),
    "k1": (
        "This is a Schedule K-1 (Form 1065), Partner's Share of Income. "
        "Extract the partnership's name and EIN (Part I), the partner's "
        "name and SSN/TIN (Part II), the tax year, box 1 (ordinary business "
        "income/loss), box 2 (net rental real estate income/loss), and box "
        "14 (self-employment earnings, code A)."
    ),
    "bank_statement": (
        "This is a bank account statement (NOT an official tax form). "
        "Extract the bank's name, the account holder's name, the last 4 "
        "digits of the account number, the statement period start/end "
        "dates, and the total interest earned during the period."
    ),
    "other": (
        "This document did not match a known tax form. Note your best "
        "guess at what it actually is and a short summary of its contents."
    ),
}

PROMPTS_V1: dict[str, str] = {
    "classify_document_text": (
        f"{_CLASSIFY_INSTRUCTIONS}\n\nBelow is text extracted from the document:\n\n"
        "-----\n{raw_text}\n-----"
    ),
    "classify_document_vision": (
        f"{_CLASSIFY_INSTRUCTIONS}\n\nThe attached image is a photo or scan of the document."
    ),
}
for _key, _specific in _EXTRACTION_SPECIFICS.items():
    PROMPTS_V1[f"extract_{_key}_text"] = (
        f"{_EXTRACTION_COMMON}\n\n{_specific}\n\n"
        "Below is text extracted from the document:\n\n-----\n{raw_text}\n-----"
    )
    PROMPTS_V1[f"extract_{_key}_vision"] = (
        f"{_EXTRACTION_COMMON}\n\n{_specific}\n\n"
        "The attached image is a photo or scan of the document -- read the values directly from it."
    )


def seed() -> None:
    with SessionLocal() as db:
        for name, template in PROMPTS_V1.items():
            active = db.execute(
                select(Prompt).where(Prompt.name == name, Prompt.is_active.is_(True))
            ).scalar_one_or_none()
            if active is not None and active.template == template:
                print(f"[skip] '{name}' already has this template active (v{active.version})")
                continue
            version = add_prompt_version(name, template, activate=True)
            print(f"[seeded] '{name}' -> v{version}")


if __name__ == "__main__":
    seed()

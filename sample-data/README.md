# Sample data

Everything in this folder is **entirely synthetic and fictitious** -- made-up
people ("Jordan Ellis", "Morgan Alvarez"), made-up employers/payers/banks,
made-up SSNs/EINs (which do not follow real SSA/IRS issuance ranges), and
made-up dollar amounts. Nothing here was sourced from any real person's or
company's actual tax documents.

## Real IRS forms vs. synthetic recreations -- what this repo actually did

This repo uses **synthetic recreations** of the IRS forms, built with
[`reportlab`](./scripts/generate_samples.py), not the actual IRS-published
PDFs. Two reasons, deliberately:

1. **Reliability for a filled, fictitious demo.** The real IRS PDFs (W-2,
   1099-NEC, 1099-INT, 1099-DIV, Schedule K-1) are complex fillable-form
   layouts. What this tutorial needs is a small set of *filled-in* example
   documents with realistic-but-fake data for a repeatable, zero-setup demo
   and a deterministic pytest/live-smoke fixture -- a recreation we control
   completely is more reliable for that than programmatically stamping
   values onto someone else's fillable-PDF field layout.
2. **Box numbers and labels are still accurate.** A form's box numbering
   (e.g. W-2 box 1 = "Wages, tips, other compensation", box 2 = "Federal
   income tax withheld"; 1099-NEC box 1 = "Nonemployee compensation";
   1099-INT box 1 = "Interest income"; 1099-DIV box 1a/1b/2a; Schedule K-1
   (Form 1065) box 1/2/14) is public, government-published numbering, not a
   copyrightable design element -- so the recreations use the *real* box
   numbers and labels throughout, which is what actually matters for the
   classification/extraction pipeline this app demonstrates. Only the visual
   layout (fonts, borders, spacing) is our own simplified design rather than
   a pixel-for-pixel copy of the official form.

Every generated PDF says "(Recreation)" in its title and carries a footer
note that it is a synthetic demo document, not an IRS-issued one.

Regenerate everything at any time with:

```bash
pip install reportlab   # already in backend/requirements.txt
python sample-data/scripts/generate_samples.py
```

## What's here

### `w2/` -- 2 Forms W-2 (Wage and Tax Statement), two different fictitious employers

| File | Employer | Employee | Box 1 wages |
|---|---|---|---|
| `W2_Cascade_Retail_Group_Jordan_Ellis.pdf` | Cascade Retail Group | Jordan Ellis | $28,450.00 |
| `W2_Fenwick_Logistics_Inc_Morgan_Alvarez.pdf` | Fenwick Logistics Inc | Morgan Alvarez | $41,200.00 |

### `1099/` -- one each of 1099-NEC, 1099-INT, 1099-DIV

| File | Type | Payer | Recipient | Key box |
|---|---|---|---|---|
| `1099NEC_Bluepeak_Design_Studio_Jordan_Ellis.pdf` | 1099-NEC | Bluepeak Design Studio | Jordan Ellis | Box 1: $6,200.00 nonemployee comp |
| `1099INT_Harborview_Savings_Bank_Jordan_Ellis.pdf` | 1099-INT | Harborview Savings Bank | Jordan Ellis | Box 1: $184.32 interest |
| `1099DIV_Crestline_Investments_Morgan_Alvarez.pdf` | 1099-DIV | Crestline Investments | Morgan Alvarez | Box 1a: $912.44 ordinary dividends |

### `k1/` -- one Schedule K-1 (Form 1065)

| File | Partnership | Partner | Key box |
|---|---|---|---|
| `K1_Alvarez_Family_Holdings_LLC_Morgan_Alvarez.pdf` | Alvarez Family Holdings LLC | Morgan Alvarez | Box 1: $3,200.00 ordinary business income |

### `bank-statements/` -- one plain bank interest statement (NOT an official tax form)

| File | Bank | Account holder | Total interest |
|---|---|---|---|
| `Harborview_Savings_Bank_Statement_Jordan_Ellis.pdf` | Harborview Savings Bank | Jordan Ellis | $184.32 |

This is deliberately **not** on Jordan Ellis's expected-documents checklist
(only the W-2/1099-NEC/1099-INT are) -- uploading it demonstrates the
`cross_check` node's "unexpected document" info flag: useful supplementary
backup for the 1099-INT, but not itself a required filing document.

### `organizer/` -- prior-year tax organizer checklists (JSON), one per client

These are the "expected documents" checklists a real tax preparer carries
forward from a client's prior-year organizer -- e.g. "this client has a W-2
job plus freelance 1099 income plus one savings account, so expect a W-2, a
1099-NEC, and a 1099-INT this year." Loaded into the `clients` table by
`backend/scripts/seed_clients.py`.

- `jordan_ellis.json` -- expects a W-2 (Cascade Retail Group), a 1099-NEC
  (Bluepeak Design Studio), and a 1099-INT (Harborview Savings Bank). All
  three are present in the seeded example documents, so this client's
  organizer shows **complete**.
- `morgan_alvarez.json` -- expects two W-2s (a mid-year job change: Fenwick
  Logistics Inc through June, Northbridge Analytics LLC from July), a
  Schedule K-1 (Alvarez Family Holdings LLC), and a 1099-DIV (Crestline
  Investments). Only the Fenwick W-2, the K-1, and the 1099-DIV are among
  the seeded example documents -- **the Northbridge Analytics W-2 is
  deliberately never provided**, so this client's organizer shows
  **incomplete** with a "still missing" flag on that document, and
  `backend/scripts/seed_examples.py` also seeds a rejected duplicate
  re-upload of the Fenwick W-2 to demonstrate the duplicate-document catch.

This client/document data is loaded by `backend/scripts/seed_clients.py`
and `backend/scripts/seed_examples.py` -- see the root README for how it's
wired into the `cross_check` graph node and the Client Organizer page.

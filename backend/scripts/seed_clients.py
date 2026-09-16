"""Load the bundled synthetic prior-year tax organizer checklists
(`sample-data/organizer/*.json`) into the `clients` table.

Each JSON file represents one fictitious client's "this is what your tax
situation implies you should receive this year" checklist, carried forward
from a prior-year organizer -- exactly the artifact a real tax preparer
uses to know what to chase down as documents trickle in.

Run with:
    python -m scripts.seed_clients

Safe to re-run: upserts by the client `id` in each JSON file rather than
inserting duplicates, and only resets `expected_documents`/`notes`/`name`/
`tax_year` (never touches `documents_received`/`completeness_status`,
which `app/tools/organizer.py::recompute_client_completeness` owns).
"""
from __future__ import annotations

import glob
import json
import os

from app.config import get_settings
from app.db.models import Client
from app.db.session import SessionLocal


def seed() -> None:
    settings = get_settings()
    organizer_dir = os.path.join(settings.sample_data_dir, "organizer")
    paths = sorted(glob.glob(os.path.join(organizer_dir, "*.json")))
    if not paths:
        raise SystemExit(
            f"No organizer checklists found in {organizer_dir!r}. Did you set "
            "SAMPLE_DATA_DIR correctly, or run sample-data/scripts/generate_samples.py?"
        )

    with SessionLocal() as db:
        for path in paths:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            client = db.get(Client, data["id"])
            expected = data.get("expected_documents", [])
            if client is None:
                client = Client(
                    id=data["id"],
                    name=data["name"],
                    tax_year=data["tax_year"],
                    notes=data.get("notes", ""),
                    expected_documents=expected,
                    documents_expected=len(expected),
                    documents_received=0,
                    completeness_status="incomplete",
                )
                db.add(client)
                print(f"[seeded] client {data['id']!r} ({data['name']})")
            else:
                client.name = data["name"]
                client.tax_year = data["tax_year"]
                client.notes = data.get("notes", "")
                client.expected_documents = expected
                client.documents_expected = len(expected)
                print(f"[updated] client {data['id']!r} ({data['name']})")
        db.commit()


if __name__ == "__main__":
    seed()

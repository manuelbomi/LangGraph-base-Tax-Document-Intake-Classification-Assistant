"""Thin prompt registry backed by the Postgres `prompts` table.

Design: each prompt has a `name` (e.g. "classify_document", "extract_w2")
and one or more `version`s. Exactly one version per name is flagged
`is_active`; that is the version `get_prompt()` returns. This lets you
iterate on prompts (add a new version, A/B it, roll back) without
redeploying code -- you just insert a new row and flip `is_active`.

A small process-local cache avoids hitting Postgres on every graph node
invocation; call `invalidate_cache()` (or restart the process) after
activating a new prompt version if you need the change to take effect
immediately.
"""
from __future__ import annotations

import threading

from sqlalchemy import select

from app.db.models import Prompt
from app.db.session import SessionLocal

_cache: dict[str, str] = {}
_cache_lock = threading.Lock()


def invalidate_cache(name: str | None = None) -> None:
    with _cache_lock:
        if name is None:
            _cache.clear()
        else:
            _cache.pop(name, None)


def get_prompt(name: str) -> str:
    """Return the active template text for `name`, raising if none is active."""
    with _cache_lock:
        if name in _cache:
            return _cache[name]

    with SessionLocal() as db:
        stmt = select(Prompt).where(Prompt.name == name, Prompt.is_active.is_(True))
        prompt = db.execute(stmt).scalar_one_or_none()

    if prompt is None:
        raise LookupError(
            f"No active prompt version found for '{name}'. "
            "Did you run `python -m app.prompts.seed_prompts`?"
        )

    with _cache_lock:
        _cache[name] = prompt.template
    return prompt.template


def render_prompt(name: str, **kwargs: object) -> str:
    """Fetch the active template for `name` and `.format(**kwargs)` it."""
    template = get_prompt(name)
    return template.format(**kwargs)


def add_prompt_version(name: str, template: str, *, activate: bool = True) -> int:
    """Insert a new version of a prompt, optionally activating it.

    Returns the new version number. This is the "admin" operation referenced
    in the README for adding/rolling prompt versions; it can be called from
    a script or wrapped in an admin-only API route.
    """
    with SessionLocal() as db:
        current_max = db.execute(
            select(Prompt.version)
            .where(Prompt.name == name)
            .order_by(Prompt.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        next_version = (current_max or 0) + 1

        if activate:
            db.query(Prompt).filter(Prompt.name == name, Prompt.is_active.is_(True)).update(
                {Prompt.is_active: False}
            )

        db.add(
            Prompt(
                name=name,
                version=next_version,
                template=template,
                is_active=activate,
            )
        )
        db.commit()

    invalidate_cache(name)
    return next_version

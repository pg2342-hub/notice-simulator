"""Load notice variants: markdown files with a small front matter block (id, name)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Notice:
    id: str
    name: str
    text: str


def load_notice(path: str | Path) -> Notice:
    raw = Path(path).read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        _, front, body = raw.split("---", 2)
        for line in front.strip().splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    if "id" not in meta or "name" not in meta:
        raise ValueError(f"{path}: front matter needs id and name")
    return Notice(meta["id"], meta["name"], body.strip())


def load_notices(paths: list[str | Path]) -> list[Notice]:
    notices = [load_notice(p) for p in sorted(paths)]
    ids = [n.id for n in notices]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate notice ids: {ids}")
    return notices

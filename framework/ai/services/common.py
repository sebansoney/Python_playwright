"""Shared helpers for AI services: prompt loading and safe output writing."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from framework.core.exceptions import FrameworkError
from framework.core.paths import PROJECT_ROOT

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_PROTECTED = (PROJECT_ROOT / "tests", PROJECT_ROOT / "framework", PROJECT_ROOT / "config")


@cache
def load_prompt(name: str) -> str:
    """Prompt text without its version comment. Prompts are versioned files so a change
    in AI behaviour is reviewable in a diff like any other code change."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return re.sub(r"^<!--.*?-->\s*", "", text, flags=re.S).strip()


def prompt_version(name: str) -> str:
    match = re.search(r"version:\s*(\S+)", (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"))
    return match.group(1) if match else "?"


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def write_report(out_dir: Path, stem: str, markdown: str, data: BaseModel | None = None) -> Path:
    """Write <stem>.md (+ <stem>.json) into the AI output folder. Returns the .md path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{stem}.md"
    md.write_text(markdown, encoding="utf-8")
    if data is not None:
        (out_dir / f"{stem}.json").write_text(data.model_dump_json(indent=2), encoding="utf-8")
    return md


class UnsafeDraftLocationError(FrameworkError):
    """AI output may never be written into tests/, framework/ or config/."""


def write_draft(drafts_dir: Path, filename: str, content: str) -> Path:
    """Write AI-generated code ONLY into the drafts folder (human approval gate)."""
    target = (drafts_dir / Path(filename).name).resolve()
    for protected in _PROTECTED:
        if target.is_relative_to(protected.resolve()):
            raise UnsafeDraftLocationError(f"Refusing to write AI output into {protected}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def bullet(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- (none)"

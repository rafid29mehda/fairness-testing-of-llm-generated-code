"""Load the task catalog and the legitimate-use table."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml


@dataclass(frozen=True)
class Sanity:
    feature: str
    step: float
    kind: str


@dataclass(frozen=True)
class Task:
    id: str
    return_type: str
    docstring: str
    legitimate: Dict[str, str]
    sanity: Optional[Sanity]
    group: str


@dataclass(frozen=True)
class Label:
    label: str
    source: str


def load_tasks(path: Path) -> list:
    data = yaml.safe_load(Path(path).read_text())
    tasks = []
    for raw in data["tasks"]:
        sanity = None
        if raw.get("sanity"):
            sanity = Sanity(
                feature=raw["sanity"]["feature"],
                step=raw["sanity"]["step"],
                kind=raw["sanity"]["kind"],
            )
        tasks.append(
            Task(
                id=raw["id"],
                return_type=raw["return_type"],
                docstring=raw["docstring"],
                legitimate=dict(raw["legitimate"]),
                sanity=sanity,
                group=raw["group"],
            )
        )
    return tasks


def load_labels(path: Path) -> Dict[Tuple[str, str], Label]:
    labels = {}
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            labels[(row["task"], row["attribute"])] = Label(row["label"], row["source"])
    return labels

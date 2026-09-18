"""Pull the expected function out of a model response. Never guess a different one."""

from __future__ import annotations

import ast
import re
from typing import Optional, Tuple

_FENCE = re.compile(r"```(?:python|py)?[^\n]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_function(text: str, expected_name: str) -> Tuple[Optional[str], str]:
    """Return (source, reason). reason is empty when extraction succeeded."""
    fences = _FENCE.findall(text or "")
    if fences:
        saw_parse_error = False
        saw_wrong = False
        for block in fences:
            code, reason = _from_source(block, expected_name)
            if reason == "":
                return code, ""
            if reason == "ambiguous":
                return None, "ambiguous"
            if reason == "parse_error":
                saw_parse_error = True
            elif reason == "wrong_name":
                saw_wrong = True
        if saw_parse_error and not saw_wrong:
            return None, "parse_error"
        return None, "wrong_name"
    return _from_source(_slice_to_code(text or ""), expected_name)


def _slice_to_code(text: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(("def ", "import ", "from ", "@")):
            return "\n".join(lines[i:]) + ("\n" if text.endswith("\n") else "")
    return text


def _from_source(src: str, expected_name: str) -> Tuple[Optional[str], str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None, "parse_error"
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == expected_name
    ]
    if len(matches) > 1:
        return None, "ambiguous"
    if len(matches) == 0:
        return None, "wrong_name"
    segment = ast.get_source_segment(src, matches[0])
    if not segment:
        return None, "wrong_name"
    if not segment.endswith("\n"):
        segment += "\n"
    return segment, ""

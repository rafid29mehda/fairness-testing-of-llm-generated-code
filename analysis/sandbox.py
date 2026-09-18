"""Run one generated function in a fresh subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

_CHILD = Path(__file__).with_name("sandbox_child.py")


def run_in_sandbox(
    code: str,
    function_name: str,
    calls: List[Dict],
    per_call_timeout_s: float = 2.0,
    work_root: Optional[Path] = None,
) -> Dict:
    """Return the child's JSON, or a timeout/error row for every call."""
    job = {
        "code": code,
        "function_name": function_name,
        "calls": calls,
        "per_call_timeout_s": per_call_timeout_s,
    }
    total = per_call_timeout_s * max(1, len(calls)) + 5
    parent = Path(work_root) if work_root is not None else None
    with tempfile.TemporaryDirectory(dir=parent) as tmp:
        env = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": tmp,
            "TMPDIR": tmp,
        }
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-B", str(_CHILD)],
                input=json.dumps(job),
                capture_output=True,
                text=True,
                timeout=total,
                cwd=tmp,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _failed(calls, "timeout", secret_in_env=False, limits_applied=[])
    if proc.returncode != 0 or not proc.stdout.strip():
        return _failed(calls, "error", secret_in_env=False, limits_applied=[], detail=proc.stderr[-500:])
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return _failed(calls, "error", secret_in_env=False, limits_applied=[], detail="bad-json")


def _failed(calls, status, secret_in_env, limits_applied, detail=""):
    return {
        "results": [
            {"id": call["id"], "status": status, "value": None, "detail": detail} for call in calls
        ],
        "secret_in_env": secret_in_env,
        "limits_applied": limits_applied,
    }

"""Child process. Reads one JSON job on stdin and writes one JSON object on stdout.

This file is the only code that execs a generated function. The parent does not
import it into the test process.
"""

from __future__ import annotations

import json
import os
import signal
import sys

ALLOWED_MODULES = {
    "math",
    "statistics",
    "json",
    "re",
    "datetime",
    "collections",
    "functools",
    "itertools",
    "decimal",
    "fractions",
    "copy",
    "typing",
    "time",
}
SECRET_KEYS = ("GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
_REAL_IMPORT = __import__


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = (name or "").split(".")[0]
    if root not in ALLOWED_MODULES:
        raise ImportError(f"blocked import: {root}")
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


def _restricted_builtins():
    import builtins

    allowed = [
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len",
        "list", "max", "min", "range", "round", "sorted", "str", "sum", "tuple",
        "zip", "map", "filter", "isinstance", "print", "repr", "pow", "divmod",
        "True", "False", "None", "Exception", "ValueError", "TypeError", "KeyError",
        "ZeroDivisionError", "StopIteration", "reversed", "slice", "set", "frozenset",
        "iter", "next", "object", "hasattr", "getattr", "setattr", "super",
        "staticmethod", "classmethod", "property", "format", "ord", "chr", "hash",
        "id", "hex", "bin", "oct",
    ]
    table = {}
    for name in allowed:
        if hasattr(builtins, name):
            table[name] = getattr(builtins, name)
    table["__import__"] = _guarded_import
    return table


def _apply_limits() -> list:
    applied = []
    try:
        import resource
    except ImportError:
        return applied
    specs = [
        ("RLIMIT_CPU", 8),
        ("RLIMIT_FSIZE", 1_000_000),
        ("RLIMIT_NOFILE", 64),
        ("RLIMIT_AS", 1024 * 1024 * 1024),
    ]
    for name, value in specs:
        limit = getattr(resource, name, None)
        if limit is None:
            continue
        try:
            resource.setrlimit(limit, (value, value))
        except (ValueError, OSError):
            continue
        applied.append(name)
    return applied


def _json_safe(value):
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    return False


def _load(code: str, function_name: str):
    globs = {"__builtins__": _restricted_builtins(), "__name__": "generated"}
    exec(code, globs)  # noqa: S102  -- the child exists to exec this one function
    fn = globs.get(function_name)
    if not callable(fn):
        raise LookupError(function_name)
    return fn


def _call(fn, person, timeout_s: float):
    def handler(signum, frame):
        raise TimeoutError("call exceeded timeout")

    signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        value = fn(person)
    except TimeoutError:
        return "timeout", None, "timeout"
    except ImportError as exc:
        if "blocked import" in str(exc):
            return "blocked_import", None, str(exc)
        return "error", None, str(exc)
    except Exception as exc:  # noqa: BLE001 -- untrusted code, record and continue
        return "error", None, type(exc).__name__
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if not _json_safe(value):
        return "error", None, "unserializable"
    return "ok", value, ""


def main() -> None:
    job = json.loads(sys.stdin.read() or "{}")
    applied = _apply_limits()
    payload = {
        "results": [],
        "limits_applied": applied,
        "secret_in_env": any(key in os.environ for key in SECRET_KEYS),
    }
    try:
        fn = _load(job["code"], job["function_name"])
    except ImportError as exc:
        status = "blocked_import" if "blocked import" in str(exc) else "error"
        for call in job.get("calls", []):
            payload["results"].append({"id": call["id"], "status": status, "value": None})
        json.dump(payload, sys.stdout)
        return
    except Exception as exc:  # noqa: BLE001
        for call in job.get("calls", []):
            payload["results"].append(
                {"id": call["id"], "status": "error", "value": None, "detail": type(exc).__name__}
            )
        json.dump(payload, sys.stdout)
        return
    timeout_s = float(job.get("per_call_timeout_s", 2))
    for call in job.get("calls", []):
        status, value, detail = _call(fn, call["person"], timeout_s)
        row = {"id": call["id"], "status": status, "value": value}
        if detail and status != "ok":
            row["detail"] = detail
        payload["results"].append(row)
    json.dump(payload, sys.stdout)


if __name__ == "__main__":
    main()

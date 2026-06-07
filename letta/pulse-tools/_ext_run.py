#!/usr/bin/env python3
"""Generic entrypoint for Letta Code extension tools to invoke pinned-venv Python.

The extension (Node) execFiles the pa-tools venv python running this script:

    _ext_run.py <module> <func> [<json-kwargs>]

It imports <module>, calls <func>(**kwargs), and prints the result — a str
as-is, otherwise json.dumps(result). Errors are emitted as a JSON object on
stderr with a non-zero exit so the extension can surface them.

Reusable for ANY migrated (ex-server) Python tool — not snapshot-specific.
Relies on PYTHONPATH (set by the extension) to locate the target module +
its helpers. See docs/superpowers/specs/2026-06-07-pulse-analytics-extension-pilot-design.md
"""

import sys
import json
import importlib
import traceback


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({
            "status": "error",
            "error_message": "usage: _ext_run.py <module> <func> [json-kwargs]",
        }), file=sys.stderr)
        return 2

    module_name, func_name = sys.argv[1], sys.argv[2]
    kwargs = {}
    if len(sys.argv) > 3 and sys.argv[3].strip():
        try:
            kwargs = json.loads(sys.argv[3])
        except json.JSONDecodeError as e:
            print(json.dumps({
                "status": "error",
                "error_message": f"invalid json-kwargs: {e}",
            }), file=sys.stderr)
            return 2

    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        result = func(**kwargs)
    except Exception as e:  # noqa: BLE001 - surface any tool failure to the extension
        print(json.dumps({
            "status": "error",
            "error_message": str(e),
            "trace": traceback.format_exc()[-1500:],
        }), file=sys.stderr)
        return 1

    sys.stdout.write(result if isinstance(result, str) else json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

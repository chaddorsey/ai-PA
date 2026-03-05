import json
import sys


def output_result(data, json_output: bool = False):
    if json_output:
        print(json.dumps(data, indent=2, default=str))
        return
    if isinstance(data, list):
        for item in data:
            _print_item(item)
            print()
    elif isinstance(data, dict):
        _print_item(data)
    else:
        print(data)


def output_error(message: str, json_output: bool = False):
    if json_output:
        print(json.dumps({"error": message}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)


def _print_item(item: dict):
    for key, value in item.items():
        if value is None:
            continue
        if isinstance(value, list):
            print(f"  {key}: {', '.join(str(v) for v in value)}")
        else:
            print(f"  {key}: {value}")

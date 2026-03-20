"""Field mask filtering for CLI output."""

from __future__ import annotations


def apply_field_mask(data, fields: list[str] | None):
    """Filter output data to only include specified fields.

    Handles the standard {status, data:{tasks:[]}, meta:{}} envelope
    by applying the mask to tasks inside data.tasks.
    """
    if fields is None:
        return data
    if isinstance(data, dict):
        # Standard envelope: apply mask to tasks inside data.tasks
        if "data" in data and isinstance(data["data"], dict) and "tasks" in data["data"]:
            masked_tasks = [
                {k: v for k, v in item.items() if k in fields}
                for item in data["data"]["tasks"]
                if isinstance(item, dict)
            ]
            result = dict(data)
            result["data"] = dict(data["data"])
            result["data"]["tasks"] = masked_tasks
            return result
        # Legacy bridge envelope: {"result": [...]}
        if "result" in data and isinstance(data["result"], list):
            return [{k: v for k, v in item.items() if k in fields} for item in data["result"] if isinstance(item, dict)]
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in fields} for item in data if isinstance(item, dict)]
    return data

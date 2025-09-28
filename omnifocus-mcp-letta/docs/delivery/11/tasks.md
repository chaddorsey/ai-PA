# Tasks for PBI 11: Planned Date Exposure

This document lists all tasks associated with PBI 11.

**Parent PBI**: [PBI 11: Planned Date Exposure](./prd.md)

## Task Summary

| Task ID | Name | Status | Description |
| :------ | :---- | :----- | :---------- |
| 11-1 | [Audit OmniFocus planned date support](./11-1.md) | Review | Confirm availability of `plannedDate`/`effectivePlannedDate` across task types and identify serialization touchpoints |
| 11-2 | [Expose planned dates in plugin payloads](./11-2.md) | Review | Update plugin serializers to include planned date fields with safe ISO conversion |
| 11-3 | [Propagate planned dates through MCP server](./11-3.md) | Review | Extend TypeScript interfaces/schemas and HTTP bridge to surface planned dates |
| 11-4 | [Document planned date support and regression coverage](./11-4.md) | InProgress | Update docs and regression checks to reflect planned date support |

# Jira Query Language (JQL) Documentation

This directory contains downloaded documentation for Jira Query Language (JQL) from Atlassian Support.

## Source

All documentation is sourced from:
- **Base URL**: https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/
- **Last Updated**: 2025-12-31

## Contents

The following JQL documentation pages are included:

1. **use-advanced-search-with-jira-query-language-jql.md** - Main overview page
2. **what-is-advanced-search-in-jira-cloud.md** - Introduction to advanced search
3. **jql-functions.md** - JQL functions reference
4. **jql-developer-status.md** - Developer status in JQL
5. **jql-fields.md** - Available JQL fields
6. **jql-keywords.md** - JQL keywords reference
7. **jql-operators.md** - JQL operators reference
8. **search-for-advanced-roadmaps-custom-fields-in-jql.md** - Advanced Roadmaps custom fields
9. **use-jira-query-language-jql-to-create-service-level-agreements-slas.md** - SLA queries
10. **write-jql-queries-for-slas.md** - Writing SLA queries
11. **how-to-structure-your-sla-goals-around-priority-using-jql.md** - SLA goal structure

## Usage

These markdown files can be used as reference documentation when:
- Writing JQL queries for Jira searches
- Understanding JQL syntax and capabilities
- Building tools that generate JQL queries
- Training on JQL usage

## Regenerating Documentation

To update these files, run:

```bash
python3 /Volumes/main-drive/ai-PA/jira-rovo-server/download-jql-docs.py
```

## Notes

- Each file includes metadata (source URL, title, crawl timestamp) in YAML frontmatter
- Content is converted from HTML to Markdown format
- Links may need to be updated if Atlassian changes their URL structure


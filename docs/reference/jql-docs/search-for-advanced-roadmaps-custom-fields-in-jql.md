---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/
title: Search for Advanced Roadmaps custom fields in JQL | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:47.922205
---

# Search for Advanced Roadmaps custom fields in JQL

You can use Jira Query Language (JQL) to search for work items with custom work item fields used in your plan. You can search for

* Parent link
* Child work items
* Team field
* Target start or Target end

## Parent link

To search for child work items of a work item in your plan using the work item’s Parent Link:

|  |  |
| --- | --- |
| Syntax | `"Parent Link"` |
| Alias | `cf[CustomFieldID]` |
| Field Type | Parent Link relationship |
| Auto-complete | No |
| Supported operators | IS,IS NOT,=,!=,IN,NOT IN |
| Unsupported operators | ~,!~,>,>=,<,<= WAS,WAS IN,WAS NOT,WAS NOT IN,CHANGED |
| Supported Keywords | `EMPTY` |
| Examples | * Get the list of child work items from parent work items:  `"Parent Link" = EX-001` * Get the child work items from multiple Parent Links:  `"Parent Link" IN (EX-000, EX-001, EX-002, EX-003)` * Find all work items with no Parent Link:  `"Parent Link" IS EMPTY` * Find all work items that have either EX-001 set as a parent or don't have a parent.  `"Parent Link" IN (EX-001, EMPTY)` * Get the child work items from multiple Parent Links:  `"Parent Link" IN (EX-000, EX-001, EX-002, EX-003)` |

## Child work items

To search for child work items of a work item:

|  |  |
| --- | --- |
| Syntax | `portfolioChildworkitemssOf("work item key")` |
| Field Type | JQL function returning work item keys |
| Auto-complete | No |
| Supported operators | IS,IS NOT,=,!=,IN,NOT IN |
| Unsupported operators | ~,!~,>,>=,<,<= WAS,WAS IN,WAS NOT,WAS NOT IN,CHANGED |
| Supported Keywords | `EMPTY` |
| Examples | * To get all child work items below INIT-00 and not just the child work items at the epic hierarchy level:  `workitemkey in portfolioChildworkitemsOf("INIT-001")` * if you want to return just the story-level work items:  `workitemkey in portfolioChildworkitemsOf("INIT-001") AND workType = Story` * If needed, you can skip returning work items of the hierarchy levels you don't need:  `workitemkey in portfolioChildworkitemsOf("INIT-001") AND workType != Epic.` |

## Team field

To search for work items, including subtasks, using the Team custom field:

|  |  |
| --- | --- |
| Syntax | `"Team"` |
| Aliases | `"Team[Team]" cf[CustomFieldID]` |
| Field type | Team Field |
| Auto-complete | Yes  **Note:** Selecting the shared team name from the auto-suggested list of team names will replace the actual name of the team in the query with its numerical ID. For example:  `"Team" = MyTeam → "Team" = 3` |
| Supported operators | IS,IS NOT,=,!=,IN,NOT IN |
| Unsupported operators | ~,!~,>,>=,<,<= WAS,WAS IN,WAS NOT,WAS NOT IN,CHANGED |
| Supported Keywords | `EMPTY` |
| Examples | * Get the list of work items assigned to a team:  `"Team" = "shared team name"`    + Get the list of work items assigned to any set of teams type:  `"Team" IN ("Shared team 1", "Shared team 2", "Shared team 3")`   + Find all work items in the "iOS app development" space that don't have a team assigned:  `space = iOS app development and "Team" IS EMPTY`   + Find all stories in the "IOS-76" epic that don't have a team assigned:  `workitemKey = IOS-76 and "Team" IS EMPTY`   + Find all work items with no team assigned:  `"Team" IS EMPTY` |

## Target start or Target end

To search for work items based on their target start or end date:

|  |  |
| --- | --- |
| Syntax | `"Target start" /or/ "Target end"` |
| Alias | `cf[CustomFieldID]` |
| Field type | Target Date Field |
| Auto-complete | Yes  **Note:** The auto-suggested list contains JQL functions that returns date-time values where the function name matches the user supplied text. For example:  `"Target start" = end → endOfDay(), endOfMonth(), endOfWeek(), endOfYear()` |
| Supported operators | =, !=, NOT IN, IN, IS NOT, IS, >, >=, <, <= |
| Unsupported operators | ~,!~,>,>=,<,<= WAS,WAS IN,WAS NOT,WAS NOT IN,CHANGED |
| Supported Keywords | `EMPTY` |
| Examples | * Find all work items with target start after 2 Jan 2020:   `"Target start" >= "2020-01-02"`   * Find all work items with target start before current timestamp:   `"Target start" < now()`   * Find all work items with target end earlier than 5 days ago:   `"Target end" <= -5d`   * Find all work items without a target end date:   `"Target end" is not EMPTY` |

Was this helpful?

Yes

No

It wasn't accurateIt wasn't clearIt wasn't relevant

Provide feedback about this article

## Still need help?

The Atlassian Community is here for you.

[Ask the Community](https://community.atlassian.com/t5/custom/page/page-id/create-post-step-1?add-tags=jira-service-management,Cloud)

* [Use advanced search with Jira Query Language (JQL)](/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
* Show more
* [JQL developer status](/jira-service-management-cloud/docs/jql-developer-status/)
* [JQL fields](/jira-service-management-cloud/docs/jql-fields/)
* [JQL keywords](/jira-service-management-cloud/docs/jql-keywords/)
* [JQL operators](/jira-service-management-cloud/docs/jql-operators/)
* Search for Advanced Roadmaps custom fields in JQL

On this page[Parent link](/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/#Parent-link)[Child work items](/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/#Child-work-items)[Team field](/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/#Team-field)[Target start or Target end](/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/#Target-start-or-Target-end)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
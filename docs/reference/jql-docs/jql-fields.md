---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/jql-fields/
title: JQL fields | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:41.803091
---

# JQL fields

We're updating terminology in Jira, moving from "issue" to "work item", and "project" to "space".

As we roll out these changes, some JQL entries using the new terms may not work yet. If you come across this, try using the old term instead.

**There are no changes to existing JQL queries.**

JQL lets you search for a value in a specific field. Each field in Jira has a corresponding JQL name. If you’ve made a custom field, you’ll be asked to name the field.

In a clause, a field is followed by an operator, which in turn is followed by one or more values (or functions). The operator compares the value of the field with one or more values or functions on the right, such that only true results are retrieved by the clause. It's not possible to compare two fields in JQL.

## Affected version

Search for work items that are assigned to a particular affects version(s). You can search by version name or version ID (i.e. the number that Jira automatically allocates to a version). It is better to search by version ID than by version name as different spaces may have versions with the same name.

|  |  |
| --- | --- |
| Syntax | `affectedVersion` |
| Field Type | VERSION |
| Auto-complete | Yes |
| Supported operators | `= , != , > , >= , < , <=`  `IS, IS NOT, IN, NOT IN` Note that the comparison operators (e.g. ">") use the version order that has been set up by your space administrator, not a numeric or alphabetic order. |
| Unsupported operators | `~ , !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | When used with the **=** and **!=** operators, this field supports:   * latestReleasedVersion() * earliestUnreleasedVersion()   When used with the **IN** and **NOT IN** operators, this field supports:   * releasedVersions() * unreleasedVersions() |
| Examples | * Find work items with an AffectedVersion of 3.14: `affectedVersion = "3.14"`   *Note that full-stops are reserved characters and need to be surrounded by quote-marks.* * Find work items with an AffectedVersion of "Big Ted": `affectedVersion = "Big Ted"` * Find work items with an AffectedVersion ID of 10350: `affectedVersion = 10350` |

## Approvals

Used in business spaces and Jira Service Management only.

Search for requests that have been approved or require approval. This can be further refined by user.

|  |  |
| --- | --- |
| Syntax | `approvals` |
| Field Type | USER |
| Auto-complete | No |
| Supported operators | `=` |
| Unsupported operators | `~ , != , !~ , > , >= , < , <=`  `IS , IS NOT , IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | * approved() * approver() * myApproval() * myPending() * myPendingApproval() * pending() * pendingBy() |
| Examples | * Find requests that require or required approval by John Smith: `approval = approver(jsmith)` * Find requests that require approval by John Smith: `approval = pendingBy(jsmith)` * Find requests that require or have required approval by the current user: `approval = myPending()` * Find all requests that require approval: `approval = pending()` |

## Assignee

Search for work items that are assigned to a particular user. You can search by the user's full name, ID, or email address.

|  |  |
| --- | --- |
| Syntax | `assignee` |
| Field Type | USER |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS, IS NOT, IN, NOT IN, WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED`  Note that the comparison operators (e.g. ">") use the version order that has been set up by your spaceadmin, not a numeric or alphabetic order. |
| Unsupported operators | `~ , !~ , > , >= , < , <=` |
| Supported functions | When used with the **IN** and **NOT IN** operators, this field supports:   * membersOf()   When used with the **EQUALS** and **NOT EQUALS** operators, this field supports:   * currentUser() |
| Examples | * Find work items that are assigned to John Smith: `assignee = "John Smith"`or `assignee = jsmith` * Find work items that are currently assigned, or were previously assigned, to John Smith: `assignee WAS jsmith` * Find work items that are assigned by the user with email address `bob@mycompany.com:`    + `assignee = "bob@mycompany.com"`  *Note that full-stops and "@" symbols are reserved characters and need to be surrounded by quote-marks.* |

## Attachments

Search for work items that have or do not have attachments.

|  |  |
| --- | --- |
| Syntax | `attachments` |
| Field Type | ATTACHMENT |
| Auto-complete | Yes |
| Supported operators | `IS, IS NOT` |
| Unsupported operators | `=, != , ~ , !~ , > , >= , < , <= IN, NOT IN, WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | * Search for work items that have attachments: `attachments IS NOT EMPTY` * Search for work items that do not have attachments: `attachments IS EMPTY` |

## Category

Search for work items that belong to spaces in a particular category.

|  |  |
| --- | --- |
| Syntax | `category` |
| Field Type | CATEGORY |
| Auto-complete | Yes |
| Supported operators | `=, !=`  `IS, IS NOT, IN, NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <= WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | * Find work items that belong to spaces in the "Alphabet Projects" Category: `category = "Alphabet Projects"` |

## Change gating type

Used in business spaces only.

Search for types of change gating that are used in change requests. "Tracked-only" requests are produced by integrations that stand separately from a change management process. These tools don't respect approval or change gating strategies. Change requests that are "tracked-only" are just for record-keeping purposes.

|  |  |
| --- | --- |
| Syntax | `change-gating-type` |
| Field Type | TEXT |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS, IS NOT, IN, NOT IN` |
| Unsupported operators | `~ , !~ ,` > , >= , < , <= `WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | * Find requests where the gating type is empty: `change-gating-type is EMPTY` * Find requests where the gating type is tracked-only: `change-gating-type = "tracked-only"` |

## Comment

Search for work items that have a comment that contains particular text using Jira text-search syntax. [More about searching syntax for text fields.](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

|  |  |
| --- | --- |
| Syntax | `comment` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~ , !~` |
| Unsupported operators | `= , != , > , >= , < , <=`  `IS, IS NOT, IN, NOT IN, WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | * Find work items where a comment contains the words "My PC is quite old" (a “term search” match): `comment ~ "My PC is quite old"` * Find work items where a comment contains the exact phrase "My PC is quite old": `comment ~ "\"My PC is quite old\""` * Find work items where a comment contains both the exact phrase "My PC is quite old" and the exact phrase “My Mac is quite new”: `comment ~ "\"My PC is quite old\"" AND comment ~ "\"My Mac is quite new\""` |

## Component

Search for work items that belong to a particular component(s) of a space. You can search by component name or component ID (i.e. the number that Jira automatically allocates to a component).

|  |  |
| --- | --- |
| Syntax | `component` |
| Field Type | COMPONENT |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <= WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | When used with the **IN** and **NOT IN** operators, component supports:   * componentsLeadByUser() |
| Examples | * Find work items in the "Comp1" or "Comp2" component: `component in (Comp1, Comp2)` * Find work items in the "Comp1" and"Comp2" components: `component in (Comp1) and component in (Comp2)` `or` `component = Comp1 and component = Comp2` * Find work items in the component with ID 20500: `component = 20500` |

## Created

Search for work items that were created on, before, or after a particular date (or date range). Note that if a time-component is not specified, midnight will be assumed. Please note that the search results will be relative to your configured time zone (which is by default the Jira server's time zone).

Use one of the following formats:

`"yyyy/MM/dd HH:mm"`  
`"yyyy-MM-dd HH:mm"`  
`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks), `"d"` (days), `"h"` (hours) or `"m"` (minutes) to specify a date relative to the current time. The default is `"m"` (minutes). Be sure to use quote-marks (`"`); if you omit the quote-marks, the number you supply will be interpreted as milliseconds after epoch (1970-1-1).

|  |  |
| --- | --- |
| Syntax | `created` |
| Alias | `createdDate` |
| Field Type | DATE |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <= IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~ WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | When used with the **EQUALS**, **NOT EQUALS**, **GREATER THAN**, **GREATER THAN EQUALS**, **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find all work items created before 12th December 2010: `created < "2010/12/12"` * Find all work items created on or before 12th December 2010: `created <= "2010/12/13"` * Find all work items created on 12th December 2010 before 2:00pm: `created > "2010/12/12" and created < "2010/12/12 14:00"` * Find work items created less than one day ago: `created > "-1d"` * Find work items created in January 2011: `created > "2011/01/01"` `and created < "2011/02/01"` * Find work items created on 15 January 2011:`created > "2011/01/15" and created < "2011/01/16"` |

## Creator

Search for work items that were created by a particular user. You can search by the user's full name, ID, or email address. Note that a work item's creator does not change, so you cannot search for past creators (e.g. WAS).

|  |  |
| --- | --- |
| Syntax | `creator` |
| Field Type | USER |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <= CHANGED, WAS, WAS IN, WAS NOT, WAS NOT IN` |
| Supported functions | When used with the **IN**and **NOT IN**operators, this field supports:   * membersOf()   When used with the **EQUALS**and **NOT EQUALS** operators, this field supports:   * currentUser() |
| Examples | * Search for work items that were created by Jill Jones: `creator = "Jill Jones"` `or` `creator = "jjones"` * Search for work items that were created by the user with email address : `creator = "bob@mycompany.com"` `(Note that full-stops and "@" symbols are reserved characters, so the email address needs to be surrounded by quote-marks.)` |

## Custom field

Only applicable if your Jira administrator has created one or more custom fields.

Search for work items where a particular custom field has a particular value. You can search by custom field name or custom field ID (i.e. the number that Jira automatically allocates to a custom field).

For multiple choice and dropdown custom fields, you can search by both option value and option ID. However, for performance reasons, when using `closedSprints()`, `futureSprints()`, and `openSprints()`, you can only search by option value. For example, if `closedSprints()` were to return `16`, the following query:

`"customField1[Dropdown]" in (12, closedSprints())`

would search for option values `12` and `16` and ID `12`.

|  |  |
| --- | --- |
| Syntax | `CustomFieldName` |
| Alias | `cf[CustomFieldID]` |
| Field Type | Depends on the custom field's configuration  Jira text-search syntax can be used with custom fields of type 'Text'. |
| Auto-complete | Yes, for custom fields of type picker, group picker, select, checkbox and radio button fields |
| Supported operators | *Different types of custom field support different operators.* |
| Supported operators:  number and date fields | `= , != , > , >= , < , <=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators:  number and date fields | `~ , !~ WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported operators:  picker, select, checkbox  and radio button fields | `= , !=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators:  picker, select, checkbox  and radio button fields | `~ , !~ , > , >= , < , <= WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported operators:  text fields | `~ , !~`  IS , IS NOT |
| Unsupported operators:  text fields | `= , != , > , >= , < , <= IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported operators:  URL fields | `= , !=` `IS , IS NOT , IN , NOT IN` |
| Unsupported operators:  URL fields | `~ , !~ , > , >= , < , <= WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | *Different types of custom fields support different functions.* |
| Supported functions:  date/time fields | When used with the **EQUALS**, **NOT EQUALS**, **GREATER THAN**, **GREATER THAN EQUALS**,  **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Supported functions:  version picker fields | Version picker fields: When used with the **IN**and **NOT IN** operators, this field supports:   * releasedVersions() * latestReleasedVersion() * unreleasedVersions() * earliestUnreleasedVersion() |
| Examples | * Find work items where the value of the "Location" custom field is "New York": `location = "New York"` * Find work items where the value of the custom field with ID 10003 is "New York": `cf[10003] = "New York"` * Find work items where the value of the "Location" custom field is "London" or "Milan" or "Paris": `cf[10003] in ("London", "Milan", "Paris")` * Find work items where the "Location" custom field has no value: `location != empty` |

## Description

Search for work items where the description contains particular text using Jira text-search syntax. [More about searching syntax for text fields.](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

|  |  |
| --- | --- |
| Syntax | `description` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~ , !~`  `IS , IS NOT` |
| Unsupported operators | `= , !=` , > , >= , < , <= `IN , NOT IN, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items where the description contains the words "Please see screenshot" (a "term search" match): `description ~ "Please see screenshot"` * Find work items where the description contains the exact phrase "Please see screenshot": `description ~ "\"Please see screenshot\""` * Find work items where the description contains both the exact phrase "Please see screenshot" and the exact phrase “What is needed”: `description ~ "\"Please see screenshot\"" AND description ~ "\"What is needed\""` |

## Due

Search for work items that were due on, before, or after a particular date (or date range). Note that the due date relates to the *date* only (not to the time).

Use one of the following formats:

`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks) or `"d"` (days) to specify a date relative to the current date. Be sure to use quote-marks (`"`).

|  |  |
| --- | --- |
| Syntax | `due` |
| Alias | `dueDate` |
| Field Type | DATE |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=` `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~ WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **EQUALS, NOT EQUALS, GREATER THAN, GREATER THAN EQUALS**,  **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find all work items due before 31st December 2010: `due < "2010/12/31"` * Find all work items due on or before 31st December 2010: `due <= "2011/01/01"` * Find all work items due tomorrow: `due = "1d"` * Find all work items due in January 2011: `due >= "2011/01/01"` `and due <= "2011/01/31"` * Find all work items due on 15 January 2011: `due = "2011/01/15"` |

## Environment

Search for work items where the environment contains particular text using Jira text-search syntax. [More about searching syntax for text fields.](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

|  |  |
| --- | --- |
| Syntax | `environment` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~ , !~`  `IS , IS NOT` |
| Unsupported operators | `= , !=` , > , >= , < , <= `IN , NOT IN, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items where the environment contains both the exact phrase "Third floor" and the exact phrase “Fire escape”: `environment ~ "\"Third floor\"" AND environment ~ "\"Fire escape\""` * Find work items where the environment contains both the exact phrase "Third floor" and the exact phrase “Fire escape”: `environment ~ "\"Third floor\"" AND environment ~ "\"Fire escape\""` |

## Epic link

As of February 2024, **Epic link** function has been retired in favor of **Parent**. Existing filters that use the Epic link function still function, but you’ll need to use Parent when creating new filters.

[Jump down to the Parent section of this page.](#Parent "#Parent")

## Filter

You can use a saved filter to narrow your search. You can search by filter name or filter ID (i.e. the number that Jira automatically allocates to a saved filter).

Note:

* It is safer to search by filter ID than by filter name. It is possible for a filter name to be changed, which could break a saved filter that invokes another filter by name. Filter IDs, however, are unique and cannot be changed.
* An unnamed link statement in your typed query will override an ORDER BY statement in the saved filter.
* You can’t run or save a filter that would cause an infinite loop (i.e. you can’t reference a saved filter if it eventually references your current filter).

|  |  |
| --- | --- |
| Syntax | `filter` |
| Aliases | `request , savedFilter , searchRequest` |
| Field Type | Filter |
| Auto-complete | Yes |
| Supported operators | `= , !=` `IN , NOT IN` |
| Unsupported operators | `~ , !~` , > , >= , < , <= `IS , IS NOT, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Search the results of the filter "My Saved Filter" (which has an ID of 12000) for work items assigned to the user jsmith: `filter = "My Saved Filter" and assignee = jsmith` `or` `filter = 12000 and assignee = jsmith` |

## Fix version

Search for work items that are assigned to a particular fix version. You can search by version name or version ID (i.e. the number that Jira automatically allocates to a version).

|  |  |
| --- | --- |
| Syntax | `fixVersion` |
| Field Type | VERSION |
| Auto-complete | Yes |
| Supported operators | `= , != , > , >= , < , <=` `IS , IS NOT, IN , NOT IN, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED`  Note that the comparison operators (e.g. ">") use the version order that has been set up by your space admin, not a numeric or alphabetic order. |
| Unsupported operators | `~ , !~` |
| Supported functions | When used with the **=** and **!=** operators, this field supports:   * latestReleasedVersion() * earliestUnreleasedVersion()   When used with the **IN** and **NOT IN** operators, this field supports:   * releasedVersions() * unreleasedVersions() |
| Examples | * Find work items with a Fix Version of 3.14 or 4.2: `fixVersion in ("3.14", "4.2")` `(Note that full-stops are reserved characters, so they need to be surrounded by quote-marks.)` * Find work items with a Fix Version of "Little Ted": `fixVersion = "Little Ted"` * Find work items with a Fix Version ID of 10001: `fixVersion = 10001` |

## Hierarchy level

Filter work items according to their hierarchy level using a JQL filter. This field uses numbers that correlate to hierarchy levels. Use:

* 1 to filter by parent level task, such as epics. This level is defined by your Jira administrator.
* 0 to filter by standard level work items, such as stories or tasks
* -1 to filter by subtasks

Currently, this field doesn’t support custom hierarchy levels made in Advanced Roadmaps.

|  |  |
| --- | --- |
| Syntax | `hierarchyLevel` |
| Field Type | Number |
| Auto-complete | Yes |
| Supported operators | `= , != , > , >= , < , <= , IN , NOT IN` |
| Unsupported operators | `~ , !~ , IS, IS NOT, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | * None |
| Examples | * Find work items at the story level: `hierarchyLevel = "0"` * Find work items higher than the subtask level: `hierarchyLevel > -1` |

## Journey

Search for work items that were created during a specific journey execution.

|  |  |
| --- | --- |
| Syntax | `journeyID` |
| Auto-complete | No |
| Supported operators | `= , !=` `IN, NOT IN, IS, IS NOT` |
| Unsupported operators | `> , >= , < , <=~ , !~`  `WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | Find work items with the journey ID "123": `journeyID = 123` |

## Journey parent

Search for journey parent work items that were created using a specific journey type.

|  |  |
| --- | --- |
| Syntax | `journeyParentOfTypeId` |
| Auto-complete | No |
| Supported operators | `= , !=` `IN, NOT IN, IS, IS NOT` |
| Unsupported operators | `> , >= , < , <=~ , !~`  `WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | Find work items with the journey parent ID "123": `journeyParentOfTypeID = 123` |

## Journey type

Search for work items that were created using a specific journey type.

|  |  |
| --- | --- |
| Syntax | `journeyTypeId` |
| Auto-complete | No |
| Supported operators | `= , !=` `IN, NOT IN, IS, IS NOT` |
| Unsupported operators | `> , >= , < , <=~ , !~`  `WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | Find work items with the journey type ID "123": `journeyType = 123` |

## Journey type version

Search for work items that were created using a specific version of a journey type.

|  |  |
| --- | --- |
| Syntax | `journeyTypeVersion` |
| Auto-complete | No |
| Supported operators | `= , !=` `IN, NOT IN, IS, IS NOT` |
| Unsupported operators | `> , >= , < , <=~ , !~`  `WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | Find work items where the journey type version is "1": `journeyTypeVersion = 1` |

## Journey work item

Search for specific work items that were created using a specific journey type.

|  |  |
| --- | --- |
| Syntax | `journeyWorkItemId` |
| Auto-complete | No |
| Supported operators | `= , !=` `IN, NOT IN, IS, IS NOT` |
| Unsupported operators | `> , >= , < , <=~ , !~`  `WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | Find work items with the journey work item ID "123": `journeyWorkItemId = 123` |

## Labels

Search for work items tagged with a label or list of labels. You can also search for work items without any labels to easily identify which work items need to be tagged so they show up in the relevant sprints, queues or reports.

|  |  |
| --- | --- |
| Syntax | `labels` |
| Field Type | LABEL |
| Auto-complete | Yes |
| Supported operators | `= , !=, IS, IS NOT, IN, NOT IN` |
| Unsupported operators | `~ , !~ , , > , >= , < , <=`  `WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | None |
| Examples | * Find work items with an existing label: `labels = "x"` * Find work items without a specified label, including work items without a label: `labels not in ("x") or labels is EMPTY` |

## Last viewed

Search for work items that were last viewed on, before, or after a particular date (or date range). Note that if a time-component is not specified, midnight will be assumed. Please note that the search results will be relative to your configured time zone (which is by default the Jira server's time zone).

Use one of the following formats:

`"yyyy/MM/dd HH:mm"`  
`"yyyy-MM-dd HH:mm"`  
`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks), `"d"` (days), `"h"` (hours) or `"m"` (minutes) to specify a date relative to the current time. The default is `"m"` (minutes). Be sure to use quote-marks (`"`); if you omit the quote-marks, the number you supply will be interpreted as milliseconds after epoch (1970-1-1).

|  |  |
| --- | --- |
| Syntax | `lastViewed` |
| Field Type | DATE |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=` `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `~ , !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **EQUALS**, **NOT EQUALS**, **GREATER THAN**, **GREATER THAN EQUALS**, **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find all work items last viewed before 12th December 2010: `lastViewed < "2010/12/12"` * Find all work items last viewed on or before 12th December 2010: `lastViewed <= "2010/12/13"` * Find all work items last viewed on 12th December 2010 before 2:00pm: `lastViewed > "2010/12/12"` `and created < "2010/12/12 14:00"` * Find work items last viewed less than one day ago: `lastViewed > "-1d"` * Find work items last viewed in January 2011: `lastViewed > "2011/01/01"` `and created < "2011/02/01"` * Find work items last viewed on 15 January 2011: `lastViewed > "2011/01/15"` `and created < "2011/01/16"` |

## Level

Only available if work-level security has been enabled by your Jira administrator.

Search for work items with a particular security level. You can search by work-level security name or work item level security ID (i.e. the number that Jira automatically allocates to a work-level security).

|  |  |
| --- | --- |
| Syntax | `level` |
| Field Type | SECURITY LEVEL |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `> , >= , < , <= , ~ , !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Search for work items with a security level of "Really High" or "level1": `level in ("Really High", level1)` * Search for work items with a security level ID of 123: `level = 123` |

## Organization

Used in business spaces only.

Search for all requests shared with an organization. Requests that were kept private won't be returned.

|  |  |
| --- | --- |
| Syntax | `organizations` |
| Field Type | USER |
| Auto-complete | Yes |
| Supported operators | `= , !=` `IN, NOT IN` |
| Examples | Search for all requests shared with the organization *Atlassian*:  `organizations = "Atlassian"` |

## Original estimate

Only available if time-tracking has been enabled by your Jira administrator.

Search for work items where the original estimate is set to a particular value (i.e. a number, not a date or date range). Use "w", "d", "h" and "m" to specify weeks, days, hours, or minutes.

|  |  |
| --- | --- |
| Syntax | `originalEstimate` |
| Alias | `timeOriginalEstimate` |
| Field Type | DURATION |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `~ , !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items with an original estimate of 1 hour: `originalEstimate = 1h` * Find work items with an original estimate of more than 2 days: `originalEstimate > 2d` |

## Parent

Search for all child work items of a parent. For example, you can view all stories under an epic. This function works for both team-managed and company-managed spaces.

You can search by work item key or by ID.

|  |  |
| --- | --- |
| Syntax | `parent` |
| Field Type | WORKITEM |
| Auto-complete | No |
| Supported operators | `= , !=`  `IN , NOT IN` |
| Unsupported operators | `> , >= , < , <= , ~ , !~`  `IS , IS NOT, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find child work items of work item TEST-1234: `parent = TEST-1234` |

## Parent space

Search for all child work items with a parent work item that belongs to a specific space. You can search by the name of a space or space ID (i.e. the number that Jira automatically allocates to a space).

|  |  |
| --- | --- |
| **Syntax** | `parentProject` |
| **Field Type** | PROJECT |
| **Auto-complete** | No |
| **Supported operators** | `=, !=, IN, NOT IN` |
| **Unsupported operators** | `~, !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| **Supported functions** | When used with the **IN**and **NOT IN** operators, `project` supports:   * `projectsLeadByUser()` * `projectsWhereUserHasPermission()` * `projectsWhereUserHasRole()` |
| **Examples** | * Find work items where the parent project is ABC: `parentProject = "ABC"` * Find work items where the parent project ID is 12345: `parentProject = 12345` |

## Priority

Search for work items with a particular priority. You can search by priority name or priority ID (i.e. the number that Jira automatically allocates to a priority).

|  |  |
| --- | --- |
| Syntax | `priority` |
| Field Type | PRIORITY |
| Auto-complete | Yes |
| Supported operators | `= , != , > , >= , < , <= IS , IS NOT, IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Unsupported operators | `~ , !~` |
| Supported functions | None |
| Examples | * Find work items with a priority of "High": `priority = High` * Find work items with a priority ID of 10000: `priority = 10000` |

## Project

Search for work items that belong to a particular space. You can search by the name of a space, by space key or by space ID (i.e. the number that Jira automatically allocates to a space). In the rare case where there is a space whose key is the same as another space's name, then the space key takes preference and hides results from the second space.

|  |  |
| --- | --- |
| Syntax | `project` |
| Field Type | PROJECT |
| Auto-complete | Yes |
| Supported operators | `= , !=` `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `> , >= , < , <= , ~ , !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **IN**and **NOT IN** operators, `project` supports:   * projectsLeadByUser() * projectsWhereUserHasPermission() * projectsWhereUserHasRole() |
| Examples | * Find work items that belong to the Project that has the name "ABC Project": `project = "ABC Project"` * Find work items that belong to the project that has the key "ABC": `project = "ABC"` * Find work items that belong to the project that has the ID "1234": `project = 1234` |

## Project type

Search for work items that belong to a particular type of space, either:

* “business” which finds work items created in business spaces
* “software” which finds work items created in Jira
* “service\_desk” which finds work items created in service space

Results depend on your permission level. You will only see results for apps you have access to. [Read about](https://support.atlassian.com/user-management/docs/update-product-access-settings/ "https://support.atlassian.com/user-management/docs/update-product-access-settings/") app [access](https://support.atlassian.com/user-management/docs/update-product-access-settings/ "https://support.atlassian.com/user-management/docs/update-product-access-settings/").

|  |  |
| --- | --- |
| **Syntax** | `projectType` |
| **Auto-complete** | Yes |
| **Supported operators** | **=, !=**  **IN, NOT IN** |
| **Unsupported operators** | **>, >=, <, <=, ~, !~**  **IS, IS NOT, WAS, WAS NOT, WAS NOT IN, CHANGED** |
| **Supported functions** | None |
| **Examples** | Find all work items in a software space:  `projectType = ”software”`  Find all work items in either a software space or a service space:  `projectType = ”software” OR projectType = ”service_desk”`  Find all work items that aren’t in a software space:  `projectType != ”software”` |

## Remaining estimate

Only available if time-tracking has been enabled by your Jira administrator.

Search for work items where the remaining estimate is set to a particular value (i.e. a number, not a date or date range). Use "w", "d", "h" and "m" to specify weeks, days, hours, or minutes.

|  |  |
| --- | --- |
| Syntax | `remainingEstimate` |
| Alias | `timeEstimate` |
| Field Type | DURATION |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `~ , !~`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items with a remaining estimate of more than 4 hours: remainingEstimate > 4h |

## Reporter

Search for work items that were reported by a particular user. This may be the same as the creator, but can be distinct. You can search by the user's full name, ID, or email address.

|  |  |
| --- | --- |
| Syntax | `reporter` |
| Field Type | USER |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT, IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Unsupported operators | `~ , !~ , > , >= , < , <=` |
| Supported functions | When used with the **IN** and **NOT IN**operators, this field supports:   * membersOf()   When used with the **EQUALS**and **NOT EQUALS**operators, this field supports:   * currentUser() |
| Examples | * Search for work items that were reported by Jill Jones: `reporter = "Jill Jones"orreporter = jjones` * Search for work items that were reported by the user with email address `bob@mycompany.com`:    + `reporter = "bob@mycompany.com"` *(Note that full-stops and "@" symbols are reserved characters, so the email address needs to be surrounded by quote-marks.)* |

## Request channel type

Used in business spaces only.

Search for requests by the channel that they were created by. For example, you could search for all requests that were emailed to the service space, or all requests that were sent from a customer portal.

|  |  |
| --- | --- |
| Syntax | `request-channel-type` |
| Field Type | TEXT |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS, IS NOT, IN, NOT IN` |
| Unsupported operators | `~ , !~ ,` > , >= , < , <= `WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | When used with the **IN** and **NOT IN** operators, this field supports:   * `email`: requests sent by email * `jira`: work items created in Jira (by clicking the blue **Create** button) * `portal`: requests sent from a service space portal * `anonymous portal`: requests sent from the customer portal by a customer who was not logged in * `api`: requests sent by REST API |
| Examples | * Find requests where the request channel was email: `request-channel-type = email` * Find requests where the request channel was something other than a service space portal: `request-channel-type != portal` * Find requests where the request channel was sent by a CI/CD deployment tool: `request-channel-type = deployment` |

## Request last activity time

Used in business spaces only.

Search for requests that were created on, before, or after a particular date (or date range). Note that if a time-component is not specified, midnight will be assumed. Search results are relative to your configured time zone (which is by default the Jira server's time zone).

Use one of the following formats:

`"yyyy/MM/dd HH:mm"`  
`"yyyy-MM-dd HH:mm"`  
`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks), `"d"` (days), `"h"` (hours) or `"m"` (minutes) to specify a date relative to the current time. The default is `"m"` (minutes). Be sure to use quote-marks (`"`); if you omit the quote-marks, the number you supply will be interpreted as milliseconds after epoch (1970-1-1).

|  |  |
| --- | --- |
| Syntax | `request-last-activity-time` |
| Field Type | DATE |
| Auto-complete | Yes |
| Supported operators | `= , != , > , >= , < , <=`  `IS, IS NOT, IN, NOT IN` |
| Unsupported operators | `~ , !~WAS, WAS IN, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | When used with the **EQUALS, NOT EQUALS, GREATER THAN, GREATER THAN EQUALS**,  **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find all work items last acted on before 23rd May 2016: `request-last-activity-time < "2016/05/23"`    + Find all work items last acted on or before 23rd May 2016: `request-last-activity-time <= "2016/05/23"`   + Find all work items created on 23rd May 2016 and last acted on before 2:00pm that day: `created > "2016/05/23" AND request-last-activity-time < "2016/05/23 14:00"`   + Find work items last acted on less than one day ago: `request-last-activity-time > "-1d"`   + Find work items last acted on in January 2016: `request-last-activity-time > "2016/01/01"` `and request-last-activity-time < "2016/02/01"` |

## Request type

Used in service spaces only.

Search for requests of a certain request type. You can search by request type name or request type description as configured in the Request Type configuration screen.

|  |  |
| --- | --- |
| Syntax | `"Request Type"` |
| Field Type | Custom field |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <= IS , IS NOT, WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED`  Note that the Lucene value for Request Type, is `portal-key/request-type-key`. While the portal key cannot be changed after a service space portal is created, the space key can be changed. The Request Type key cannot be changed once the Request Type is created. |
| Supported functions | None |
| Examples | * Find work items where Request Type is **Request a new account** in spaces that the user has access to: `"Request Type" = "Request a new account"` * Find work items where the Request Type is **Request a new account** in **SimpleDesk** **space**, where the right operand is a selected Lucene value from the auto-complete suggestion list. `"Request Type" = "sd/system-access"` * Find work items where Request Type is either **Request a new account** or **Get IT Help**.  `"Request Type" IN ("Request a new account", "Get IT Help")` |

## Resolution

The resolution field doesn't exist in service team-managed spaces. This means you can't search for work items in service team-managed spaces with the resolution field. Instead, you can use the statusCategory field (a work item is resolved when statusCategory = Done).

Search for work items that have a particular resolution. You can search by resolution name or resolution ID (i.e. the number that Jira automatically allocates to a resolution).

|  |  |
| --- | --- |
| Syntax | `resolution` |
| Field Type | RESOLUTION |
| Auto-complete | Yes |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT, IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Unsupported operators | `~ , !~` |
| Supported functions | None |
| Examples | * Find work items with a resolution of "Can't Reproduce" or "Won't Fix": `resolution in ("Can't Reproduce", "Won't Fix")` * Find work items with a resolution ID of 5: `resolution = 5` * Find work items that don’t have a resolution: resolution = unresolved |

## Resolved

Search for work items that were resolved on, before, or after a particular date (or date range). Note that if a time-component is not specified, midnight will be assumed. Please note that the search results will be relative to your configured time zone (which is by default the Jira server's time zone).

Use one of the following formats:

`"yyyy/MM/dd HH:mm"`  
`"yyyy-MM-dd HH:mm"`  
`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks), `"d"` (days), `"h"` (hours) or `"m"` (minutes) to specify a date relative to the current time. The default is `"m"` (minutes). Be sure to use quote-marks (`"`); if you omit the quote-marks, the number you supply will be interpreted as milliseconds after epoch (1970-1-1).

|  |  |
| --- | --- |
| Syntax | `resolved` |
| Alias | `resolutionDate` |
| Field Type | DATE |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `~ , !~ WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the EQUALS, NOT EQUALS, GREATER THAN, GREATER THAN EQUALS, LESS THAN or LESS THAN EQUALS operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find all work items that were resolved before 31st December 2010: `resolved < "2010/12/31"` * Find all work items that were resolved before 2.00pm on 31st December 2010: `resolved < "2010/12/31 14:00"` * Find all work items that were resolved on or before 31st December 2010: `resolved <= "2011/01/01"` * Find work items that were resolved in January 2011: `resolved > "2011/01/01"` `and resolved < "2011/02/01"` * Find work items that were resolved on 15 January 2011: `resolved > "2011/01/15"` `and resolved < "2011/01/16"` * Find work items that were resolved in the last hour: resolved > -1h |

## SLA

Used in service spaces only.

Search and sort through your requests to ensure that you're hitting your SLA goals. You can search for requests whose SLAs are in a certain state of completion, or that have a certain amount of time on their SLA clock.

|  |  |
| --- | --- |
| Syntax | `Time to resolution`  `Time to first response`  <`your custom SLA name`> |
| Field Type | SLA |
| Auto-complete | No |
| Supported operators | `= , !=, > , >= , < , <=` |
| Unsupported operators | `~ , !~` `IS , IS NOT , IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | * breached() * completed() * elapsed() * everBreached() * paused() * remaining() * running() * withinCalendarHours() |
| Examples | * Find work items where Time to First Response was breached: `"Time to First Response" = everBreached()` * Find work items where the SLA for Time to Resolution is paused due to a condition: `"Time to Resolution" = paused()` * Find work items where the SLA for Time to Resolution is paused due to the SLA calendar: `"Time to Resolution" = withinCalendarHours()` * Find work items that have been waiting for a response for more than 1 hour: `"Time to First Response" > elapsed("1h")` * Find work items that that will breach Time to First Response in the next two hours: `"Time to First Response" < remaining("2h")` |

## Sprint

Search for work items that are assigned to a particular sprint. This works for active sprints and future sprints. The search is based on either the sprint name or the sprint ID (i.e. the number that Jira automatically allocates to a sprint).

If you have multiple sprints with similar (or identical) names, you can simply search by using the sprint name — or even just part of it. The possible matches will be shown in the autocomplete drop-down, with the sprint dates shown to help you distinguish between them. (The sprint ID will also be shown, in brackets).

|  |  |
| --- | --- |
| Syntax | `sprint` |
| Field Type | NUMBER |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT, IN , NOT IN` |
| Unsupported operators | `~ , !~ ,` > , >= , < , <= `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | * openSprints() * closedSprints() |
| Examples | * Find work items that belong to sprint 999: `sprint = 999` * Find work items that belong to sprint "February 1": `sprint = "February 1"` * Find work items that belong to either "February 1", "February 2" or "February 3": `sprint in ("February 1","February 2","February 3")` * Find work items that are assigned to a sprint: `sprint is not empty` |

## Status

Search for work items that have a particular status. You can search by status name or status ID (i.e. the number that Jira automatically allocates to a status).

The WAS, WAS NOT, WAS IN and WAS NOT IN operators can only be used with the name, not the ID.

|  |  |
| --- | --- |
| Syntax | `status` |
| Field Type | STATUS |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT, IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Unsupported operators | `~ , !~ ,` > , >= , < , <= |
| Supported functions | None |
| Examples | * Find work items with a status of "Open": `status = Open` * Find work items with a status ID of 1: `status = 1` * Find work items that currently have, or previously had, a status of "Open": `status WAS Open` |

## Summary

Search for work items where the summary contains specific text using Jira text-search syntax. [More about searching syntax for text fields.](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

|  |  |
| --- | --- |
| Syntax | `summary` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~ , !~`  `IS , IS NOT` |
| Unsupported operators | `= , != ,` > , >= , < , <=  `IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items where the summary contains the words "Error saving file" (a “term search” match): `summary ~ "Error saving file"` * Find work items where the summary contains the exact phrase "Error saving file": `summary ~` `"\"Error saving file\""` * Find work items where the summary contains both the exact phrase "Error saving file" and the exact phrase “Create new version”: `summary ~ "\"Error saving file\"" AND summary ~ "\"Create new version\""` |

## Text

This is a master-field that allows you to search all text fields for work items, such as:

* Summary
* Description
* Environment
* Comments
* custom fields that use the "free text searcher"; this includes custom fields of the following built-in custom field types:

  + Free text field (unlimited text)
  + Text field (< 255 characters)
  + Read-only text field

Search for work items that have certain text present using Jira text-search syntax. [More about searching syntax for text fields.](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

The `text` master-field can only be used with the CONTAINS operator ("`~`").

Some characters and words are reserved and you can’t search for work items using these. [Read about reserved and characters](https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/#Restricted-words-and-characters "https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/#Restricted-words-and-characters").

|  |  |
| --- | --- |
| Syntax | `text` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~` |
| Unsupported operators | `!~, = , != ,` > , >= , < , <=  `IS , IS NOT , IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items where a text field contains the word "Fred": `text ~ "Fred"` or `text ~ Fred` * Find all work items where a text field contains the words "full screen": `text ~ "full screen"` * Find all work items where a text field contains the exact phrase "full screen": `text ~ "\"full screen\""` * Find all work items where text fields contain the exact phrase "full screen" and the exact phrase “minimize screen”: `text ~ "\"full screen\"" AND text ~ "\"minimize screen\""` |

## Text fields

Similar to `text`, this is a master-field that allows you to search in most text fields (except Comments, Worklog) for work items, such as:

* Summary
* Description
* Environment
* custom fields that use the "free text searcher"; this includes custom fields of the following built-in custom field types:

  + Free text field (unlimited text)
  + Text field (< 255 characters)
  + Read-only text field

The `textfields` master-field can only be used with the CONTAINS operator ("`~`").

Some characters and words are reserved and you can’t search for work items using these. [Read about reserved and characters](https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/#Restricted-words-and-characters "https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/#Restricted-words-and-characters").

|  |  |
| --- | --- |
| Syntax | `textfields` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~` |
| Unsupported operators | `!~, = , != ,` > , >= , < , <=  `IS , IS NOT , IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items where a text field contains the word "Fred": `textfields ~ "Fred"` or `textfields ~ Fred` * Find all work items where a text field contains the words "full screen": `textfields ~ "full screen"` * Find all work items where a text field contains the exact phrase "full screen": `textfields ~ "\"full screen\""` * Find all work items where text fields contain the exact phrase "full screen" and the exact phrase “minimize screen”: `textfields ~ "\"full screen\"" AND textfields ~ "\"minimize screen\""` |

## Time spent

Only available if time-tracking has been enabled by your Jira administrator.

Search for work items where the time spent is set to a particular value (i.e. a number, not a date or date range). Use "w", "d", "h" and "m" to specify weeks, days, hours, or minutes.

|  |  |
| --- | --- |
| Syntax | `timeSpent` |
| Field Type | DURATION |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~` `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | Find work items where the time spent is more than 5 days: `timeSpent > 5d` |

## Type

Search for work items that have a particular work type. You can search by work type name or work type ID (i.e. the number that Jira automatically allocates to a work type).

|  |  |
| --- | --- |
| Syntax | `type` |
| Alias | `workType` |
| Field Type | WORK\_TYPE |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~  ,` > , >= , < , <= `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items with a work type of "Bug": `type = Bug` * Find work items with a work type of "Bug" or "Improvement": `workType in (Bug,Improvement)` * Find work items with a work type ID of 2: `workType = 2` |

## Updated

Search for work items that were last updated on, before, or after a particular date (or date range). Note that if a time-component is not specified, midnight will be assumed. Please note that the search results will be relative to your configured time zone (which is by default the Jira server's time zone).

Use one of the following formats:

`"yyyy/MM/dd HH:mm"`  
`"yyyy-MM-dd HH:mm"`  
`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks), `"d"` (days), `"h"` (hours) or `"m"` (minutes) to specify a date relative to the current time. The default is `"m"` (minutes). Be sure to use quote-marks (`"`); if you omit the quote-marks, the number you supply will be interpreted as milliseconds after epoch (1970-1-1).

|  |  |
| --- | --- |
| Syntax | `updated` |
| Alias | `updatedDate` |
| Field Type | DATE |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~` `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **EQUALS**, **NOT EQUALS, GREATER THAN, GREATER THAN EQUALS,**  **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find work items that were last updated before 12th December 2010: `updated < "2010/12/12"` * Find work items that were last updated on or before 12th December 2010: `updated < "2010/12/13"` * Find all work items that were last updated before 2.00pm on 31st December 2010: `updated < "2010/12/31 14:00"` * Find work items that were last updated more than two weeks ago: `updated < "-2w"` * Find work items that were last updated on 15 January 2011: `updated > "2011/01/15" and updated < "2011/01/16"` * Find work items that were last updated in January 2011: `updated > "2011/01/01" and updated < "2011/02/01"` |

## Voter

Search for work items for which a particular user has voted. You can search by the user's full name, ID, or email address. Note that you can only find work items for which you have the "View Voters and Watchers" permission, unless you are searching for your own votes.

|  |  |
| --- | --- |
| Syntax | `voter` |
| Field Type | USER |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <=`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **IN** and **NOT IN** operators, this field supports:   * membersOf()   When used with the **EQUALS** and **NOT EQUALS** operators, this field supports:   * currentUser() |
| Examples | * Search for work items that you have voted for: `voter = currentUser()` * Search for work items that the user "jsmith" has voted for: `voter = "jsmith"` * Search for work items for which a member of the group "jira-administrators" has voted: `voter in membersOf("jira-administrators")` |

## Votes

Search for work items with a specified number of votes.

|  |  |
| --- | --- |
| Syntax | `votes` |
| Field Type | NUMBER |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IN , NOT IN` |
| Unsupported operators | `~ , !~` `IS , IS NOT , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | Find all work items that have 12 or more votes: `votes >= 12` |

## Watcher

Search for work items that a particular user is watching. You can search by the user's full name, ID, or email address. Note that you can only find work items for which you have the "View Voters and Watchers" permission, unless you are searching for work items where you are the watcher.

|  |  |
| --- | --- |
| Syntax | `watcher` |
| Field Type | USER |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <=`  `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **IN** and **NOT IN** operators, this field supports:   * membersOf()   When used with the **EQUALS** and **NOT EQUALS** operators, this field supports:   * currentUser() |
| Examples | * Search for work items that you are watching: `watcher = currentUser()` * Search for work items that the user "jsmith" is watching: `watcher = "jsmith"` * Search for work items that are being watched by a member of the group "jira-administrators": `watcher in membersOf("jira-administrators")` |

## Watchers

Search for work items with a specified number of watchers.

|  |  |
| --- | --- |
| Syntax | `watchers` |
| Field Type | NUMBER |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IN , NOT IN` |
| Unsupported operators | `~ , !~` `IS , IS NOT , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | Find all work items that are being watched by more than 3 people: `watchers > 3` |

## Worklog comment

This field is only available if time tracking has been enabled by your Jira administrator, and can only support the CONTAINS operator ("`~`").

Search for work items that have certain text present in worklog comments using Jira text-search syntax. [More about searching syntax for text fields.](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

|  |  |
| --- | --- |
| Syntax | `worklogComment` |
| Field Type | TEXT |
| Auto-complete | No |
| Supported operators | `~` |
| Unsupported operators | `!~, = , != , > , >= , < , <=`  `IS , IS NOT , IN , NOT IN , WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | * Find work items where a worklog comment contains the word "Fred": `worklogComment ~ "Fred"` * Find all work items where a worklog comment contains the words "full screen": `worklogComment ~ "full screen"` * Find all work items where a worklog comment contains the exact phrase "full screen": `worklogComment ~ "\"full screen\""` * Find all work items where a worklog comment contains both the exact phrase "full screen" and the exact phrase “minimize screen”: `worklogComment ~ "\"full screen\"" AND worklogComment ~ "\"minimize screen\""` |

## Worklog date

Only available if time-tracking has been enabled by your Jira administrator.

Search for work items with work logged on a specific date

|  |  |
| --- | --- |
| Syntax | `worklogDate` |
| Field Type | DATE |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=` `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~` `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | When used with the **EQUALS**, **NOT EQUALS, GREATER THAN, GREATER THAN EQUALS,**  **LESS THAN** or **LESS THAN EQUALS** operators, this field supports:   * currentLogin() * lastLogin() * now() * startOfDay() * startOfWeek() * startOfMonth() * startOfYear() * endOfDay() * endOfWeek() * endOfMonth() * endOfYear() |
| Examples | * Find work items where someone logged work on 12th December 2010: `worklogDate = "2010/12/12"` * Find the work items where someone has logged work in the past week: `worklogDate > startOfWeek()` |

## Work item key

Search for work items with a particular key or ID (i.e. the number that Jira automatically allocates to a work item).

|  |  |
| --- | --- |
| Syntax | `workItemKey` |
| Aliases | `id , workItem , key` |
| Field Type | WORKITEM |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <= , ~ , !~`  `IN, NOT IN` |
| Unsupported operators | `IS, IS NOT, WAS NOT, WAS NOT IN, CHANGED` |
| Supported functions | When used with the **IN**or **NOT IN** operators, `workItemKey` supports:   * workItemHistory() * linkedworkItems() * votedworkItems() * watchedworkItems() |
| Examples | * Find the work item with key "ABC-123": `workItemKey = ABC-123` * Find the work item with the work item number  ”123”: `workItemKey ~ "-123"` * Find work items that contains the key “ABC”: `workItemKey ~ "*ABC*"` * Find work items with a key that ends with “ABC”, and a work item number that starts with “1”: `workItemKey ~ "*ABC-1*"` |

## Work item link

Searches for work items linked or not linked to a work item. You can restrict the search to links of a particular type.

|  |  |
| --- | --- |
| Syntax | `workItemLink`, `workItemLink["link type"]`, or `workItemLinkType`*,* where `link type` or `LinkType` is a variable you replace with the work item link type (*blocks*, *duplicates*, or *is blocked by*, for example). |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <=`  `WAS , WAS IN , WAS NOT , WAS NOT IN , CHANGED , IS , IS NOT` |
| Supported functions | None |
| Examples | Find work items:   * with a link of any type to the work item ABC-123: `workItemLink = ABC-123` * with linked work items but *not* linked to a specific work item: `workItemLink != ABC-123` * linked to at least one of a list of work items: `workItemLink in (ABC-123, ABC-456)` * with linked work items but *not* linked to any of the work items you specify: `workItemLink not in (ABC-123, ABC-456)` * that block the work item ABC-123 (link type is "blocks"): `WorkItemBlocks = ABC-123 or workItemLink["blocks"] = ABC-123` * that are blocked by the work item ABC-123 (link type is "is blocked by"): `workItemIsBlockedBy = ABC-123 or workItemLink["is blocked by"] = ABC-123` |

## Work item link type

Search for work items that have a particular link type, like *blocks* or *is duplicated by*. You can only find work items from the Jira instance you're searching on; remote links to work items on other Jira instances won’t be included.

Use this JQL query to add colors to your work item cards! For example, add a red stripe to work items that have some blockers, and keep all other work items green. This will help you bring the right information to your team’s attention, at a glance. For more info, see [Customizing cards](https://support.atlassian.com/jira-software-cloud/docs/customize-cards/ "https://support.atlassian.com/jira-software-cloud/docs/customize-cards/").

|  |  |
| --- | --- |
| Syntax | `workItemLinkType` |
| Auto-complete | Yes |
| Supported operators | `= , !=`  `IN , NOT IN` |
| Unsupported operators | `~ , !~ , > , >= , < , <=`  `WAS , WAS IN , WAS NOT , WAS NOT IN , CHANGED , IS , IS NOT` |
| Supported functions | None |
| Examples | Find work items:   * with a link type of "causes": `workItemLinkType = causes` * with a link type of "duplicates" or "clones": `workItemLinkType in (duplicates,clones)` * with link types other than “clones”: `workItemLinkType != clones` * that are blocked by other work items, or that don't have any blockers:    + `workItemLinkType = "is blocked by"`   + `workItemLinkType != "is blocked by"` |

Jira work item link types have the following properties:

* **Name:** The title for the link type
* **Outward description:** The description of how a work item **affects** other work items
* **Inward description:** The description of how a work item **is affected by** other work items

For example, a link type could have the following properties:

* **Name:** Problem/Incident
* **Outward description:** causes
* **Inward description:** is caused by

When searching `workItemLinkType`, Jira searches all three properties. This can mean you're unable to isolate work items with a specific inward or outward description if the link type's name and either of the descriptions are the same. This is the case for the default "Blocks" link type, where the name and outward description are "blocks".

If you need to be able to search specifically for work items with an outward description of "blocks", for example, a Jira administrator must change the name of the link type to something else. If you're a Jira admin, take a look at [Configuring work item linking](https://support.atlassian.com/jira-cloud-administration/docs/configure-issue-linking/ "https://support.atlassian.com/jira-cloud-administration/docs/configure-issue-linking/") for more info.

## Work ratio

Only available if time-tracking has been enabled by your Jira administrator.

Search for work items where the work ratio has a particular value. Work ratio is calculated as follows: **workRatio = timeSpent / originalEstimate) x 100**

|  |  |
| --- | --- |
| Syntax | `workRatio` |
| Field Type | NUMBER |
| Auto-complete | No |
| Supported operators | `= , != , > , >= , < , <=`  `IS , IS NOT , IN , NOT IN` |
| Unsupported operators | `~ , !~` `WAS, WAS IN, WAS NOT, WAS NOT IN , CHANGED` |
| Supported functions | None |
| Examples | Find work items on which more than 75% of the original estimate has been spent: `workRatio > 75` |

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
* [JQL functions](/jira-service-management-cloud/docs/jql-functions/)
* [JQL developer status](/jira-service-management-cloud/docs/jql-developer-status/)
* JQL fields
* [JQL keywords](/jira-service-management-cloud/docs/jql-keywords/)
* [JQL operators](/jira-service-management-cloud/docs/jql-operators/)
* Show more

On this page[Affected version](/jira-service-management-cloud/docs/jql-fields/#Affected-version)[Approvals](/jira-service-management-cloud/docs/jql-fields/#Approvals)[Assignee](/jira-service-management-cloud/docs/jql-fields/#Assignee)[Attachments](/jira-service-management-cloud/docs/jql-fields/#Attachments)[Category](/jira-service-management-cloud/docs/jql-fields/#Category)[Change gating type](/jira-service-management-cloud/docs/jql-fields/#Change-gating-type)[Comment](/jira-service-management-cloud/docs/jql-fields/#Comment)[Component](/jira-service-management-cloud/docs/jql-fields/#Component)[Created](/jira-service-management-cloud/docs/jql-fields/#Created)[Creator](/jira-service-management-cloud/docs/jql-fields/#Creator)[Custom field](/jira-service-management-cloud/docs/jql-fields/#Custom-field)[Description](/jira-service-management-cloud/docs/jql-fields/#Description)[Due](/jira-service-management-cloud/docs/jql-fields/#Due)[Environment](/jira-service-management-cloud/docs/jql-fields/#Environment)[Epic link](/jira-service-management-cloud/docs/jql-fields/#Epic-link)[Filter](/jira-service-management-cloud/docs/jql-fields/#Filter)[Fix version](/jira-service-management-cloud/docs/jql-fields/#Fix-version)[Hierarchy level](/jira-service-management-cloud/docs/jql-fields/#Hierarchy-level)[Journey](/jira-service-management-cloud/docs/jql-fields/#Journey)[Journey parent](/jira-service-management-cloud/docs/jql-fields/#Journey-parent)[Journey type](/jira-service-management-cloud/docs/jql-fields/#Journey-type)[Journey type version](/jira-service-management-cloud/docs/jql-fields/#Journey-type-version)[Journey work item](/jira-service-management-cloud/docs/jql-fields/#Journey-work-item)[Labels](/jira-service-management-cloud/docs/jql-fields/#Labels)[Last viewed](/jira-service-management-cloud/docs/jql-fields/#Last-viewed)[Level](/jira-service-management-cloud/docs/jql-fields/#Level)[Organization](/jira-service-management-cloud/docs/jql-fields/#Organization)[Original estimate](/jira-service-management-cloud/docs/jql-fields/#Original-estimate)[Parent](/jira-service-management-cloud/docs/jql-fields/#Parent)[Parent space](/jira-service-management-cloud/docs/jql-fields/#Parent-space)[Priority](/jira-service-management-cloud/docs/jql-fields/#Priority)[Project](/jira-service-management-cloud/docs/jql-fields/#Project)[Project type](/jira-service-management-cloud/docs/jql-fields/#Project-type)[Remaining estimate](/jira-service-management-cloud/docs/jql-fields/#Remaining-estimate)[Reporter](/jira-service-management-cloud/docs/jql-fields/#Reporter)[Request channel type](/jira-service-management-cloud/docs/jql-fields/#Request-channel-type)[Request last activity time](/jira-service-management-cloud/docs/jql-fields/#Request-last-activity-time)[Request type](/jira-service-management-cloud/docs/jql-fields/#Request-type)[Resolution](/jira-service-management-cloud/docs/jql-fields/#Resolution)[Resolved](/jira-service-management-cloud/docs/jql-fields/#Resolved)[SLA](/jira-service-management-cloud/docs/jql-fields/#SLA)[Sprint](/jira-service-management-cloud/docs/jql-fields/#Sprint)[Status](/jira-service-management-cloud/docs/jql-fields/#Status)[Summary](/jira-service-management-cloud/docs/jql-fields/#Summary)[Text](/jira-service-management-cloud/docs/jql-fields/#Text)[Text fields](/jira-service-management-cloud/docs/jql-fields/#Text-fields)[Time spent](/jira-service-management-cloud/docs/jql-fields/#Time-spent)[Type](/jira-service-management-cloud/docs/jql-fields/#Type)[Updated](/jira-service-management-cloud/docs/jql-fields/#Updated)[Voter](/jira-service-management-cloud/docs/jql-fields/#Voter)[Votes](/jira-service-management-cloud/docs/jql-fields/#Votes)[Watcher](/jira-service-management-cloud/docs/jql-fields/#Watcher)[Watchers](/jira-service-management-cloud/docs/jql-fields/#Watchers)[Worklog comment](/jira-service-management-cloud/docs/jql-fields/#Worklog-comment)[Worklog date](/jira-service-management-cloud/docs/jql-fields/#Worklog-date)[Work item key](/jira-service-management-cloud/docs/jql-fields/#Work-item-key)[Work item link](/jira-service-management-cloud/docs/jql-fields/#Work-item-link)[Work item link type](/jira-service-management-cloud/docs/jql-fields/#Work-item-link-type)[Work ratio](/jira-service-management-cloud/docs/jql-fields/#Work-ratio)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
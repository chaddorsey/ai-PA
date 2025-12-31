---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/jql-functions/
title: JQL functions | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:43.289419
---

# JQL functions

We're updating terminology in Jira, moving from "issue" to "work item", and "project" to "space".

As we roll out these changes, some JQL entries using the new terms may not work yet. If you come across this, try using the old term instead.

**There are no changes to existing JQL queries.**

This page describes information about functions that are used for advanced searching. Additional JQL functions may also be available through installed apps.

A function in JQL appears as a word followed by parentheses, which may contain one or more explicit values or Jira fields. In a clause, a function is preceded by an [operator](https://support.atlassian.com/jira-software-cloud/docs/jql-operators/ "https://support.atlassian.com/jira-software-cloud/docs/jql-operators/"), which in turn is preceded by a [field](https://support.atlassian.com/jira-software-cloud/docs/jql-fields/ "https://support.atlassian.com/jira-software-cloud/docs/jql-fields/"). A function performs a calculation on either specific Jira data or the function's content in parentheses, such that only true results are retrieved by the function, and then again by the clause in which the function is used.

Unless specified in the search query, note that JQL searches do not return empty fields in results. To include empty fields (e.g. unassigned work items) when searching for work items that are not assigned to the current user, you would enter (assignee != currentUser() OR assignee is EMPTY) to include unassigned work items in the list of results.

## approved()

Only applicable for sites with Jira Service Management subscriptions.

Search for all requests that have an approval with a final decision of **approved**.

|  |  |
| --- | --- |
| Syntax | `approved()` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` |
| Unsupported operators | `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests that have been approved: `approvals = approved()` |

## approver()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests where any specified user is an approver for a pending or completed approval step, and may or may not have already approved or declined the approval. You must specify a username.

|  |  |
| --- | --- |
| Syntax | `approver(user1, user2)` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` |
| Unsupported operators | `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find requests that require or required approval by John Smith: `approvals = approver(jsmith)` * Find requests that require or required approval by John Smith or Sarah Khan:  `approvals = approver(jsmith, skhan)` |

## breached()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items that whose most recent SLA has missed its goal.

|  |  |
| --- | --- |
| Syntax | `breached()` |
| Supported fields | **SLA** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `!~` , `>`, `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` , `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items where an SLA (“Time to First Response**”**) was breached: `"Time to First Response" = breached()` |

## cascadeOption()

Search for work items that match the selected values of a **Cascading Select** custom field.

The `parentOption` parameter matches against the first tier of options in the cascading select field.

The `childOption` parameter matches against the second tier of options in the cascading select field, and is optional.

The keyword `none` can be used to search for work items where either or both of the options have no value.

|  |  |
| --- | --- |
| Syntax | `cascadeOption(parentOption) cascadeOption(parentOption,childOption)` |
| Supported fields | Custom fields of type **Cascading Select** |
| Supported operators | `IN , NOT IN` |
| Unsupported operators | `= , != , ~ , !~ , > , >= , < , <= IS , IS NOT, WAS , WAS IN , WAS NOT , WAS NOT IN , CHANGED` |
| Examples | * Find work items where a custom field ("Location") has the value "USA" for the first tier and "New York" for the second tier: `location in cascadeOption("USA", "New York")` * Find work items where a custom field ("Location") has the value "USA" for the first tier and any value (or no value) for the second tier: `location in cascadeOption("USA")` * Find work items where a custom field ("Location") has the value "USA" for the first tier and no value for the second tier: `location in cascadeOption("USA", none)` * Find work items where a custom field ("Location") has no value for the first tier and no value for the second tier: `location in cascadeOption(none)` * Find work items where a custom field ("Referrer") has the value "none" for the first tier and "none" for the second tier: `referrer in cascadeOption("\"none\"", "\"none\"")` * Find work items where a custom field ("Referrer") has the value "none" for the first tier and no value for the second tier: `referrer in cascadeOption("\"none\"", none)` |

## choiceOption()

Search for work items that match the selected IDs of a **Multiple Choice** or **Dropdown** custom field.

Requires at least one argument. For multiple arguments, returns the ID of each one. Arguments must be valid option values. In cases where the argument could be both an ID and the option value, returns work items where the option value matches.

|  |  |
| --- | --- |
| Syntax | `choiceOption(ValueOption) choiceOption(ValueOption1,ValueOption2,ValueOption3)` |
| Supported fields | Custom fields of types **Multiple Choice** and **Dropdown** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items where a custom field ("Product Version") has the value  ”123”: `"Product Version[Select List (multiple choices)]" in choiceOption(123)` |

## closedSprints()

Search for work items that are assigned to a completed Sprint.

It is possible for a work item to belong to both a completed Sprint(s) and an incomplete Sprint(s). See also [openSprints](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-functions/#Advancedsearchingfunctionsreference-openSprints "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-functions/#Advancedsearchingfunctionsreference-openSprints")().

|  |  |
| --- | --- |
| Syntax | `closedSprints()` |
| Supported fields | **Sprint** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all work items that are assigned to a completed sprint: `sprint in closedSprints()` |

## completed()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items where the SLA cycle is complete, meaning the work item has reached one of their stop events.

|  |  |
| --- | --- |
| Syntax | `completed()` |
| Supported fields | **SLA** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `!~` , `>`, `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items where an SLA (“Time to First Response”) has completed the cycle: `"Time to First Response" = completed()` |

## componentsLeadByUser()

Find work items in components that are led by a specific user. You can optionally specify a user, or if the user is omitted, the current user (i.e. you) will be used.

If you are not logged in to Jira, a user must be specified.

|  |  |
| --- | --- |
| Syntax | `componentsLeadByUser() componentsLeadByUser(username)` |
| Supported fields | **Component** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find open work items in components that are led by you: `component in componentsLeadByUser() AND status = Open` * Find open work items in components that are led by Bill: `component in componentsLeadByUser(bill) AND status = Open` |

## currentLogin()

Perform searches based on the time at which the current user's session began. See also [lastLogin()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#lastLogin-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#lastLogin--").

|  |  |
| --- | --- |
| Syntax | `currentLogin()` |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS`\* , `WAS IN`\* , `WAS NOT`\* , `WAS NOT IN`\*, `CHANGED`\*  \* Only in predicate |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items that have been created during your current session: `created > currentLogin()` |

## currentUser()

Perform searches based on the currently logged-in user.

This function can only be used by logged-in users. So if you are creating a saved filter that you expect to be used by anonymous users, do not use this function.

|  |  |
| --- | --- |
| Syntax | `currentUser()` |
| Supported fields | **Assignee**, **Reporter**, **Voter**, **Watcher**, **Creator**, custom fields of type **User** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items that are assigned to you: `assignee = currentUser()` * Find work items that were reported by you but are not assigned to you: `reporter = currentUser() AND assignee != currentUser()` |

## customerDetail()

Perform searches based on the customers details.

To use this JQL function, turn on **Customer service management** on the **Features** page in **Space** **settings**.

This function will return up to 32000 customers.

|  |  |
| --- | --- |
| Syntax | `customerDetail()` |
| Supported fields | **Assignee**, **Reporter**, **Voter**, **Watcher**, custom fields of type **User** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` ,  `WAS NOT IN` , `WAS NOT` , `CHANGED` |
| Examples | * Find all requests reported by customers in the APAC region: `reporter in customerDetail("Region", "APAC")` * Find all requests reported by customers who are not technical contacts: `reporter not in customerDetail("Role", "Technical Contact")` |

## earliestUnreleasedVersion()

Perform searches based on the earliest unreleased version in a space. See also [unreleasedVersions()](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-functions/#Advancedsearchingfunctionsreference-unreleasedVersions "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-functions/#Advancedsearchingfunctionsreference-unreleasedVersions").

Version order is determined by the order versions are placed in on the **Releases** page in the space. The version at the bottom of the list is considered the "earliest." To change the order of versions, drag and drop them to a new place in the list.

|  |  |
| --- | --- |
| Syntax | `earliestUnreleasedVersion(space)` |
| Supported fields | **AffectedVersion**, **FixVersion**, custom fields of type **Version** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items whose fix version is the earliest unreleased version of the “ABC” space: `fixVersion = earliestUnreleasedVersion(ABC)` * Find work items that relate to the earliest unreleased version of the “ABC” space: `affectedVersion = earliestUnreleasedVersion(ABC) or fixVersion = earliestUnreleasedVersion(ABC)` |

## endOfDay()

Perform searches based on the end of the current day.

See also [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--"), [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--"), [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), and [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--").

|  |  |
| --- | --- |
| Syntax | `endOfDay() endOfDay("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `endOfDay("+1")` is the same as `endOfDay("+1d")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items due by the end of today: `due < endOfDay()` * Find work items due by the end of tomorrow: `due < endOfDay("+1")` |

## endOfMonth()

Perform searches based on the end of the current month.

See also [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--"), [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), and [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--").

|  |  |
| --- | --- |
| Syntax | `endOfMonth() endOfMonth("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `endOfMonth("+1")` is the same as `endOfMonth("+1M")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items due by the end of this month: `due < endOfMonth()` * Find work items due by the end of next month: `due < endOfMonth("+1")` * Find work items due by the 15th of next month: `due < endOfMonth("+15d")` |

## endOfWeek()

Search for work items that are due by the end of the last day of the current week. By default, this function considers Saturday to be the last day of the week. You can use a different day (for example, Sunday) as the end of the week. See the syntax in the examples mentioned below.

See also [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--"), [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--"), [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), and [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--").

|  |  |
| --- | --- |
| Syntax | `endOfWeek() endOfWeek("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `endOfWeek("+1")` is the same as `endOfWeek("+1w")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items due by the last day of the end of this week (by default, the last day is Saturday): `due < endOfWeek()` * Find work items due by the end of this week (last day as Sunday): `due < endOfWeek("+1d")` * Find work items due by the end of next week: `due < endOfWeek("+1")` |

## endOfYear()

Perform searches based on the end of the current year.

See also [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--"), [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), and [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--").

|  |  |
| --- | --- |
| Syntax | `endOfYear() endOfYear("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `endOfYear("+1")` is the same as `endOfYear("+1y")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items due by the end of this year: `due < endOfYear()` * Find work items due by the end of March next year: `due < endOfYear("+3M")` |

## entitlementDetail()

Only applicable for sites with Jira Service Management subscriptions.

Perform searches based on the entitlement’s details.

To use this JQL function, turn on **Customer service management** and **Products and entitlements** on the **Features** page in **Space** **settings**.

This function will return up to 32,000 entitlements.

|  |  |
| --- | --- |
| Syntax | `entitlementDetail("Field Name", "Field Value")` |
| Supported fields | **Entitlement** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all work items related to an entitlement where the “Support Level” is “Gold”: `entitlement in entitlementDetail("Support Level", "Gold")` |

## entitlementProduct()

Only applicable for sites with Jira Service Management subscriptions.

Perform searches based on a product.

To use this JQL function, turn on **Customer service management** and **Products and entitlements** on the **Features** page in **Space** **settings**.

|  |  |
| --- | --- |
| Syntax | `entitlementProduct("Product Name")` |
| Supported fields | **Entitlement** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all work items related to entitlements for the product “Acme Widget”: `entitlement in entitlementProduct("Acme Widget")` |

## everBreached()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items that have missed one of their SLA goals.

|  |  |
| --- | --- |
| Syntax | `everBreached()` |
| Supported fields | **SLA** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items have missed their goal for Time to First Response: `"Time to First Response" = everBreached()` |

## futureSprints()

Search for work items that are assigned to a sprint that hasn't been started yet.

It is possible for work items to belong to both a completed sprint(s) and an incomplete sprint(s).

|  |  |
| --- | --- |
| Syntax | `futureSprints()` |
| Supported fields | **Sprint** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all work items that are assigned to a sprint that hasn't been started yet: `sprint in futureSprints()` |

## workItemHistory()

Find work items that you have recently viewed, i.e. work items that are in the 'Recent work' section of the 'Work items' dropdown menu.

* `workItemHistory()` returns up to 50 work items, whereas the 'Recent work' dropdown returns only 5.

* If you are not logged in to Jira, only work items from your current browser session will be included.

|  |  |
| --- | --- |
| Syntax | `workItemHistory()` |
| Supported fields | **Work item** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items which you have recently viewed, that are assigned to you: `work item in workItemHistory() AND assignee = currentUser()` |

## workItemsWithRemoteLinksByGlobalId()

Perform searches based on work items that are associated with remote links that have any of the specified global IDs.

This function accepts 1 to 100 globalIds. Specifying 0 or more than 100 globalIds will result in errors.

|  |  |
| --- | --- |
| Syntax | `workItemsWithRemoteLinksByGlobalId(globalId)` |
| Supported fields | **Work item** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items that are linked to remote links that have global ID "abc": `work item in workItemsWithRemoteLinksByGlobalId(abc)` * Find work items that are linked to remote links that have either global ID "abc" or "def": `work item in workItemsWithRemoteLinksByGlobalId(abc, def)` |

## lastLogin()

Perform searches based on the time at which the current user's previous session began. See also [currentLogin()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#currentLogin-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#currentLogin--").

|  |  |
| --- | --- |
| Syntax | `lastLogin()` |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS`\* , `WAS IN`\* , `WAS NOT`\* , `WAS NOT IN`\*, `CHANGED`\*  \* Only in predicate |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items that have been created during your last session: `created > lastLogin()` |

## latestReleasedVersion()

Perform searches based on the latest released version (i.e. the most recent version that has been released) of a specified space. See also [releasedVersions()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#releasedVersions-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#releasedVersions--").

The "latest" is determined by the ordering assigned to the versions, not by actual Version Due Dates.

|  |  |
| --- | --- |
| Syntax | `latestReleasedVersion(space)` |
| Supported fields | **AffectedVersion**, **FixVersion**, custom fields of type **Version** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items whose fix version is the latest released version of the “ABC” space: `fixVersion = latestReleasedVersion(ABC)` * Find work items that relate to the latest released version of the “ABC” space: `affectedVersion = latestReleasedVersion(ABC) or fixVersion = latestReleasedVersion(ABC)` |

## linkedWorkItem

Searches for epics and subtasks. If the work item is not an epic, the search returns all subtasks for the work item.

Only applicable for company-managed spaces.

|  |  |
| --- | --- |
| Syntax | `linkedWorkItem = workItemKey` |
| Supported fields | **Work item** |
| Supported operators | `=` , `!=` , `IN` , `NOT IN` |
| Unsupported operators | `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find subtasks that are linked to a particular epic: `linkedWorkItem = epicKey-123` |

## linkedWorkItems()

Searches for work items that are linked to a work item. You can restrict the search to links of a particular type.

|  |  |
| --- | --- |
| Syntax | `linkedWorkItems(workItemKey) linkedWorkItems(workItemKey,CaseSensitiveLinkType) linkedWorkItems(workItemKey,CaseSensitiveLinkType, CaseSensitiveLinkType)` |
| Supported fields | **Work item** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items that are linked to a particular work item: `work item in linkedWorkItems(ABC-123)` * Find work items that are linked to a particular work item via a particular type of link: `work item in linkedWorkItems(ABC-123,"is duplicated by")` * Find work items that are linked to a particular work item via any type of link specified:  `work item in linkedWorkItems(ABC-123, "is duplicated by", "is blocked by")` |

## membersOf()

Perform searches based on the members of a particular group.

|  |  |
| --- | --- |
| Syntax | `membersOf(Group)` |
| Supported fields | **Assignee**, **Reporter**, **Voter**, **Watcher**, **Creator**, custom fields of type **User** |
| Supported operators | `IN` , `NOT IN` , `WAS IN` , `WAS NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS NOT` , `CHANGED` |
| Examples | * Find work items where the assignee is a member of the group  "jira-administrators": `assignee in membersOf("jira-administrators")` * Search through multiple groups and a specific user: `reporter in membersOf("jira-administators") or reporter in membersOf("jira-work-management-users") or reporter=jsmith` * Search for a particular group, but exclude a particular member or members: `assignee in membersOf(QA) and assignee not in ("John Smith","Jill Jones")` * Exclude members of a particular group: `assignee not in membersOf(QA)` |

## myApproval()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests where the current user is the approver for a pending or completed approval step, and may or may not have already approved or declined the request.

|  |  |
| --- | --- |
| Syntax | `myApproval()` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` |
| Unsupported operators | `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests that require your approval: `approval = myApproval()` |

## myPendingApproval()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests where the current user is the approver for a pending approval step and is yet to approve or decline the approval.

|  |  |
| --- | --- |
| Syntax | `myPendingApproval()` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` |
| Unsupported operators | `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests that currently require your approval: `approvals = myPendingApproval()` |

## myPending()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests where the current user is the approver for a pending approval step, and may or may not have already approved or declined the approval.

|  |  |
| --- | --- |
| Syntax | `myPending()` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` |
| Unsupported operators | `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `IN` , `NOT IN` , `WAS` ,  `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests that currently or previously required your approval `approvals = myPending()` |

## now()

Perform searches based on the current time.

|  |  |
| --- | --- |
| Syntax | `now()` |
| Supported fields | **Created**, **Due**, **Resolved**, **Updated**, custom fields of type **Date/Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS`\* , `WAS IN`\* , `WAS NOT`\* , `WAS NOT IN`\*, `CHANGED`\*  \* Only in predicate |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find work items that are overdue: `duedate < now() and status not in (closed, resolved)` |

## openSprints()

Search for work items that are assigned to a sprint that was started, but has not yet been completed.

It is possible for a work item to belong to both a completed sprint(s) and an incomplete sprint(s). See also [closedSprints()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#openSprints-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#openSprints--").

|  |  |
| --- | --- |
| Syntax | `openSprints()` |
| Supported fields | **Sprint** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all work items that are assigned to a sprint that has not yet been completed: `sprint in openSprints()` |

## organizationDetail()

Perform searches based on the organization details.

### In Customer Service Management

This function will return up to 32,000 organizations.

|  |  |
| --- | --- |
| Syntax | `organizationDetail("Field Name", "Field Value")` |
| Supported fields | **Organization** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests shared with organizations in the APAC region: `organization in organizationDetail("Region", "APAC")` * Find all requests shared with organizations that are not in a platinum support level `organization not in organizationDetail("Support level", "Platinum")` * Find all unresolved requests shared with organizations that joined on 2023-08-24 where the date is in `YYYY-MM-DD` format: `resolution = Unresolved AND Organization in organizationDetail("Joined on", "2023-08-24")` * Consider a multi-select dropdown that can contain up to two values (`option1` and `option2`). To create a query for all the organizations where both values are present:  `resolution = Unresolved AND Organization in organizationDetail("Options", "option1") AND Organization in organizationDetail("Options", "option2")` |

### In Jira Service Management

This function will return up to 32,000 organizations.

|  |  |
| --- | --- |
| Syntax | `organizationDetail("Field Name", "Field Value")` |
| Supported fields | **Organizations** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests shared with organizations in the APAC region: `organizations in organizationDetail("Region", "APAC")` * Find all requests shared with organizations that are not in a platinum support level `organizations not in organizationDetail("Support level", "Platinum")` * Find all unresolved requests shared with organizations that joined on 2023-08-24 where the date is in `YYYY-MM-DD` format: `resolution = Unresolved AND Organizations in organizationDetail("Joined on", "2023-08-24")` * Consider a multi-select dropdown that can contain up to two values (`option1` and `option2`). To create a query for all the organizations where both values are present:  `resolution = Unresolved AND Organizations in organizationDetail("Options", "option1") AND Organizations in organizationDetail("Options", "option2")` |

## organizationMembers()

Only applicable for sites with Jira Service Management subscriptions.

Search for all requests sent by the members of an organization. Returns requests that the members have shared with or kept private from that organization, and with any other organizations they're a member of.

|  |  |
| --- | --- |
| Syntax | `organizationMembers()` |
| Supported fields | **Assignee**, **Reporter**, **Voter**, **Watcher**, custom fields of type **User** |
| Supported operators | `IN` , `NOT IN` , `WAS IN` , `WAS NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS NOT` , `CHANGED` |
| Examples | * Find all requests sent by members of the “Atlassian” organization: `reporter in organizationMembers("Atlassian")` * Find all requests sent by people who are not in the “Atlassian” or “ACME” organizations: `reporter not in organizationMembers("Atlassian","ACME")` |

## parentEpic

Only applicable for company-managed spaces.

Search for work items and subtasks that are linked to an epic.

|  |  |
| --- | --- |
| Syntax | `parentEpic = workItemkey` |
| Supported fields | **Work item** |
| Supported operators | `=` , `!=` , `IN` , `NOT IN` |
| Unsupported operators | `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN`, `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items and sub-tasks in the epic DEMO-123: parentEpic = DEMO 123 * Find work items and sub-tasks the epic DEMO-1 or SAMPLE-4: parentEpic in (DEMO-1, SAMPLE-4) |

## paused()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items that have an SLA that is paused due to a condition.

To find work items that are paused because they are outside calendar hours, use [withinCalendarHours()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#withinCalendarHours-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#withinCalendarHours--").

|  |  |
| --- | --- |
| Syntax | `paused()` |
| Supported fields | **SLA** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items where Time to First Response is paused: `"Time to First Response" = paused()` |

## pending()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests with a pending approval step.

|  |  |
| --- | --- |
| Syntax | `pending()` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find all requests that are awaiting approval: `approvals = pending()` |

## pendingApprovalBy()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests where any specified user is the approver for a pending approval step and is yet to approve or decline the approval. You must specify a username.

|  |  |
| --- | --- |
| Syntax | `pendingApprovalBy(user1, user2)` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find request |

## pendingBy()

Only applicable for sites with Jira Service Management subscriptions.

Search for requests where any specified user is an approver for a pending approval step, and may or may not have already approved or declined the request. You must specify a username.

|  |  |
| --- | --- |
| Syntax | `pendingBy(user1, user2)` |
| Supported fields | Custom fields of type **Approval** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find requests that require approval by John Smith: `approvals = pendingBy(jsmith)` * Find requests that require approval by John Smith or Sarah Khan: `approvals = pendingBy(jsmith, skhan)` |

## spacesLeadByUser()

Find work items in spaces that are led by a specific user. You can optionally specify a user, or if the user is omitted, the current user will be used.

Note that if you are not logged in to Jira, a user must be specified.

|  |  |
| --- | --- |
| Syntax | `spacesLeadByUser() spacesLeadByUser(username)` |
| Supported fields | **Space** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find open work items in spaces that are led by you: `space in spacesLeadByUser() AND status = Open` * Find open work items in spaces that are led by Bill: `space in pspacesLeadByUser(bill) AND status = Open` |

## spacesWhereUserHasPermission()

Find work items in spaces where you have a specific permission. Note, this function operates at the space level. This means that if a permission (e.g. "Edit work items") is granted to the reporter of work items in a space, then you may see some work items returned where you are not the reporter, and therefore don't have the permission specified.

This function is only available if you are logged in to Jira.

|  |  |
| --- | --- |
| Syntax | `spacesWhereUserHasPermission(permission)`  For the `permission` parameter, you can specify any of the permissions described on [permissions for company-manage spaces](https://support.atlassian.com/jira-cloud-administration/docs/permissions-for-company-managed-projects/ "https://support.atlassian.com/jira-cloud-administration/docs/permissions-for-company-managed-projects/"). |
| Supported fields | **Space** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find open work items in spaces where you have the "Resolve work items" permission: `space in spacesWhereUserHasPermission("Resolve work items") AND status = Open` |

## spacesWhereUserHasRole()

Find work items in spaces where you have a specific role.

This function is only available if you are logged in to Jira.

|  |  |
| --- | --- |
| Syntax | `spacesWhereUserHasRole(rolename)` |
| Supported fields | **Space** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find open work items in spaces where you have the "Developers" role: `space in spacesWhereUserHasRole("Developers") AND status = Open` |

## releasedVersions()

Perform searches based on the released versions (i.e. versions that your Jira administrator has released) of a specified space. You can also search on the released versions of all spaces, by omitting the `project` parameter. See also [latestReleasedVersion()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#latestReleasedVersion-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#latestReleasedVersion--").

|  |  |
| --- | --- |
| Syntax | `releasedVersions() releasedVersions(project)` |
| Supported fields | **AffectedVersion**, **FixVersion**, custom fields of type **Version** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` ,  `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items whose fix version is a released version of the ABC space: `fixVersion in releasedVersions(ABC)` * Find work items that relate to released versions of the ABC space: `(affectedVersion in releasedVersions(ABC)) or (fixVersion in releasedVersions(ABC))` |

## remaining()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items whose SLA clock is at a certain point relative to the goal.

|  |  |
| --- | --- |
| Syntax | `remaining()` |
| Supported fields | **SLA** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items that will breach Time to Resolution in the next two hours: `"Time to Resolution" < remaining("2h")` |

## running()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items that have an SLA that is running, regardless of the calendar.

To find work items that are running based on calendar hours, use [withinCalendarHours()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#withinCalendarHours-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#withinCalendarHours--").

|  |  |
| --- | --- |
| Syntax | `running()` |
| Supported fields | **SLA** |
| Supported operators | `=` , `!=` |
| Unsupported operators | `~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items where Time to First Response is running: `"Time to First Response" = running()` |

## standardWorkTypes()

Perform searches based on "standard" work types, that is, search for work items that are not subtasks. See also [subtaskWorkTypes()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#subtaskIssueTypes-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#subtaskIssueTypes--").

|  |  |
| --- | --- |
| Syntax | `standardWorkTypes()` |
| Supported fields | **Type** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT`, `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items that are not subtasks (i.e. work items whose work type is a standard work type, not a subtask work type): `workType in standardWorkTypes()` |

## startOfDay()

Perform searches based on the start of the current day.

See also [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--"), [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--") and [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--").

|  |  |
| --- | --- |
| Syntax | `startOfDay() startOfDay("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `startOfDay("+1")` is the same as `startOfDay("+1d")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created, Due, Resolved, Updated,** custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find new work items created since the start of today: `created > startOfDay()` * Find new work items created since the start of yesterday: `created > startOfDay("-1")` * Find new work items created in the last three days: `created > startOfDay("-3d")` |

## startOfMonth()

Perform searches based on the start of the current month.

See also [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--") [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--"), [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--") and [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--").

|  |  |
| --- | --- |
| Syntax | `startOfMonth() startOfMonth("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `startOfMonth("+1")` is the same as `startOfMonth("+1M")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created, Due, Resolved, Updated,** custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find new work items created since the start of this month: `created > startOfMonth()` * Find new work items created since the start of last month: `created > startOfMonth("-1")` * Find new work items created since the 15th of this month: `created > startOfMonth("+14d")` |

## startOfWeek()

Search for new work items created since the start of the first day of the current week. By default, this function considers Sunday to be the first day of the week when ISO8601 for the Date Picker is disabled in Look and feel settings. You can use a different day (for example, Monday) as the start of the week.

See also [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), [startOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfYear--"), [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--") and [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--").

|  |  |
| --- | --- |
| Syntax | `startOfWeek() startOfWeek("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `startOfWeek("+1")` is the same as `startOfWeek("+1w")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created, Due, Resolved, Updated,** custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find new work items since the first day of the start of this week (by default, the first day is Sunday): `created > startOfWeek()` * Find new work items since the first day of the start of this week (first day as Monday): `created > startOfWeek("+1d")` * Find new work items since the start of last week: `created > startOfWeek("-1")` |

## startOfYear()

Perform searches based on the start of the current year.

See also [startOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfDay--"), [startOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfWeek--"), [startOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#startOfMonth--"), [endOfDay()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfDay--"), [endOfWeek()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfWeek--"), [endOfMonth()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfMonth--") and [endOfYear()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#endOfYear--").

|  |  |
| --- | --- |
| Syntax | `startOfYear() startOfYear("inc")`  where`inc` is an optional increment of `(+/-)nn(y|M|w|d|h|m)`. If the time unit qualifier is omitted, it defaults to the natural period of the function, e.g. `startOfYear("+1")` is the same as `startOfYear("+1y")`. If the plus/minus `(+/-)` sign is omitted, plus `(+)` is assumed. |
| Supported fields | **Created, Due, Resolved, Updated,** custom fields of type **Date**/**Time** |
| Supported operators | `=` , `!=` , `>` , `>=` , `<` , `<=` , `WAS` , `WAS IN` , `WAS NOT` , `WAS NOT IN` , `CHANGED` |
| Unsupported operators | `~` , `!~` , `IS` , `IS NOT` , `IN` , `NOT IN` |
| Examples | * Find new work items since the start of this year: `created > startOfYear()` * Find new work items since the start of last year: `created > startOfYear("-1")` |

## subtaskWorkTypes()

Perform searches based on work items that are sub-tasks. See also [standardWorkTypes()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#standardIssueTypes-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#standardIssueTypes--").

|  |  |
| --- | --- |
| Syntax | `subtaskWorkTypes()` |
| Supported fields | **Type** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT IN` ,  `WAS NOT` , `CHANGED` |
| Examples | * Find work items that are subtasks (i.e. work items whose work type is a subtask work type): `workType in subtaskWorkTypes()` |

## unreleasedVersions()

Perform searches based on the unreleased versions (i.e. versions that your Jira administrator has not yet released) of a specified space. You can also search on the unreleased versions of all spaces, by omitting the `project` parameter. See also [earliestUnreleasedVersion()](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#earliestUnreleasedVersion-- "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/#earliestUnreleasedVersion--").

|  |  |
| --- | --- |
| Syntax | `unreleasedVersions() unreleasedVersions(project)` |
| Supported fields | **AffectedVersion, FixVersion,** custom fields of type **Version** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` ,  `IS NOT` , `WAS` , `WAS IN` , `WAS NOT IN` ,  `WAS NOT` , `CHANGED` |
| Examples | * Find work items whose fix version is an unreleased version of the “ABC” space: `fixVersion in unreleasedVersions(ABC)` * Find work items that relate to unreleased versions of the “ABC” space: `affectedVersion in unreleasedVersions(ABC)` |

## updatedBy()

Search for work items that were updated by a specific user, optionally within the specified time range. An update, in this case, includes creating a work item, updating any of the work item’s fields, creating or deleting a comment, or editing a comment (only the last edit).

For the time range, use one of the following formats:

`"yyyy/MM/dd"`  
`"yyyy-MM-dd"`

Or use `"w"` (weeks), or `"d"` (days) to specify a date relative to the current time. Unlike some other functions, `updatedBy` doesn't support values smaller than a day, and will always round them up to 1 day.

|  |  |
| --- | --- |
| Syntax | `updatedBy(user) updatedBy(user, dateFrom) updatedBy(user, dateFrom, dateTo)` |
| Supported fields | **Work item** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT IN` , `WAS NOT` , `CHANGED` |
| Examples | * Find work items that were updated by John Smith: `workItemKey in updatedBy(jsmith)` * Find work items that were updated by John Smith within the last 8 days: `workItemKey in updatedBy(jsmith, "-8d")` * Find work items updated between June and September 2018: `workItemkey in updatedBy(jsmith, "2018/06/01", "2018/08/31")` * If you try to find work items updated in the last hour, like in the following example, the time will be rounded up to 1 day, as smaller values aren't supported: `workItemkey in updatedBy(jsmith, "-1h")` |

## votedWorkItems()

Perform searches based on work itemss for which you have voted. Also, see the Voter field. Note, this function can only be used by logged-in users.

This function will return up to 32,000 work item IDs.

|  |  |
| --- | --- |
| Syntax | `votedWorkItems()` |
| Supported fields | **Work item** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` , `IS NOT` , `WAS` , `WAS IN` , `WAS NOT IN` , `WAS NOT` , `CHANGED` |
| Examples | * Find work items that you have voted for: `work item in votedWorkItems()` |

## watchedWorkItems()

Perform searches based on work items that you are watching. Also, see the Watcher field. Note that this function can only be used by logged-in users.

This function will return up to 32,000 work item IDs.

|  |  |
| --- | --- |
| Syntax | `watchedWorkItems()` |
| Supported fields | **Work item** |
| Supported operators | `IN` , `NOT IN` |
| Unsupported operators | `=` , `!=` , `~` , `!~` , `>` , `>=` , `<` , `<=` , `IS` ,  `IS NOT` , `WAS` , `WAS IN` , `WAS NOT` ,  `WAS NOT IN` , `CHANGED` |
| Examples | * Find work items that you are watching: `work item in watchedWorkItems()` |

## withinCalendarHours()

Only applicable for sites with Jira Service Management subscriptions.

Returns work items that have an SLA that is running according to the SLA calendar.

For example, say your space has two SLAs that count Time to First Response. Some work items with this SLA use a 9am-1pm calendar, and others use a 9am-5pm calendar. If an agent starts work at 3pm, they probably want to work on work items from the 9am-5pm agreement first. They can use `withinCalendarHours()` to find all the work items where Time to First Response is running at 3pm.

|  |  |
| --- | --- |
| Syntax | `withinCalendarHours()` |
| Supported fields | **SLA** |
| Supported operators | `=`,`!=` |
| Unsupported operators | `~` **,** `!~` ,`>` **,** `>=` **,** `<` **,** `<=` **,** `IS` **,** `IS NOT` **,** `WAS` **,**  `WAS IN` **,** `WAS NOT` **,**`WAS NOT IN` **,** `CHANGED` |
| Examples | * Find work items where an SLA (“Time to First Response”) is within calendar hours: `"Time to First Response" = withinCalendarHours()` |

Was this helpful?

Yes

No

It wasn't accurateIt wasn't clearIt wasn't relevant

Provide feedback about this article

## Still need help?

The Atlassian Community is here for you.

[Ask the Community](https://community.atlassian.com/t5/custom/page/page-id/create-post-step-1?add-tags=jira-service-management,Cloud)

* [Use advanced search with Jira Query Language (JQL)](/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
* [What is advanced search in Jira Cloud?](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/)
* JQL functions
* [JQL developer status](/jira-service-management-cloud/docs/jql-developer-status/)
* [JQL fields](/jira-service-management-cloud/docs/jql-fields/)
* [JQL keywords](/jira-service-management-cloud/docs/jql-keywords/)
* Show more

On this page[approved()](/jira-service-management-cloud/docs/jql-functions/#approved--)[approver()](/jira-service-management-cloud/docs/jql-functions/#approver--)[breached()](/jira-service-management-cloud/docs/jql-functions/#breached--)[cascadeOption()](/jira-service-management-cloud/docs/jql-functions/#cascadeOption--)[choiceOption()](/jira-service-management-cloud/docs/jql-functions/#choiceOption--)[closedSprints()](/jira-service-management-cloud/docs/jql-functions/#closedSprints--)[completed()](/jira-service-management-cloud/docs/jql-functions/#completed--)[componentsLeadByUser()](/jira-service-management-cloud/docs/jql-functions/#componentsLeadByUser--)[currentLogin()](/jira-service-management-cloud/docs/jql-functions/#currentLogin--)[currentUser()](/jira-service-management-cloud/docs/jql-functions/#currentUser--)[customerDetail()](/jira-service-management-cloud/docs/jql-functions/#customerDetail--)[earliestUnreleasedVersion()](/jira-service-management-cloud/docs/jql-functions/#earliestUnreleasedVersion--)[endOfDay()](/jira-service-management-cloud/docs/jql-functions/#endOfDay--)[endOfMonth()](/jira-service-management-cloud/docs/jql-functions/#endOfMonth--)[endOfWeek()](/jira-service-management-cloud/docs/jql-functions/#endOfWeek--)[endOfYear()](/jira-service-management-cloud/docs/jql-functions/#endOfYear--)[entitlementDetail()](/jira-service-management-cloud/docs/jql-functions/#entitlementDetail--)[entitlementProduct()](/jira-service-management-cloud/docs/jql-functions/#entitlementProduct--)[everBreached()](/jira-service-management-cloud/docs/jql-functions/#everBreached--)[futureSprints()](/jira-service-management-cloud/docs/jql-functions/#futureSprints--)[workItemHistory()](/jira-service-management-cloud/docs/jql-functions/#workItemHistory--)[workItemsWithRemoteLinksByGlobalId()](/jira-service-management-cloud/docs/jql-functions/#workItemsWithRemoteLinksByGlobalId--)[lastLogin()](/jira-service-management-cloud/docs/jql-functions/#lastLogin--)[latestReleasedVersion()](/jira-service-management-cloud/docs/jql-functions/#latestReleasedVersion--)[linkedWorkItem](/jira-service-management-cloud/docs/jql-functions/#linkedWorkItem)[linkedWorkItems()](/jira-service-management-cloud/docs/jql-functions/#linkedWorkItems--)[membersOf()](/jira-service-management-cloud/docs/jql-functions/#membersOf--)[myApproval()](/jira-service-management-cloud/docs/jql-functions/#myApproval--)[myPendingApproval()](/jira-service-management-cloud/docs/jql-functions/#myPendingApproval--)[myPending()](/jira-service-management-cloud/docs/jql-functions/#myPending--)[now()](/jira-service-management-cloud/docs/jql-functions/#now--)[openSprints()](/jira-service-management-cloud/docs/jql-functions/#openSprints--)[organizationDetail()](/jira-service-management-cloud/docs/jql-functions/#organizationDetail--)[In Customer Service Management](/jira-service-management-cloud/docs/jql-functions/#In-Customer-Service-Management)[In Jira Service Management](/jira-service-management-cloud/docs/jql-functions/#In-Jira-Service-Management)[organizationMembers()](/jira-service-management-cloud/docs/jql-functions/#organizationMembers--)[parentEpic](/jira-service-management-cloud/docs/jql-functions/#parentEpic)[paused()](/jira-service-management-cloud/docs/jql-functions/#paused--)[pending()](/jira-service-management-cloud/docs/jql-functions/#pending--)[pendingApprovalBy()](/jira-service-management-cloud/docs/jql-functions/#pendingApprovalBy--)[pendingBy()](/jira-service-management-cloud/docs/jql-functions/#pendingBy--)[spacesLeadByUser()](/jira-service-management-cloud/docs/jql-functions/#spacesLeadByUser--)[spacesWhereUserHasPermission()](/jira-service-management-cloud/docs/jql-functions/#spacesWhereUserHasPermission--)[spacesWhereUserHasRole()](/jira-service-management-cloud/docs/jql-functions/#spacesWhereUserHasRole--)[releasedVersions()](/jira-service-management-cloud/docs/jql-functions/#releasedVersions--)[remaining()](/jira-service-management-cloud/docs/jql-functions/#remaining--)[running()](/jira-service-management-cloud/docs/jql-functions/#running--)[standardWorkTypes()](/jira-service-management-cloud/docs/jql-functions/#standardWorkTypes--)[startOfDay()](/jira-service-management-cloud/docs/jql-functions/#startOfDay--)[startOfMonth()](/jira-service-management-cloud/docs/jql-functions/#startOfMonth--)[startOfWeek()](/jira-service-management-cloud/docs/jql-functions/#startOfWeek--)[startOfYear()](/jira-service-management-cloud/docs/jql-functions/#startOfYear--)[subtaskWorkTypes()](/jira-service-management-cloud/docs/jql-functions/#subtaskWorkTypes--)[unreleasedVersions()](/jira-service-management-cloud/docs/jql-functions/#unreleasedVersions--)[updatedBy()](/jira-service-management-cloud/docs/jql-functions/#updatedBy--)[votedWorkItems()](/jira-service-management-cloud/docs/jql-functions/#votedWorkItems--)[watchedWorkItems()](/jira-service-management-cloud/docs/jql-functions/#watchedWorkItems--)[withinCalendarHours()](/jira-service-management-cloud/docs/jql-functions/#withinCalendarHours--)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
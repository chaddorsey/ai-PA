---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/jql-operators/
title: JQL operators | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:46.149780
---

# JQL operators

We're updating terminology in Jira, moving from "issue" to "work item", and "project" to "space".

As we roll out these changes, some JQL entries using the new terms may not work yet. If you come across this, try using the old term instead.

**There are no changes to existing JQL queries.**

This page describes information about operators that are used for advanced searching.

An operator in JQL is one or more symbols or words, which compares the value of a field on its left with one or more values (or functions) on its right, such that only true results are retrieved by the clause. Some operators may use the [NOT](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-NOT "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-NOT") keyword.

## Equals (=)

The "`=`" operator is used to search for work items where the value of the specified field exactly matches the specified value. (Note: cannot be used with text fields; see the [CONTAINS](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-CONTAINS "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-CONTAINS") operator instead.)

To find work items where the value of a specified field exactly matches *multiple* values, use multiple "`=`" statements with the [AND](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-AND "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-AND") operator.

**Examples**

* Find all work items that were created by John Smith:

  `reporter = "John Smith"`

* Find all work items that were created by John Smith whose Atlassian account id is `abcde-12345-fedcba:`

  `reporter = "abcde-12345-fedcba"`

## Not equals (!=)

The "`!=`" operator is used to search for work items where the value of the specified field does not match the specified value. (Note: cannot be used with text fields; see the [DOES NOT MATCH](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-DOES_NOT_MATCH "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-DOES_NOT_MATCH") ("`!~`") operator instead.)

Note that typing `field != value` is the same as typing `NOT field = value`, and that `field != EMPTY` is the same as `field IS_NOT EMPTY`.

The "`!=`" operator will not match a field that has no value (i.e. a field that is empty). For example, `component != fred` will only match work items that have a component **and** the component is not "fred". To find work items that have a component other than "fred" **or have no component**, you would need to type: `component != fred or component is empty`.

**Examples**

* Find all work items that are assigned to any user's Atlassian account id except John Smith's:

  `not assignee = abcde-12345-fedcba`

  or

  `assignee != abcde-12345-fedcba`
* Find all work items that are not assigned to John Smith's Atlassian account ID

  `assignee != abcde-12345-fedcba or assignee is empty`
* Find all work items that were reported by me but are not assigned to me:

  `reporter = currentUser() and assignee != currentUser()`
* Find all work items where the Reporter or Assignee is anyone except John Smith:

  `assignee != "John Smith" or reporter != "John Smith"`
* Find all work items where the Reports or Assignee is anyone except John Smith's:

  `assignee != "John Smith" or reporter != "John Smith"`
* Find all work items that are not unassigned:

  `assignee is not empty`

  or

  `assignee != null`

## Greater than (>)

The "`>`" operator is used to search for work items where the value of the specified field is greater than the specified value.

Note that the "`>`" operator can only be used with fields that support ordering (e.g. date fields and version fields), and cannot be used with text fields. To see a field's supported operators, check the individual field reference.

**Examples**

* Find all work items with more than 4 votes:

  `votes > 4`
* Find all overdue work items:

  `duedate < now() and resolution is empty`
* Find all work items where priority is higher than "Normal":

  `priority > normal`

## Greater than equals (>=)

The "`>=`" operator is used to search for work items where the value of the specified field is greater than or equal to the specified value.

Note that the "`>=`" operator can only be used with fields that support ordering (e.g. date fields and version fields), and cannot be used with text fields. To see a field's supported operators, check the individual field reference.

**Examples**

* Find all work items with 4 or more votes:

  `votes >= 4`
* Find all work items due on or after 31/12/2008:

  `duedate >= "2008/12/31"`
* Find all work items created in the last five days:

  `created >= "-5d"`

## Less than (<)

The "`<`" operator is used to search for work items where the value of the specified field is less than the specified value.

Note that the "`<`" operator can only be used with fields which support ordering (e.g. date fields and version fields), and cannot be used with text fields. To see a field's supported operators, check the individual field reference.

**Examples**

* Find all work items with less than 4 votes:

  `votes < 4`

## Less than equals (<=)

The "`<=`" operator is used to search for work items where the value of the specified field is less than or equal to than the specified value.

Note that the "`<=`" operator can only be used with fields which support ordering (e.g. date fields and version fields), and cannot be used with text fields. To see a field's supported operators, check the individual field reference.

**Examples**

* Find all work items with 4 or fewer votes:

  `votes <= 4`
* Find all work items that have not been updated in the past month (30 days):

  `updated <= "-4w 2d"`

## IN

The "`IN`" operator is used to search for work items where the value of the specified field is one of multiple specified values. The values are specified as a comma-delimited list, surrounded by parentheses.

Using "`IN`" is equivalent to using multiple `EQUALS (=)` statements, but is shorter and more convenient. That is, typing `reporter IN (tom, jane, harry)` is the same as typing `reporter = "tom" OR reporter = "jane" OR reporter = "harry"`.

**Examples**

* Find all work items that were created by either jsmith or jbrown or jjones:

  `reporter in (jsmith,jbrown,jjones)`
* Find all work items that were created by John Smith, Jim Brown, or Jared Jones whose Atlassian account IDs are abcde-12345-fedcba or fedcb-12345-edcba or cdefb-67895-cbaed, respectively:

  `reporter in (abcde-12345-fedcba,fedcb-12345-edcba,cdefb-67895-cbaed)`
* Find all work items where the Reporter or Assignee is either Jack or Jill:

  `reporter in (Jack,Jill) or assignee in (Jack,Jill)`
* Find all work items where the Reporter or Assignee is either Jack or Jill whose Atlassian account IDs are abcde-12345-fedcba and cdefb-67895-cbaed, respectively:

  `reporter in (abcde-12345-fedcba,cdefb-67895-cbaed) or assignee in (abcde-12345-fedcba,cdefb-67895-cbaed)`
* Find all work items in version 3.14 or version 4.2:

  `affectedVersion in ("3.14", "4.2")`

## NOT IN

The "`NOT IN`" operator is used to search for work items where the value of the specified field is not one of multiple specified values.

Using "`NOT IN`" is equivalent to using multiple `NOT_EQUALS (!=)` statements, but is shorter and more convenient. That is, typing `reporter NOT IN (tom, jane, harry)` is the same as typing `reporter != "tom" AND reporter != "jane" AND reporter != "harry"`.

The "`NOT IN`" operator will not match a field that has no value (i.e. a field that is empty). For example, `assignee not in (jack,jill)` will only match work items that have an assignee **and** the assignee is not "jack" or "jill". To find work items that are assigned to someone other than "jack" or "jill" **or are unassigned**, you would need to type: `assignee not in (jack,jill) or assignee is empty`.

**Examples**

* Find all work items where the Assignee is someone other than Jack, Jill, or John:

  `assignee not in (Jack,Jill,John)`
* Find all work items where the Assignee is someone other than Jack, Jill, or John whose Atlassian account IDs are abcde-12345-fedcba or fedcb-12345-edcba or cdefb-67895-cbaed, respectively:

  `assignee not in (abcde-12345-fedcba,fedcb-12345-edcba,cdefb-67895-cbaed)`
* Find all work items where the Assignee is not Jack, Jill, or John:

  `assignee not in (Jack,Jill,John) or assignee is empty`
* Find all work items where the Assignee is not Jack, Jill, or John whose Atlassian account IDs are abcde-12345-fedcba or fedcb-12345-edcba or cdefb-67895-cbaed, respectively:

  `assignee not in (abcde-12345-fedcba,fedcb-12345-edcba,cdefb-67895-cbaed) or assignee is empty`

* Find all work items where the FixVersion is not 'A', 'B', 'C', or 'D':

  `FixVersion not in (A, B, C, D)`
* Find all work items where the FixVersion is not 'A', 'B', 'C', or 'D', or has not been specified:

  `FixVersion not in (A, B, C, D) or FixVersion is empty`

## CONTAINS (~)

The "`~`" operator is used to search for work items where the value of the specified field matches the specified value (either an exact match or a "fuzzy" match — see examples below). For use with text fields, such as:

* Summary
* Description
* Environment
* Comments
* custom fields that use the "Free Text Searcher"; this includes custom fields of the following built-in Custom Field Types

  + Free Text Field (unlimited text)
  + Text Field (< 255 characters)
  + Read-only Text Field

And, the work item key.

The JQL field "text" as in `text ~ "some words"` searches a work item’s Summary, Description, Environment, Comments. It also searches all text custom fields. If you have many text custom fields you can improve performance of your queries by searching on specific fields, e.g.   
`Summary ~ "some words" OR Description ~ "some words"`

Note: when using the "`~`" operator, the value on the right-hand side of the operator can be specified using [Jira text-search syntax](https://confluence.atlassian.com/jirasoftwarecloud/search-syntax-for-text-fields-764478343.html "https://confluence.atlassian.com/jirasoftwarecloud/search-syntax-for-text-fields-764478343.html").

**Examples**

* Find all work items where the Summary contains the word "win" (or simple derivatives of that word, such as "wins"):

  `summary ~ win`

* Find all work items with a space key ending in “WIN” and work item number starting with “1”:

  `issueKey ~ "*WIN-1*"`

* Find all work items where the Summary contains a wild-card match for the word "win":

  `summary ~ "win*"`
* Find all work items where the Summary contains the word "work items" and the word "collector":

  `summary ~ "workItem collector"`
* Find all work items where the Summary contains the exact phrase "full screen" (see [Search syntax for text fields](https://confluence.atlassian.com/jirasoftwarecloud/search-syntax-for-text-fields-764478343.html "https://confluence.atlassian.com/jirasoftwarecloud/search-syntax-for-text-fields-764478343.html") for details on how to escape quote-marks and other special characters):

  `summary ~ "\"full screen\""`

## DOES NOT CONTAIN (!~)

The "`!~`" operator is used to search for work items where the value of the specified field is not a "fuzzy" match for the specified value. For use with text fields, such as:

* Summary
* Description
* Environment
* Comment\*
* custom fields that use the "Free Text Searcher"; this includes custom fields of the following built-in Custom Field Types

  + Free Text Field (unlimited text)
  + Text Field (< 255 characters)
  + Read-only Text Field

And, the work item key.

*\*If the work item contains more than 1 comment, this operator will fail, because all comments will be included in the search.*

The JQL field "text" as in `text ~ "some words"` searches a work item’s Summary, Description, Environment, Comments. It also searches all text custom fields. If you have many text custom fields you can improve performance of your queries by searching on specific fields, e.g.   
`Summary ~ "some words" OR Description ~ "some words"`

Note: when using the "`!~`" operator, the value on the right-hand side of the operator can be specified using [Jira text-search syntax](https://confluence.atlassian.com/jirasoftwarecloud/search-syntax-for-text-fields-764478343.html "https://confluence.atlassian.com/jirasoftwarecloud/search-syntax-for-text-fields-764478343.html").

**Examples**

* Find all work items where the Summary does not contain the word "run" (or derivatives of that word, such as "running" or "ran"):

  `summary !~ run`
* Find all work items with a work item key that does not start with “12”:

  `issueKey !~ "-12*"`

## IS

The "`IS`" operator can only be used with [EMPTY](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-EMPTY "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-EMPTY") or [NULL](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-NULL "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-NULL"). That is, it is used to search for work items where the specified field has no value.

Note that not all fields are compatible with this operator; see the individual field reference for details.

**Examples**

* Find all work items that have no Fix Version:

  `fixVersion is empty`

  or

  `fixVersion is null`

## IS NOT

The "`IS NOT`" operator can only be used with [EMPTY](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-EMPTY "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-EMPTY") or [NULL](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-NULL "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-operators/#Advancedsearchingoperatorsreference-NULL"). That is, it is used to search for work items where the specified field has a value.

Note that not all fields are compatible with this operator; see the individual field reference for details.

**Examples**

* Find all work items that have one or more votes:

  `votes is not empty`

  or

  `votes is not null`

## WAS

The "`WAS`" operator is used to find work items that currently have or previously had the specified value for the specified field.

This operator has the following optional predicates:

* `AFTER "date"`
* `BEFORE "date"`
* `BY "username"` or `BY (username1,username2)`
* `DURING ("date1","date2")`
* `ON "date"`

This operator will match the value name (e.g. "Resolved"), which was configured in your system *at the time that the field was changed*. This operator will also match the value ID associated with that value name too — that is, it will match "4" as well as "Resolved".

This operator can be used with the Assignee, Fix Version, Priority, Reporter, Resolution, and Status fields only.

**Examples**

* Find work items that currently have or previously had a status of 'In Progress':

  `status WAS "In Progress"`
* Find work items that were resolved by Joe Smith before 2nd February:

  `status WAS "Resolved" BY jsmith BEFORE "2019/02/02"`
* Find work items that were resolved by Joe Smith, whose Atlassian account ID is abcde-12345-fedcba, before 2nd February:

  `status WAS "Resolved" BY abcde-12345-fedcba BEFORE "2019/02/02"`
* Find work items that were resolved by Joe Smith during 2010:

  `status WAS "Resolved" BY jsmith DURING ("2010/01/01","2011/01/01")`
* Find work items that were resolved by Joe Smith, whose Atlassian account ID is abcde-12345-fedcba, during 2010:

  `status WAS "Resolved" BY abcde-12345-fedcba DURING ("2010/01/01","2011/01/01")`
* Find work items that were resolved by Joe Smith or Sam Rogen during 2019:

  `status WAS "Resolved" BY (jsmith,srogen) DURING ("2019/01/01","2020/01/01")`

## WAS IN

The "`WAS IN`" operator is used to find work items that currently have or previously had any of multiple specified values for the specified field. The values are specified as a comma-delimited list, surrounded by parentheses.

Using "`WAS IN`" is equivalent to using multiple `WAS` statements, but is shorter and more convenient. That is, typing `status WAS IN ('Resolved', 'Closed')` is the same as typing `status WAS "Resolved" OR status WAS "Closed"`.

This operator has the following optional predicates:

* `AFTER "date"`
* `BEFORE "date"`
* `BY "username"`
* `DURING ("date1","date2")`
* `ON "date"`

This operator will match the value name (e.g. "Resolved"), which was configured in your system *at the time that the field was changed*. This operator will also match the value ID associated with that value name too — that is, it will match "4" as well as "Resolved".

Note: This operator can be used with the Assignee, Fix Version, Priority, Reporter, Resolution, and Status fields only.

**Examples**

* Find all work items that currently have, or previously had, a status of 'Resolved' or 'In Progress':

  `status WAS IN ("Resolved","In Progress")`

## WAS NOT IN

The "`WAS NOT IN`" operator is used to search for work items where the value of the specified field has never been one of multiple specified values.

Using "`WAS NOT IN`" is equivalent to using multiple `WAS_NOT` statements, but is shorter and more convenient. That is, typing `status WAS NOT IN ("Resolved","In Progress")` is the same as typing `status WAS NOT "Resolved" AND status WAS NOT "In Progress"`.

This operator has the following optional predicates:

* `AFTER "date"`
* `BEFORE "date"`
* `BY "username"`
* `DURING ("date1","date2")`
* `ON "date"`

This operator will match the value name (e.g. "Resolved"), which was configured in your system *at the time that the field was changed*. This operator will also match the value ID associated with that value name, too — that is, it will match "4" as well as "Resolved".

Note: This operator can be used with the Assignee, Fix Version, Priority,  Reporter, Resolution, and Status fields only.

**Examples**

* Find work items that have never had a status of 'Resolved' or 'In Progress':

  `status WAS NOT IN ("Resolved","In Progress")`
* Find work items that did not have a status of 'Resolved' or 'In Progress' before 2nd February:

  `status WAS NOT IN ("Resolved","In Progress") BEFORE "2011/02/02"`

## WAS NOT

The "`WAS NOT`" operator is used to find work items that have never had the specified value for the specified field.

This operator has the following optional predicates:

* `AFTER "date"`
* `BEFORE "date"`
* `BY "username"`
* `DURING ("date1","date2")`
* `ON "date"`

This operator will match the value name (e.g. "Resolved"), which was configured in your system *at the time that the field was changed*. This operator will also match the value ID associated with that value name too — that is, it will match "4" as well as "Resolved".

Note: This operator can be used with the Assignee, Fix Version, Priority, Reporter, Resolution, and Status fields only.

**Examples**

* Find work items that do not have, and have never had a status of 'In Progress':

  `status WAS NOT "In Progress"`
* Find work items that did not have a status of 'In Progress' before 2nd February:

  `status WAS NOT "In Progress" BEFORE "2011/02/02"`

## CHANGED

The "`CHANGED`" operator is used to find work items that have a value that had changed for the specified field.

This operator has the following optional predicates:

* `AFTER "date"`
* `BEFORE "date"`
* `BY "username"`
* `DURING ("date1","date2")`
* `ON "date"`
* `FROM "oldvalue"`
* `TO "newvalue"`

Note: This operator can be used with the Assignee, Fix Version, Priority, Reporter, Resolution, and Status fields only.

**Examples**

* Find work items whose assignee had changed:

  `assignee CHANGED`
* Find work items whose status had changed from 'In Progress' back to 'Open':

  `status CHANGED FROM "In Progress" TO "Open"`
* Find work items whose priority was changed by user 'freddo' after the start and before the end of the current week.

  `priority CHANGED BY freddo BEFORE endOfWeek() AFTER startOfWeek()`

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
* JQL operators
* [Search for Advanced Roadmaps custom fields in JQL](/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/)

On this page[Equals (=)](/jira-service-management-cloud/docs/jql-operators/#Equals----)[Not equals (!=)](/jira-service-management-cloud/docs/jql-operators/#Not-equals-----) [Greater than (>)](/jira-service-management-cloud/docs/jql-operators/#Greater-than---gt--)[Greater than equals (>=)](/jira-service-management-cloud/docs/jql-operators/#Greater-than-equals---gt---)[Less than (<)](/jira-service-management-cloud/docs/jql-operators/#Less-than---lt--) [Less than equals (<=)](/jira-service-management-cloud/docs/jql-operators/#Less-than-equals---lt---)[IN](/jira-service-management-cloud/docs/jql-operators/#IN)[NOT IN](/jira-service-management-cloud/docs/jql-operators/#NOT-IN)[CONTAINS (~)](/jira-service-management-cloud/docs/jql-operators/#CONTAINS----)[DOES NOT CONTAIN (!~)](/jira-service-management-cloud/docs/jql-operators/#DOES-NOT-CONTAIN-----)[IS](/jira-service-management-cloud/docs/jql-operators/#IS)[IS NOT](/jira-service-management-cloud/docs/jql-operators/#IS-NOT)[WAS](/jira-service-management-cloud/docs/jql-operators/#WAS)[WAS IN](/jira-service-management-cloud/docs/jql-operators/#WAS-IN)[WAS NOT IN](/jira-service-management-cloud/docs/jql-operators/#WAS-NOT-IN)[WAS NOT](/jira-service-management-cloud/docs/jql-operators/#WAS-NOT)[CHANGED](/jira-service-management-cloud/docs/jql-operators/#CHANGED)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
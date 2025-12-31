---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/jql-keywords/
title: JQL keywords | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:44.681535
---

# JQL keywords

We're updating terminology in Jira, moving from "issue" to "work item", and "project" to "space".

As we roll out these changes, some JQL entries using the new terms may not work yet. If you come across this, try using the old term instead.

**There are no changes to existing JQL queries.**

This page describes information about keywords that are used for advanced searching. A keyword in JQL is a word or phrase that does (or is) any of the following:

* joins two or more clauses together to form a complex JQL query
* alters the logic of one or more clauses
* alters the logic of operators
* has an explicit definition in a JQL query
* performs a specific function that alters the results of a JQL query

## AND

Used to combine multiple clauses, allowing you to refine your search.

Note that you can use parentheses to control the order in which clauses are executed.

**Examples**

* Find all open work items in the "New office" space:

  `space = "New office" and status = "open"`
* Find all open, urgent work items that are assigned to jsmith:

  `status = open and priority = urgent and assignee = jsmith`
* Find all work items in a particular space that are not assigned to jsmith:

  `space = JRA and assignee != jsmith`
* Find all work items for a specific release which consists of different version numbers across several spaces:

  `space in (JRA,CONF) and fixVersion = "3.14"`
* Find all work items where neither the Reporter nor the Assignee is Jack, Jill or John:

  `reporter not in (Jack,Jill,John) and assignee not in (Jack,Jill,John)`

## OR

Used to combine multiple clauses, allowing you to expand your search.

Note that you can use parentheses to control the order in which clauses are executed.

(Note: also see [IN](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-IN "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-IN"), which can be a more convenient way to search for multiple values of a field.)

**Examples**

* Find all work items that were created by either jsmith or jbrown:

  `reporter = jsmith or reporter = jbrown`
* Find all work items that are overdue or where no due date is set:

  `duedate < now() or duedate is empty`

## NOT

Used to negate individual clauses or a complex JQL query (a query made up of more than one clause) using parentheses, allowing you to refine your search.

(Note: also see [NOT EQUALS](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-NOT_EQUALS "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-NOT_EQUALS") ("!="), [DOES NOT CONTAIN](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-DOES_NOT_CONTAIN "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-DOES_NOT_CONTAIN") ("!~"), [NOT IN](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-NOT_IN "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-NOT_IN") and [IS NOT](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-IS_NOT "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-IS_NOT").)

**Examples**

* Find all work items that are assigned to any user except jsmith:

  `not assignee = jsmith`
* Find all work items that were not created by either jsmith or jbrown:

  `not (reporter = jsmith or reporter = jbrown)`

## EMPTY

Used to search for work items where a given field does not have a value. See also [NULL](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-NULL "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-NULL").

Note that EMPTY can only be used with fields that support the [IS](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-IS "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-operators-reference-764478341.html#Advancedsearchingoperatorsreference-IS") and [IS NOT](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-IS_NOT "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-IS_NOT") operators. To see a field's supported operators, check the individual [field](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-fields-reference-764478339.html "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-fields-reference-764478339.html") reference.

**Examples**

* Find all work items without a DueDate:

  `duedate = empty`

  or

  `duedate is empty`

## NULL

Used to search for work items where a given field does not have a value. See also [EMPTY](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-EMPTY "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-EMPTY").

Note that NULL can only be used with fields that support the [IS](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-IS "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-IS") and [IS NOT](https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-IS_NOT "https://support.atlassian.com/jira-software-cloud/docs/advanced-search-reference-jql-keywords/#Advancedsearchingkeywordsreference-IS_NOT") operators. To see a field's supported operators, check the individual [field](https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-fields-reference-764478339.html "https://confluence.atlassian.com/jirasoftwarecloud/advanced-searching-fields-reference-764478339.html") reference.

**Examples**

* Find all work items without a DueDate:

  `duedate = null`

  or

  `duedate is null`

## ORDER BY

Used to specify the fields by whose values the search results will be sorted. This requirement needs to be placed at the end of the JQL query, otherwise the JQL will be invalid.

By default, the field's own sorting order will be used. You can override this by specifying ascending order ("`asc`") or descending order ("`desc`").

**Examples**

* Find all work items without a DueDate, sorted by CreationDate:

  `duedate = empty order by created`
* Find all work items without a DueDate, sorted by CreationDate, then by Priority (highest to lowest):

  `duedate = empty order by created, priority desc`
* Find all work items without a DueDate, sorted by CreationDate, then by Priority (lowest to highest):

  `duedate = empty order by created, priority asc`

Ordering by **Components** or **Versions** will list the returned work items first by **Space**, and only then by the field's natural order (see [JRA-31113](https://jira.atlassian.com/browse/JRA-31113 "https://jira.atlassian.com/browse/JRA-31113")).

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
* JQL keywords
* [JQL operators](/jira-service-management-cloud/docs/jql-operators/)
* [Search for Advanced Roadmaps custom fields in JQL](/jira-service-management-cloud/docs/search-for-advanced-roadmaps-custom-fields-in-jql/)

On this page[AND](/jira-service-management-cloud/docs/jql-keywords/#AND)[OR](/jira-service-management-cloud/docs/jql-keywords/#OR)[NOT](/jira-service-management-cloud/docs/jql-keywords/#NOT)[EMPTY](/jira-service-management-cloud/docs/jql-keywords/#EMPTY)[NULL](/jira-service-management-cloud/docs/jql-keywords/#NULL)[ORDER BY](/jira-service-management-cloud/docs/jql-keywords/#ORDER-BY)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
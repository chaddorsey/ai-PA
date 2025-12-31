---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/write-jql-queries-for-slas/
title: Write JQL queries for SLAs | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:53.131027
---

# Write JQL queries for SLAs

JQL queries have an order that needs to be followed when creating [SLAs](https://support.atlassian.com/jira-service-desk-cloud/docs/what-are-slas-and-where-can-i-see-them-in-my-service-desk/ "https://support.atlassian.com/jira-service-desk-cloud/docs/what-are-slas-and-where-can-i-see-them-in-my-service-desk/") (service level agreements). There are also functions that are frequently used when creating SLA queries, commonly used operators and certain characters and words that have been reserved in Jira to perform specific functions in the query. [Read more about JQL fields](https://support.atlassian.com/jira-service-management-cloud/docs/jql-fields/ "https://support.atlassian.com/jira-service-management-cloud/docs/jql-fields/").

## Elements in a query

In JQL, a query has four basic elements:

### Field

Fields are different types of information in the system. For example, a Jira Service Management field may be priority, work type, date created and project.

### Operator

Operators are the heart of the query. They relate the field to the value. Common operators include equals (=), not equals (!=) and less than (<).

### Value

Values are the actual data in the query. For example, paused() and remaining(“2h”).

### Functions

Functions are special calculations within Jira to access specific data. For example, work items that have breached SLAs.

You can optionally link a query together using a few select keywords. Keywords are specific words in the language that have special meaning. For example, this may be AND and OR.

A simple query in JQL consists of a *field*, followed by an *operator*, followed by one or more *values* or *functions*.

For example: **project = Test**

This query finds all work items in the *Test* project. It uses the project (*field)*, the equals = (*operator)*, and the Test (*value*).

## Commonly used functions when writing SLA queries

The following are functions that are commonly used when writing JQL queries for an SLA:

### breached()

This filters out work items where the last SLA cycle has failed to meet its target goal.

### everBreached()

This filters out work items that have failed to meet their target goal.

### paused()

This filters work items where the current SLA cycle is paused due to a particular condition. For example, you may pause a work items SLA clock when the work item's status is set to *waiting for customer*.

### completed()

This filters work items where the SLA cycle is complete, meaning the work item has reached one of their stop events.

### running()

This filters work items where the current SLA clock is running, meaning the work items haven't yet reached one of the stop events.

### withincalendarhours()

This filters work items whose SLA clock is running or not running according to the SLA calendar, *not* conditions.

### elapsed()

This filters work items where the SLA cycle's clock meets a specified time condition since the ongoing SLA cycle's start event.

### remaining()

This filters work items whose SLA cycle's clock meets a specified time condition before the work item will breach an SLA goal.

## Commonly used operators

Here are some common character and word operators that you can use in your SLA JQL query:

### Characters

=, >, >,=, ~, != < <= !~

### Words

not, in, is not, was, not, was not, in, not in, is, was, was in, changed

## Reserved characters and words

Here are some reserved characters and words in Jira that need to be used in a specific manner when using them in a query.

### Characters

space (" "), +, ., ;, ?, |, \*, /, %, ^, $, #, @, [ ], ,

### Words

a, and, are, as, at, be, but, by, for, if, in, into, is, it, no, not, of, on, or, s, such, t, that, the, their, then, there, these, they, this, to, was, will, with

When using reserved characters or words in your queries, you need to:

* surround them with quote marks. You can use either single or double quote marks. For example, *‘Time to first response’.*
* if you are searching a text field and the character is on the list of reserved characters or words, precede them with two backslashes. For example, \\*'Time to first response'.*

## JQL example: find work items breaching your SLA goals

For example, if you wanted to find all the work items in your project that have successfully completed your first-response goals, use the following query:

`“Time to first response“ != everBreached ()`

## JQL example: find work items based on their SLA clock

For example, if you want to find requests that have been waiting for a first response for less than 10 minutes, use the following query:

`"Time to first response" < elapsed("10m")`

Or, if you want to find work items that will breach their resolution target within the next two hours, use this query:

`"Time to resolution" < remaining ("2h")`

Was this helpful?

Yes

No

It wasn't accurateIt wasn't clearIt wasn't relevant

Provide feedback about this article

## Still need help?

The Atlassian Community is here for you.

[Ask the Community](https://community.atlassian.com/t5/custom/page/page-id/create-post-step-1?add-tags=jira-service-management,Cloud)

* [Use Jira Query Language to create service level agreements](/jira-service-management-cloud/docs/use-jira-query-language-jql-to-create-service-level-agreements-slas/)
* [How to structure your SLA goals around priority using JQL](/jira-service-management-cloud/docs/how-to-structure-your-sla-goals-around-priority-using-jql/)
* Write JQL queries for SLAs

On this page[Elements in a query](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Elements-in-a-query) [Field](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Field) [Operator](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Operator)[Value](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Value)[Functions](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Functions)[Commonly used functions when writing SLA queries](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Commonly-used-functions-when-writing-SLA-queries)[breached()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#breached--)[everBreached()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#everBreached--)[paused()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#paused--)[completed()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#completed--)[running()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#running--)[withincalendarhours()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#withincalendarhours--)[elapsed()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#elapsed--)[remaining()](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#remaining--)[Commonly used operators](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Commonly-used-operators)[Characters](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Characters)[Words](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Words)[Reserved characters and words](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Reserved-characters-and-words)[Characters](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Characters.1)[Words](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#Words.1)[JQL example: find work items breaching your SLA goals](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#JQL-example--find-work-items-breaching-your-SLA-goals)[JQL example: find work items based on their SLA clock](/jira-service-management-cloud/docs/write-jql-queries-for-slas/#JQL-example--find-work-items-based-on-their-SLA-clock)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
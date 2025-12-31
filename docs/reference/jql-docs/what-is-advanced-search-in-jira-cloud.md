---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/
title: What is advanced search in Jira Cloud? | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:51.783142
---

# What is advanced search in Jira Cloud?

The advanced search allows you to build structured queries using the Jira Query Language (JQL) to search for work items. You can specify criteria that you can't define in the quick or basic searches. For example, you can use the `ORDER BY` clause in JQL when you’re searching for work items. JQL can help gain key space insights and help you find not just work items but also important information in spaces.

If you don't have complex search criteria, try [quick search](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-in-a-project/#Searchingforissues-Performaquicksearch "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-in-a-project/#Searchingforissues-Performaquicksearch") instead.

JQL is not a database query language, even though it uses SQL-like syntax. In advanced search, you can use queries to find your work items. Queries are a series of elements or parts, like fields, operators, and values, that are strung together to form a structure. [More about constructing JQL queries](https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/#Construct-JQL-queries "https://support.atlassian.com/jira-software-cloud/docs/what-is-advanced-search-in-jira-cloud/#Construct-JQL-queries")

Using JQL, you could search for all work items in your space “Assassin’s Guild” that:

* have “weaponry” in a text field, and
* are ordered by when they were `created` in ascending or descending order.

1. Switch between **Basic** and **JQL**
2. JQL editor
3. **Expand** or **Collapse** editor
4. **Syntax help**
5. **Search** button
6. Line numbers when your JQL query is longer than a line
7. Autocomplete suggestions based on context

## Perform advanced searching with JQL queries

The syntax-powered advanced search or JQL is a powerful tool for getting specific information from spaces.

To use advanced search or JQL to find your work items:

1. Select **Search** 🔍 in the top navigation (or press `/` on your keyboard). Alternatively, select **Filters** in the [sidebar.](https://support.atlassian.com/jira-software-cloud/docs/new-jira-cloud-navigation/#The-navigation-bar "https://support.atlassian.com/jira-software-cloud/docs/new-jira-cloud-navigation/#The-navigation-bar")
2. Select **View all work items**.

   * If the basic search is shown instead of the advanced search, select **JQL** (next to the 🔍  icon). If advanced or JQL search is already enabled, you'll see the option to switch to basic.
3. Enter your JQL query.
4. Press **Enter** or select 🔍 to run your query. Your search results will be displayed based on the criteria in your JQL query.

As you type, Jira will offer a list of "autocomplete" suggestions based on the context of your query. Note, autocomplete suggestions only include the first 15 matches, displayed alphabetically, so you may need to enter more text if you can't find a match.

## Construct JQL queries

Get the most out of advanced searching by learning how to structure your JQL query. A simple query in JQL (also known as a 'clause') consists of a *field*, followed by an *operator*, followed by one or more *values* or *functions*.

|  | **Description** |
| --- | --- |
| **Fields** | A field in JQL is a word that represents a Jira field (or a custom field that has already been defined in Jira). [More about using fields for advanced searching](https://support.atlassian.com/jira-software-cloud/docs/jql-fields/ "https://support.atlassian.com/jira-software-cloud/docs/jql-fields/"). |
| **Operators** | An operator in JQL is one or more symbols or words that compare the value of a field on its left with one or more values (or functions) on its right, such that only true results are retrieved by the clause. Some operators may use the NOT keyword. [More about using operators for advanced searching](https://support.atlassian.com/jira-software-cloud/docs/jql-operators/ "https://support.atlassian.com/jira-software-cloud/docs/jql-operators/"). |
| **Keywords** | A keyword in JQL is a word or phrase that does (or is) any of the following:   * joins two or more clauses together to form a complex JQL query * alters the logic of one or more clauses * alters the logic of operators * has an explicit definition in a JQL query * performs a specific function that alters the results of a JQL query.   [More about using keywords for advanced searching](https://support.atlassian.com/jira-software-cloud/docs/jql-keywords/ "https://support.atlassian.com/jira-software-cloud/docs/jql-keywords/"). |
| **Functions** | A function in JQL appears as a word followed by parentheses, which may contain one or more explicit values or Jira fields.  A function performs a calculation on either specific Jira data or the function's content in parentheses, such that only true results are retrieved by the function, and then again by the clause in which the function is used.  [More about using functions for advanced searching](https://support.atlassian.com/jira-software-cloud/docs/jql-functions/ "https://support.atlassian.com/jira-software-cloud/docs/jql-functions/"). |

For example:

`project = "TEST"`

This query will find all work items in the "TEST" project. It uses the "project" *field*, the EQUALS *operator*, and the *value* `"TEST"`.

A more complex query might look like this:

`project = "TEST" AND assignee = currentuser()`

This query will find all work items in the "TEST" project where the assignee is the currently logged in user. It uses the "project" *field*, the EQUALS *operator*, the *value* `"TEST",`the "AND" keyword and the "currentuser()" function.

### Set the precedence of operators

You can use parentheses in complex JQL statements to enforce the precedence of operators.

For example, if you want to find all resolved work items in the 'SysAdmin' project, as well as all work items (any status, any project) currently assigned to the system administrator (bobsmith), you can use parentheses to enforce the precedence of the boolean operators in your query, i.e.

`(status=resolved AND project=SysAdmin) OR assignee=bobsmith`

Note that if you do not use parentheses, the statement will be evaluated left-to-right.

You can also use parentheses to group clauses, so that you can apply the NOT operator to the group.

## Restricted words and characters

### Special characters

In general, non-alphanumeric characters, such as `+ . , * / % ^ $ # @ [ ]`, aren't indexed for search and are ignored in queries. Exceptions include email addresses and URLs.

When building queries, make sure to surround phrases with special characters or spaces with single `'` or double `"` quotation marks, for example: `field ~ "email@atlassian.com"`. Additionally, some characters may need to be preceded by two backslashes `\\`, for example, `field ~ "\\(text"`.

### Reserved words

JQL also has a list of reserved words. These words need to be surrounded by quotation marks (single or double) if you wish to use them in queries:

"a", "an", "abort", "access", "add", "after", "alias", "all", "alter", "and", "any", "are", "as", "asc", "at", "audit", "avg", "be", "before", "begin", "between", "boolean", "break", "but", "by", "byte", "catch", "cf", "char", "character", "check", "checkpoint", "collate", "collation", "column", "commit", "connect", "continue", "count", "create", "current", "date", "decimal", "declare", "decrement", "default", "defaults", "define", "delete", "delimiter", "desc", "difference", "distinct", "divide", "do", "double", "drop", "else", "empty", "encoding", "end", "equals", "escape", "exclusive", "exec", "execute", "exists", "explain", "false", "fetch", "file", "field", "first", "float", "for", "from", "function", "go", "goto", "grant", "greater", "group", "having", "identified", "if", "immediate", "in", "increment", "index", "initial", "inner", "inout", "input", "insert", "int", "integer", "intersect", "intersection", "into", "is", "isempty", "isnull", "it", "join", "last", "left", "less", "like", "limit", "lock", "long", "max", "min", "minus", "mode", "modify", "modulo", "more", "multiply", "next", "no", "noaudit", "not", "notin", "nowait", "null", "number", "object", "of", "on", "option", "or", "order", "outer", "output", "power", "previous", "prior", "privileges", "public", "raise", "raw", "remainder", "rename", "resource", "return", "returns", "revoke", "right", "row", "rowid", "rownum", "rows", "select", "session", "set", "share", "size", "sqrt", "start", "strict", "string", "subtract", "such", "sum", "synonym", "table", "that", "the", "their", "then", "there", "these", "they", "this", "to", "trans", "transaction", "trigger", "true", "uid", "union", "unique", "update", "user", "validate", "values", "view", "was", "when", "whenever", "where", "while", "will", "with"

## Types of JQL

### Bounded JQL query

A bounded JQL is a JQL that requires a search restriction. The JQL must have at least one condition with field on the left side followed by an operator and then by one or more values (or functions). Here are some examples of bounded queries:

* `project = TEST order by key`; here, `project = TEST` is a search restriction in the JQL query.
* `reporter = currentUser()`; here, `reporter = currentUser()` is a search restriction in the JQL query.
* `status IN ("To Do", "IN PROGRESS") AND priority >= Medium ORDER BY created`; here `status IN ("To Do", "IN PROGRESS")` and `priority >= Medium` are the search restrictions in the JQL query.

### Unbounded JQL query

On the other hand, unbounded JQL is a JQL that doesn't have any search restrictions. They can be an empty query or one that solely lists order by clauses, such as:

* `order by createdDate`
* `order by key`

## Perform a text search

You can use text-searching features when performing searches on the following fields, using the CONTAINS operator:

Summary, Description, Environment, Comments, and custom fields that use the "Free Text Searcher"

The custom fields that use the "Free Text Searcher" are built-in custom field types, like Free Text Field, Text Field, Read-only Text Field.

[More about using search syntax for text fields](https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/ "https://support.atlassian.com/jira-software-cloud/docs/search-for-issues-using-the-text-field/")

## Troubleshooting in advanced search

### Why can't I switch between basic and advanced search?

In general, a query created using the basic search can be translated to advanced JQL search, and back again. However, a complex query created using advanced JQL criteria may not be translated to basic search, particularly if:

* the query contains an OR operator. Instead, you can use an IN operator and it will be translated. For example: `project in (A, B)`
* the query contains a NOT operator
* the query contains an EMPTY operator
* the query contains any of the comparison operators: !=, IS, IS NOT, >, >=, <, <=
* the query specifies a field and value that is related to a space (e.g. version, component, custom fields) and the space is not explicitly included in the query (e.g. `fixVersion = "4.0"`, without the `AND project=JRA`). This is especially tricky with custom fields since they can be configured on a Space/Work Type basis. The general rule of thumb is that if the query cannot be created in the basic search form, then it will not be able to be translated from advanced search to basic search.

### Why can't I see autocomplete suggestions?

* Your administrator may have disabled the "JQL Auto-complete" feature for your Jira instance.
* Auto-complete suggestions are not offered for function parameters.
* Auto-complete suggestions are not offered for all fields. Check the [fields](https://support.atlassian.com/jira-software-cloud/docs/jql-fields/ "https://support.atlassian.com/jira-software-cloud/docs/jql-fields/") reference to see which fields support autocomplete.

### Where can I see the error in my JQL query?

While typing, you can hover over the invalid text of your query to know more about the JQL error. Alternatively, if your JQL query has an error, you can hit search and Jira will display the specifics of the error below the JQL editor, along with the line and character number of the invalid text in the query.

### How can I fix the error in my JQL query?

Run your query and check for any error messages below the JQL editor. You can fix the JQL errors:

* manually by identifying and correcting issues like missing fields, incorrect operators, or typos
* by reviewing the AI-generated, error-free query suggestion, and selecting **Accept** to apply it instantly

AI is available and automatically activated for all apps on Standard, Premium, and Enterprise plans. Organization admins can manage AI preferences from **Apps** > **AI settings** > **AI-enabled apps** in Atlassian Administration.

AI is not available in [Atlassian Government organizations](https://support.atlassian.com/organization-administration/docs/feature-availability-for-atlassian-government-cloud/) or Confluence Cloud sandbox environments.

Was this helpful?

Yes

No

It wasn't accurateIt wasn't clearIt wasn't relevant

Provide feedback about this article

## Still need help?

The Atlassian Community is here for you.

[Ask the Community](https://community.atlassian.com/t5/custom/page/page-id/create-post-step-1?add-tags=jira-service-management,Cloud)

* [Use advanced search with Jira Query Language (JQL)](/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/)
* What is advanced search in Jira Cloud?
* [JQL functions](/jira-service-management-cloud/docs/jql-functions/)
* [JQL developer status](/jira-service-management-cloud/docs/jql-developer-status/)
* [JQL fields](/jira-service-management-cloud/docs/jql-fields/)
* [JQL keywords](/jira-service-management-cloud/docs/jql-keywords/)
* Show more

On this page[Perform advanced searching with JQL queries](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Perform-advanced-searching-with-JQL-queries)[Construct JQL queries](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Construct-JQL-queries)[Set the precedence of operators](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Set-the-precedence-of-operators) [Restricted words and characters](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Restricted-words-and-characters)[Special characters](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Special-characters)[Reserved words](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Reserved-words)[Types of JQL](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Types-of-JQL)[Bounded JQL query](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Bounded-JQL-query)[Unbounded JQL query](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Unbounded-JQL-query)[Perform a text search](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Perform-a-text-search)[Troubleshooting in advanced search](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Troubleshooting-in-advanced-search)[Why can't I switch between basic and advanced search?](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Why-can--x27-t-I-switch-between-basic-and-advanced-search)[Why can't I see autocomplete suggestions?](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Why-can--x27-t-I-see-autocomplete-suggestions)[Where can I see the error in my JQL query?](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#Where-can-I-see-the-error-in-my-JQL-query)[How can I fix the error in my JQL query?](/jira-service-management-cloud/docs/what-is-advanced-search-in-jira-cloud/#How-can-I-fix-the-error-in-my-JQL-query)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
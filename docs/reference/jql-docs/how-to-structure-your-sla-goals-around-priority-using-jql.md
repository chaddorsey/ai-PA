---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/how-to-structure-your-sla-goals-around-priority-using-jql/
title: How to structure your SLA goals around priority using JQL | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:38.607915
---

# How to structure your SLA goals around priority using JQL

JQL stands for Jira Query Language and is the most powerful and flexible way to search for work items in your service project. Queries are created as simple elements strung together to form a more complex question.

With JQL, you can clearly define what kind of work items should make up an SLA goal. When creating or editing a goal, you'll see prompts to help you fill in the **Apply to work items** field in the correct JQL format. [Read more about grouping your SLAs by priority.](https://support.atlassian.com/jira-service-management-cloud/docs/use-priority-to-group-slas-early-access-feature/ "https://support.atlassian.com/jira-service-management-cloud/docs/use-priority-to-group-slas-early-access-feature/")

## An example goal structure to help improve your team’s service management

This structure helps keep things easy, simple, and straightforward. Since all work items belong to the same team, you can choose to create an SLA based on broad categories like incidents, service requests, problems, and changes.

This use case also has the most potential for granular configurations, since your service team doesn’t need to share the goal limit with any other teams.

![An example of an SLA goal configuration for one project per team](//images.ctfassets.net/zsv3d0ugroxu/BEelqOTTnvMnTiIQU3ktZ/94c2d39f53b137b3590dda6ec011261c/Screenshot_SLAexample1)

In this example we have have a simple JQL query matching `“Ticket category” = Incidents` with the 4 time targets underneath based on priority.

* High priority: 2 hour target
* Medium priority: 4 hour target
* Low priority: 8 hour target
* All remaining priorities: 16 hour target.

If a work item in the project matches `“Ticket category” = Incidents AND ”Priority” = High` it will display a time to resolution SLA of 2 hours.

For more information on JQL syntax, check out the article [Use advanced search with Jira Query Language](https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/ "https://support.atlassian.com/jira-service-management-cloud/docs/use-advanced-search-with-jira-query-language-jql/").

Was this helpful?

Yes

No

It wasn't accurateIt wasn't clearIt wasn't relevant

Provide feedback about this article

## Still need help?

The Atlassian Community is here for you.

[Ask the Community](https://community.atlassian.com/t5/custom/page/page-id/create-post-step-1?add-tags=jira-service-management,Cloud)

* [Use Jira Query Language to create service level agreements](/jira-service-management-cloud/docs/use-jira-query-language-jql-to-create-service-level-agreements-slas/)
* How to structure your SLA goals around priority using JQL
* [Write JQL queries for SLAs](/jira-service-management-cloud/docs/write-jql-queries-for-slas/)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
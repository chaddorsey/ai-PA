---
source_url: https://support.atlassian.com/jira-service-management-cloud/docs/jql-developer-status/
title: JQL developer status | Jira Service Management Cloud | Atlassian Support
crawled_at: 2025-12-31T11:49:40.128473
---

# JQL developer status

There are a few ways to find issues depending on the state of your development efforts in linked apps, for example, [Bitbucket](https://confluence.atlassian.com/bitbucket/connect-bitbucket-cloud-to-jira-software-cloud-814190686.html "https://confluence.atlassian.com/bitbucket/connect-bitbucket-cloud-to-jira-software-cloud-814190686.html").

**Before you begin**

The content on this page applies only if you have Jira Cloud connected to a build tool.

[How to connect Jira and Bitbucket](https://confluence.atlassian.com/bitbucket/connect-bitbucket-cloud-to-jira-software-cloud-814190686.html "https://confluence.atlassian.com/bitbucket/connect-bitbucket-cloud-to-jira-software-cloud-814190686.html")

## Source code searches

You can search for issues based on your development status:

* `development[pullrequests].all (or .open)`
* `development[commits].all`
* `development[reviews].all (or .open)`
* `development[builds].failing`

For example, if you wanted to find all your issues that have more than 2 failing builds, you would use:

`development[builds].failing > 2`

## Feature flags

| **Alias** | **Description** | **Values available** |
| --- | --- | --- |
| flagEnabledRollout ~ | for an enabled flag, how rolled out it is | * "partial" * "full" * "zero" |
| flagDisabledRollout ~ | how previously rolled out a currently disabled flag was | * "true" * "full" * "zero" |
| flagEnabled ~ | if the feature flag is enabled or not | * "true" * "false" |
| flagName ~ | shows feature flags with a specific name | "<name of flag>" |
| flagKey ~ | shows feature flags with a specific key | "<my flag key>" |

**Examples**

Show me all the issues that have a feature flag ON AND rollout is > 0% and < 100%:

`flagEnabledRollout ~ “partial”`

Show me all the issues that have a feature flag ON AND are at 100%:

`flagEnabledRollout ~ “full”`

Show me all the issues related to a flag that was rolled out to some people but is currently disabled:

`flagDisabledRollout ~ "partial"`

Show me issues connected to a feature flag called MakeEverythingBlue

`flagName ~ “MakeEverythingBlue“`

## Deployments

Note that these **do not** work for Bamboo deployments

| **Alias** | **Description** | **Values available** |
| --- | --- | --- |
| deploymentEnvironmentName ~ | The name of your deployment environment | "<my deployment name>" |
| deploymentEnvironmentType ~ | The type of environment | * “production“ * “staging“ * “testing“ * “development“ * “unmapped“ |
| deploymentState ~ | The current status of the deployment | * “pending” * “in\_progress” * “successful” * “cancelled” * “failed” * “rolled\_back” * “unknown” |
| deploymentName ~ | The name of the specific deployment | "<my deployment name>" |

**Examples**

Show me all the issues that have been deployed to the prod-east or stg-west environments:

`deploymentEnvironmentName ~ “prod-east“ OR deploymentEnvironmentName ~ “stg-west“`

Show me all the issues on my board that have been deployed to production but still have an open PR:

`deploymentEnvironmentType ~ “production“ AND development[pullrequests].open`

Show me all the issues that have a feature flag ON AND at 100% AND are deployed to production:

`flagEnabledRollout ~ “full“ AND deploymentEnvironmentType ~ “production“`

Show me all the issues that have not been deployed to production:

`deploymentEnvironmentType !~ “production“`

Show me all issues that have been deployed to a prod-east, that have a feature flag on which is only partially rolled out:

`deploymentEnvironmentName ~ “prod-east” AND flagEnabledRollout ~ “partial”`

## Builds

| Alias | Description | Values available |
| --- | --- | --- |
| buildState | The status of a build reported by a cloud provider, for example, Bitbucket Pipelines | * “pending“ * “in progress“ * “successful“ * “failed“ * “unknown“ |
| buildName | The name of a build reported by a cloud provider, for example, Bitbucket Pipelines | "<My build name>" |

**Examples**

Show me all the issues where the latest build failed:

`buildState ~ "failed"`

Show me all the issues on my board that have an open pull request and the last build failed:

`buildState ~ “FAILED“ AND development[pullrequests].open`

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
* [JQL functions](/jira-service-management-cloud/docs/jql-functions/)
* JQL developer status
* [JQL fields](/jira-service-management-cloud/docs/jql-fields/)
* [JQL keywords](/jira-service-management-cloud/docs/jql-keywords/)
* Show more

On this page[Source code searches](/jira-service-management-cloud/docs/jql-developer-status/#Source-code-searches)[Feature flags](/jira-service-management-cloud/docs/jql-developer-status/#Feature-flags)[Deployments](/jira-service-management-cloud/docs/jql-developer-status/#Deployments)[Builds](/jira-service-management-cloud/docs/jql-developer-status/#Builds)

Community[Questions, discussions, and articles](https://community.atlassian.com/t5/jira-service-management/ct-p/jira-service-desk)
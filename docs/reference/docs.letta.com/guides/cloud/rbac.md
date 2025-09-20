# Role-Based Access Control

> Manage team member permissions with granular role-based access control

<Note>
  Role-Based Access Control (RBAC) is an Enterprise feature that allows you to control what team members can access and modify within your organization. [Contact our team](https://forms.letta.com/request-demo) to learn more about Enterprise plans.
</Note>

Role-Based Access Control enables you to assign specific roles to team members, ensuring that each person has the appropriate level of access to your organization's resources. This helps maintain security and organization while allowing teams to collaborate effectively on agent development and deployment.

## Available Roles

Letta Cloud provides three preset roles with different levels of access, designed to match common team structures and responsibilities.

| Permission                                            | Analyst | Editor | Admin |
| :---------------------------------------------------- | :-----: | :----: | :---: |
| Read projects, agents, data sources, tools, templates |    â    |    â   |   â   |
| Message agents                                        |    â    |    â   |   â   |
| Create/update/delete projects and templates           |    â    |    â   |   â   |
| Create/update/delete agents                           |    â    |    â   |   â   |
| Create/update/delete data sources and tools           |    â    |    â   |   â   |
| Create/read API keys                                  |    â    |    â   |   â   |
| Update organization environment variables             |    â    |    â   |   â   |
| Delete API keys                                       |    â    |    â   |   â   |
| Manage users and organization settings                |    â    |    â   |   â   |
| Manage billing and integrations                       |    â    |    â   |   â   |

**Analyst** roles are perfect for team members who need to view and test agents but don't need to modify them. **Editor** roles are ideal for developers who actively work on building and maintaining agents. **Admin** roles provide full access including user management and billing.

## Managing Team Members

Organization admins can invite new team members through the organization settings page and assign them appropriate roles based on their responsibilities. User roles can be updated at any time as team members take on new responsibilities or change their involvement in projects.

When inviting users, consider their specific needs and responsibilities. Start with the principle of least privilege by assigning users the minimum permissions they need to perform their job functions effectively.

## Permission Enforcement

Permissions are automatically enforced across all API endpoints and the Letta Cloud interface. Users who lack the necessary permissions will receive a 401 Unauthorized response when attempting unauthorized actions through the API, and the interface will hide features they don't have access to.

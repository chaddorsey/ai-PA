# Migrate deployment to template version (Cloud-only)

POST https://api.letta.com/v1/templates/{project}/{template_name}/deployments/{deployment_id}/migrate
Content-Type: application/json

Migrates a deployment to a specific template version

## Examples

```shell
curl -X POST https://api.letta.com/v1/templates/project/template_name/deployments/deployment_id/migrate \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "version": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.migratedeployment(
    project="project",
    template_name="template_name",
    deployment_id="deployment_id",
    version="version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.migratedeployment("project", "template_name", "deployment_id", {
    version: "version"
});

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project/:template_name/deployments/:deployment_id/migrate \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "version": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.migratedeployment(
    project="project",
    template_name="template_name",
    deployment_id="deployment_id",
    version="version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.migratedeployment("project", "template_name", "deployment_id", {
    version: "version"
});

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project/:template_name/deployments/:deployment_id/migrate \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "version": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.migratedeployment(
    project="project",
    template_name="template_name",
    deployment_id="deployment_id",
    version="version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.migratedeployment("project", "template_name", "deployment_id", {
    version: "version"
});

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project/:template_name/deployments/:deployment_id/migrate \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "version": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.migratedeployment(
    project="project",
    template_name="template_name",
    deployment_id="deployment_id",
    version="version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.migratedeployment("project", "template_name", "deployment_id", {
    version: "version"
});

```
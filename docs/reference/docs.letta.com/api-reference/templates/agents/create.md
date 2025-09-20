# Create agents from a template (Cloud-only)

POST https://api.letta.com/v1/templates/{project}/{template_version}/agents
Content-Type: application/json

Creates an Agent or multiple Agents from a template

## Examples

```shell
curl -X POST https://api.letta.com/v1/templates/project/template_version/agents \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.agents.create(
    project="project",
    template_version="template_version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.agents.create("project", "template_version");

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project/:template_version/agents \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.agents.create(
    project="project",
    template_version="template_version",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.agents.create("project", "template_version");

```
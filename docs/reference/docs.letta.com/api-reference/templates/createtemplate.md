# Create template (Cloud-only)

POST https://api.letta.com/v1/templates/{project}
Content-Type: application/json

Creates a new template from an existing agent or agent file

## Examples

```shell
curl -X POST https://api.letta.com/v1/templates/project \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "type": "agent",
  "agent_id": "string"
}'
```

```python
from letta_client import Letta
from letta_client.templates import TemplatesCreateTemplateRequestAgentId

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.createtemplate(
    project="project",
    request=TemplatesCreateTemplateRequestAgentId(
        agent_id="agent_id",
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.createtemplate("project", {
    type: "agent",
    agentId: "agent_id"
});

```

```shell
curl -X POST https://api.letta.com/v1/templates/:project \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "type": "agent",
  "agent_id": "string"
}'
```

```python
from letta_client import Letta
from letta_client.templates import TemplatesCreateTemplateRequestAgentId

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.templates.createtemplate(
    project="project",
    request=TemplatesCreateTemplateRequestAgentId(
        agent_id="agent_id",
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.templates.createtemplate("project", {
    type: "agent",
    agentId: "agent_id"
});

```
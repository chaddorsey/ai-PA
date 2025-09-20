# Migrate Agent

POST https://api.letta.com/v1/agents/{agent_id}/migrate
Content-Type: application/json

<Note>This endpoint is only available on Letta Cloud.</Note>

Migrate an agent to a new versioned agent template.


## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/migrate \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "to_template": "string",
  "preserve_core_memories": true
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.templates.migrate(
    agent_id="agent_id",
    to_template="to_template",
    preserve_core_memories=True,
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.templates.migrate("agent_id", {
    toTemplate: "to_template",
    preserveCoreMemories: true
});

```
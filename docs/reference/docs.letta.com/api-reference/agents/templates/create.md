# Create

POST https://api.letta.com/v1/agents/{agent_id}/template

<Note>This endpoint is only available on Letta Cloud.</Note>

Creates a template from an agent.


## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/template \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.templates.create(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.templates.create("agent_id");

```
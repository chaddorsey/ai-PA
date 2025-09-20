# Create Version

POST https://api.letta.com/v1/agents/{agent_id}/version-template

<Note>This endpoint is only available on Letta Cloud.</Note>

Creates a new version of the template version of the agent.


## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/version-template \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.templates.create_version(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.templates.createVersion("agent_id");

```
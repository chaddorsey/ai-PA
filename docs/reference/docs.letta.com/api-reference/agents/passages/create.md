# Create Passage

POST https://api.letta.com/v1/agents/{agent_id}/archival-memory
Content-Type: application/json

Insert a memory into an agent's archival memory store.

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/archival-memory \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "text": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.create(
    agent_id="agent_id",
    text="text",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.create("agent_id", {
    text: "text"
});

```

```shell
curl -X POST https://api.letta.com/v1/agents/:agent_id/archival-memory \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "text": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.passages.create(
    agent_id="agent_id",
    text="text",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.passages.create("agent_id", {
    text: "text"
});

```
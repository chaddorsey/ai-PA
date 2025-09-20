# Create Group

POST https://api.letta.com/v1/groups/
Content-Type: application/json

Create a new multi-agent group with the specified configuration.

## Examples

```shell
curl -X POST https://api.letta.com/v1/groups/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "agent_ids": [
    "string"
  ],
  "description": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.create(
    agent_ids=["agent_ids"],
    description="description",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.create({
    agentIds: ["agent_ids"],
    description: "description"
});

```

```shell
curl -X POST https://api.letta.com/v1/groups/ \
     -H "X-Project: string" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "agent_ids": [
    "string"
  ],
  "description": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.create(
    agent_ids=["agent_ids"],
    description="description",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.create({
    agentIds: ["agent_ids"],
    description: "description"
});

```
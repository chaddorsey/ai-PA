# Retrieve Agent

GET https://api.letta.com/v1/agents/{agent_id}

Get the state of the agent.

## Examples

```shell
curl https://api.letta.com/v1/agents/agent_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.retrieve(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.retrieve("agent_id");

```

```shell
curl -G https://api.letta.com/v1/agents/:agent_id \
     -H "Authorization: Bearer <token>" \
     -d include_relationships=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.retrieve(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.retrieve("agent_id");

```
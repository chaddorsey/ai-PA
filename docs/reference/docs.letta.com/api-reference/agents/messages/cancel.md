# Cancel Agent Run

POST https://api.letta.com/v1/agents/{agent_id}/messages/cancel
Content-Type: application/json

Cancel runs associated with an agent. If run_ids are passed in, cancel those in particular.

Note to cancel active runs associated with an agent, redis is required.

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/messages/cancel \
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
client.agents.messages.cancel(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.cancel("agent_id");

```

```shell
curl -X POST https://api.letta.com/v1/agents/:agent_id/messages/cancel \
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
client.agents.messages.cancel(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.cancel("agent_id");

```
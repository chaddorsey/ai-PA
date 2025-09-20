# Reset Messages

PATCH https://api.letta.com/v1/agents/{agent_id}/reset-messages

Resets the messages for an agent

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/agents/agent_id/reset-messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.reset(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.reset("agent_id");

```

```shell
curl -X PATCH "https://api.letta.com/v1/agents/:agent_id/reset-messages?add_default_initial_messages=true" \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.reset(
    agent_id="agent_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.reset("agent_id");

```
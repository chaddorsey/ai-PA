# Summarize Agent Conversation

POST https://api.letta.com/v1/agents/{agent_id}/summarize

Summarize an agent's conversation history to a target message length.

This endpoint summarizes the current message history for a given agent,
truncating and compressing it down to the specified `max_message_length`.

## Examples

```shell
curl -X POST "https://api.letta.com/v1/agents/agent_id/summarize?max_message_length=1" \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.summarize(
    agent_id="agent_id",
    max_message_length=1,
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.summarize("agent_id", {
    maxMessageLength: 1
});

```

```shell
curl -X POST "https://api.letta.com/v1/agents/:agent_id/summarize?max_message_length=0" \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.summarize(
    agent_id="agent_id",
    max_message_length=1,
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.summarize("agent_id", {
    maxMessageLength: 1
});

```
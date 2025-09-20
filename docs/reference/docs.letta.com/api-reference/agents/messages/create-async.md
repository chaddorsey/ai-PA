# Send Message Async

POST https://api.letta.com/v1/agents/{agent_id}/messages/async
Content-Type: application/json

Asynchronously process a user message and return a run object.
The actual processing happens in the background, and the status can be checked using the run ID.

This is "asynchronous" in the sense that it's a background job and explicitly must be fetched by the run ID.
This is more like `send_message_job`

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/messages/async \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "messages": [
    {
      "role": "user",
      "content": [
        {}
      ]
    }
  ]
}'
```

```python
from letta_client import Letta, MessageCreate, TextContent

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.create_async(
    agent_id="agent_id",
    messages=[
        MessageCreate(
            role="user",
            content=[
                TextContent(
                    text="text",
                )
            ],
        )
    ],
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.createAsync("agent_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "text"
                }]
        }]
});

```

```shell
curl -X POST https://api.letta.com/v1/agents/:agent_id/messages/async \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "text": "string"
        }
      ]
    }
  ]
}'
```

```python
from letta_client import Letta, MessageCreate, TextContent

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.create_async(
    agent_id="agent_id",
    messages=[
        MessageCreate(
            role="user",
            content=[
                TextContent(
                    text="text",
                )
            ],
        )
    ],
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.createAsync("agent_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "text"
                }]
        }]
});

```
# Preview Raw Payload

POST https://api.letta.com/v1/agents/{agent_id}/messages/preview-raw-payload
Content-Type: application/json

Inspect the raw LLM request payload without sending it.

This endpoint processes the message through the agent loop up until
the LLM request, then returns the raw request payload that would
be sent to the LLM provider. Useful for debugging and inspection.

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/messages/preview-raw-payload \
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
from letta_client import Letta, LettaRequest, MessageCreate, TextContent

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.preview(
    agent_id="agent_id",
    request=LettaRequest(
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
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.preview("agent_id", {
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
curl -X POST https://api.letta.com/v1/agents/:agent_id/messages/preview-raw-payload \
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
from letta_client import Letta, LettaRequest, MessageCreate, TextContent

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.agents.messages.preview(
    agent_id="agent_id",
    request=LettaRequest(
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
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.agents.messages.preview("agent_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "text"
                }]
        }]
});

```
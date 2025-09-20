# Send Message Streaming

POST https://api.letta.com/v1/agents/{agent_id}/messages/stream
Content-Type: application/json

Process a user message and return the agent's response.
This endpoint accepts a message from a user and processes it through the agent.
It will stream the steps of the response always, and stream the tokens if 'stream_tokens' is set to True.

## Examples

```shell
curl -X POST https://api.letta.com/v1/agents/agent_id/messages/stream \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "The sky above the port was the color of television, tuned to a dead channel."
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
response = client.agents.messages.create_stream(
    agent_id="agent_id",
    messages=[
        MessageCreate(
            role="user",
            content=[
                TextContent(
                    text="The sky above the port was the color of television, tuned to a dead channel.",
                )
            ],
        )
    ],
)
for chunk in response.data:
    yield chunk

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
const response = await client.agents.messages.createStream("agent_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "The sky above the port was the color of television, tuned to a dead channel."
                }]
        }]
});
for await (const item of response) {
    console.log(item);
}

```

```shell
curl -X POST https://api.letta.com/v1/agents/:agent_id/messages/stream \
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
response = client.agents.messages.create_stream(
    agent_id="agent_id",
    messages=[
        MessageCreate(
            role="user",
            content=[
                TextContent(
                    text="The sky above the port was the color of television, tuned to a dead channel.",
                )
            ],
        )
    ],
)
for chunk in response.data:
    yield chunk

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
const response = await client.agents.messages.createStream("agent_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "The sky above the port was the color of television, tuned to a dead channel."
                }]
        }]
});
for await (const item of response) {
    console.log(item);
}

```
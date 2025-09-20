# Create Batch

POST https://api.letta.com/v1/messages/batches
Content-Type: application/json

Submit a batch of agent runs for asynchronous processing.

Creates a job that will fan out messages to all listed agents and process them in parallel.
The request will be rejected if it exceeds 256MB.

## Examples

```shell
curl -X POST https://api.letta.com/v1/messages/batches \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "requests": [
    {
      "messages": [
        {
          "role": "user",
          "content": [
            {}
          ]
        }
      ],
      "agent_id": "string"
    }
  ]
}'
```

```python
from letta_client import Letta, LettaBatchRequest, MessageCreate, TextContent

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.create(
    requests=[
        LettaBatchRequest(
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
            agent_id="agent_id",
        )
    ],
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.create({
    requests: [{
            messages: [{
                    role: "user",
                    content: [{
                            type: "text",
                            text: "text"
                        }]
                }],
            agentId: "agent_id"
        }]
});

```

```shell
curl -X POST https://api.letta.com/v1/messages/batches \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "requests": [
    {
      "messages": [
        {
          "role": "user",
          "content": [
            {
              "text": "string"
            }
          ]
        }
      ],
      "agent_id": "string"
    }
  ]
}'
```

```python
from letta_client import Letta, LettaBatchRequest, MessageCreate, TextContent

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.batches.create(
    requests=[
        LettaBatchRequest(
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
            agent_id="agent_id",
        )
    ],
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.batches.create({
    requests: [{
            messages: [{
                    role: "user",
                    content: [{
                            type: "text",
                            text: "text"
                        }]
                }],
            agentId: "agent_id"
        }]
});

```
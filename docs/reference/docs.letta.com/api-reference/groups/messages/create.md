# Send Message To Group

POST https://api.letta.com/v1/groups/{group_id}/messages
Content-Type: application/json

Process a user message and return the group's response.
This endpoint accepts a message from a user and processes it through through agents in the group based on the specified pattern

## Examples

```shell
curl -X POST https://api.letta.com/v1/groups/group_id/messages \
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
client.groups.messages.create(
    group_id="group_id",
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

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.create("group_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "The sky above the port was the color of television, tuned to a dead channel."
                }]
        }]
});

```

```shell
curl -X POST https://api.letta.com/v1/groups/:group_id/messages \
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
client.groups.messages.create(
    group_id="group_id",
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

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.create("group_id", {
    messages: [{
            role: "user",
            content: [{
                    type: "text",
                    text: "The sky above the port was the color of television, tuned to a dead channel."
                }]
        }]
});

```
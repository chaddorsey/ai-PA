# Modify Message For Group

PATCH https://api.letta.com/v1/groups/{group_id}/messages/{message_id}
Content-Type: application/json

Update the details of a message associated with an agent.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/groups/group_id/messages/message_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "content": "string"
}'
```

```python
from letta_client import Letta, UpdateSystemMessage

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.messages.modify(
    group_id="group_id",
    message_id="message_id",
    request=UpdateSystemMessage(
        content="content",
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.modify("group_id", "message_id", {
    content: "content"
});

```

```shell
curl -X PATCH https://api.letta.com/v1/groups/:group_id/messages/:message_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "content": "string"
}'
```

```python
from letta_client import Letta, UpdateSystemMessage

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.messages.modify(
    group_id="group_id",
    message_id="message_id",
    request=UpdateSystemMessage(
        content="content",
    ),
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.modify("group_id", "message_id", {
    content: "content"
});

```
# Reset Messages For Group

PATCH https://api.letta.com/v1/groups/{group_id}/reset-messages

Delete the group messages for all agents that are part of the multi-agent group.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/groups/group_id/reset-messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.messages.reset(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.reset("group_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/groups/:group_id/reset-messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.messages.reset(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.reset("group_id");

```
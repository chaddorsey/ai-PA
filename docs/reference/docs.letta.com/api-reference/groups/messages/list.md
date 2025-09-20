# List Messages For Group

GET https://api.letta.com/v1/groups/{group_id}/messages

Retrieve message history for an agent.

## Examples

```shell
curl https://api.letta.com/v1/groups/group_id/messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.messages.list(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.list("group_id");

```

```shell
curl -G https://api.letta.com/v1/groups/:group_id/messages \
     -H "Authorization: Bearer <token>" \
     -d before=string \
     -d after=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.messages.list(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.messages.list("group_id");

```
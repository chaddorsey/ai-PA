# Delete Group

DELETE https://api.letta.com/v1/groups/{group_id}

Delete a multi-agent group.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/groups/group_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.delete(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.delete("group_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/groups/:group_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.delete(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.delete("group_id");

```
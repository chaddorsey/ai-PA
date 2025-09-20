# Modify Group

PATCH https://api.letta.com/v1/groups/{group_id}
Content-Type: application/json

Create a new multi-agent group with the specified configuration.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/groups/group_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.modify(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.modify("group_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/groups/:group_id \
     -H "X-Project: string" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.modify(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.modify("group_id");

```
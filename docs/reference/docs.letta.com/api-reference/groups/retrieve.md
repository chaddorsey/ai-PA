# Retrieve Group

GET https://api.letta.com/v1/groups/{group_id}

Retrieve the group by id.

## Examples

```shell
curl https://api.letta.com/v1/groups/group_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.retrieve(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.retrieve("group_id");

```

```shell
curl https://api.letta.com/v1/groups/:group_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.retrieve(
    group_id="group_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.retrieve("group_id");

```
# List Blocks For Identity

GET https://api.letta.com/v1/identities/{identity_id}/blocks

Get all blocks associated with the specified identity.

## Examples

```shell
curl https://api.letta.com/v1/identities/identity_id/blocks \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.blocks.list(
    identity_id="identity_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.blocks.list("identity_id");

```

```shell
curl -G https://api.letta.com/v1/identities/:identity_id/blocks \
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
client.identities.blocks.list(
    identity_id="identity_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.blocks.list("identity_id");

```
# Delete Identity

DELETE https://api.letta.com/v1/identities/{identity_id}

Delete an identity by its identifier key

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/identities/identity_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.delete(
    identity_id="identity_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.delete("identity_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/identities/:identity_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.delete(
    identity_id="identity_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.delete("identity_id");

```
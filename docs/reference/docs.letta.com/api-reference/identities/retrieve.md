# Retrieve Identity

GET https://api.letta.com/v1/identities/{identity_id}

## Examples

```shell
curl https://api.letta.com/v1/identities/identity_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.retrieve(
    identity_id="identity_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.retrieve("identity_id");

```

```shell
curl https://api.letta.com/v1/identities/:identity_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.retrieve(
    identity_id="identity_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.retrieve("identity_id");

```
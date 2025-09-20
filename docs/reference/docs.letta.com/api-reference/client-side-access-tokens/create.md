# Create token  (Cloud-only)

POST https://api.letta.com/v1/client-side-access-tokens
Content-Type: application/json

Create a new client side access token with the specified configuration.

## Examples

```shell
curl -X POST https://api.letta.com/v1/client-side-access-tokens \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "policy": [
    {
      "type": "agent",
      "id": "string",
      "access": [
        "read_messages"
      ]
    }
  ],
  "hostname": "string"
}'
```

```python
from letta_client import Letta
from letta_client.client_side_access_tokens import (
    ClientSideAccessTokensCreateRequestPolicyItem,
)

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.client_side_access_tokens.create(
    policy=[
        ClientSideAccessTokensCreateRequestPolicyItem(
            id="id",
            access=["read_messages"],
        )
    ],
    hostname="hostname",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.clientSideAccessTokens.create({
    policy: [{
            type: "agent",
            id: "id",
            access: ["read_messages"]
        }],
    hostname: "hostname"
});

```

```shell
curl -X POST https://api.letta.com/v1/client-side-access-tokens \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "policy": [
    {
      "type": "agent",
      "id": "string",
      "access": [
        "read_messages"
      ]
    }
  ],
  "hostname": "string"
}'
```

```python
from letta_client import Letta
from letta_client.client_side_access_tokens import (
    ClientSideAccessTokensCreateRequestPolicyItem,
)

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.client_side_access_tokens.create(
    policy=[
        ClientSideAccessTokensCreateRequestPolicyItem(
            id="id",
            access=["read_messages"],
        )
    ],
    hostname="hostname",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.clientSideAccessTokens.create({
    policy: [{
            type: "agent",
            id: "id",
            access: ["read_messages"]
        }],
    hostname: "hostname"
});

```
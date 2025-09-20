# Upsert Properties For Identity

PUT https://api.letta.com/v1/identities/{identity_id}/properties
Content-Type: application/json

## Examples

```shell
curl -X PUT https://api.letta.com/v1/identities/identity_id/properties \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '[
  {
    "key": "string",
    "value": {},
    "type": "string"
  }
]'
```

```python
from letta_client import IdentityProperty, Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.properties.upsert(
    identity_id="identity_id",
    request=[
        IdentityProperty(
            key="key",
            value="value",
            type="string",
        )
    ],
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.properties.upsert("identity_id", [{
        key: "key",
        value: "value",
        type: "string"
    }]);

```

```shell
curl -X PUT https://api.letta.com/v1/identities/:identity_id/properties \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '[
  {
    "key": "string",
    "value": "string",
    "type": "string"
  }
]'
```

```python
from letta_client import IdentityProperty, Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.properties.upsert(
    identity_id="identity_id",
    request=[
        IdentityProperty(
            key="key",
            value="value",
            type="string",
        )
    ],
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.properties.upsert("identity_id", [{
        key: "key",
        value: "value",
        type: "string"
    }]);

```
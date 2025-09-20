# Create Identity

POST https://api.letta.com/v1/identities/
Content-Type: application/json

## Examples

```shell
curl -X POST https://api.letta.com/v1/identities/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "identifier_key": "string",
  "name": "string",
  "identity_type": "org"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.create(
    identifier_key="identifier_key",
    name="name",
    identity_type="org",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.create({
    identifierKey: "identifier_key",
    name: "name",
    identityType: "org"
});

```

```shell
curl -X POST https://api.letta.com/v1/identities/ \
     -H "X-Project: string" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "identifier_key": "string",
  "name": "string",
  "identity_type": "org"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.create(
    identifier_key="identifier_key",
    name="name",
    identity_type="org",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.create({
    identifierKey: "identifier_key",
    name: "name",
    identityType: "org"
});

```
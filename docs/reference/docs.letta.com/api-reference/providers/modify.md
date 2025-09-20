# Modify Provider

PATCH https://api.letta.com/v1/providers/{provider_id}
Content-Type: application/json

Update an existing custom provider.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/providers/provider_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "api_key": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.modify(
    provider_id="provider_id",
    api_key="api_key",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.modify("provider_id", {
    apiKey: "api_key"
});

```

```shell
curl -X PATCH https://api.letta.com/v1/providers/:provider_id \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "api_key": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.modify(
    provider_id="provider_id",
    api_key="api_key",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.modify("provider_id", {
    apiKey: "api_key"
});

```
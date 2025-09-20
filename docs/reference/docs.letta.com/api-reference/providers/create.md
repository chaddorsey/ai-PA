# Create Provider

POST https://api.letta.com/v1/providers/
Content-Type: application/json

Create a new custom provider.

## Examples

```shell
curl -X POST https://api.letta.com/v1/providers/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "name": "string",
  "provider_type": "anthropic",
  "api_key": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.create(
    name="name",
    provider_type="anthropic",
    api_key="api_key",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.create({
    name: "name",
    providerType: "anthropic",
    apiKey: "api_key"
});

```

```shell
curl -X POST https://api.letta.com/v1/providers/ \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
  "name": "string",
  "provider_type": "anthropic",
  "api_key": "string"
}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.create(
    name="name",
    provider_type="anthropic",
    api_key="api_key",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.create({
    name: "name",
    providerType: "anthropic",
    apiKey: "api_key"
});

```
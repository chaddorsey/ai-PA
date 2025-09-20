# Check Provider

POST https://api.letta.com/v1/providers/check
Content-Type: application/json

Verify the API key and additional parameters for a provider.

## Examples

```shell
curl -X POST https://api.letta.com/v1/providers/check \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
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
client.providers.check(
    provider_type="anthropic",
    api_key="api_key",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.check({
    providerType: "anthropic",
    apiKey: "api_key"
});

```

```shell
curl -X POST https://api.letta.com/v1/providers/check \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
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
client.providers.check(
    provider_type="anthropic",
    api_key="api_key",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.check({
    providerType: "anthropic",
    apiKey: "api_key"
});

```
# Retrieve Provider

GET https://api.letta.com/v1/providers/{provider_id}

Get a provider by ID.

## Examples

```shell
curl https://api.letta.com/v1/providers/provider_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.retrieve_provider(
    provider_id="provider_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.retrieveProvider("provider_id");

```

```shell
curl https://api.letta.com/v1/providers/:provider_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.retrieve_provider(
    provider_id="provider_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.retrieveProvider("provider_id");

```
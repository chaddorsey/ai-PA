# Delete Provider

DELETE https://api.letta.com/v1/providers/{provider_id}

Delete an existing custom provider.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/providers/provider_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.delete(
    provider_id="provider_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.delete("provider_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/providers/:provider_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.providers.delete(
    provider_id="provider_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.providers.delete("provider_id");

```
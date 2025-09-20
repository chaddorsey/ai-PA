# Delete token  (Cloud-only)

DELETE https://api.letta.com/v1/client-side-access-tokens/{token}
Content-Type: application/json

Delete a client side access token.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/client-side-access-tokens/token \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.client_side_access_tokens.delete(
    token="token",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.clientSideAccessTokens.delete("token", {
    "key": "value"
});

```

```shell
curl -X DELETE https://api.letta.com/v1/client-side-access-tokens/:token \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.client_side_access_tokens.delete(
    token="token",
    request={"key": "value"},
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.clientSideAccessTokens.delete("token", {
    "key": "value"
});

```
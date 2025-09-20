# List tokens  (Cloud-only)

GET https://api.letta.com/v1/client-side-access-tokens

List all client side access tokens for the current account. This is only available for cloud users.

## Examples

```shell
curl https://api.letta.com/v1/client-side-access-tokens \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.client_side_access_tokens.client_side_access_tokens_list_client_side_access_tokens()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.clientSideAccessTokens.clientSideAccessTokensListClientSideAccessTokens();

```

```shell
curl -G https://api.letta.com/v1/client-side-access-tokens \
     -H "Authorization: Bearer <token>" \
     -d agentId=string \
     -d offset=1
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.client_side_access_tokens.client_side_access_tokens_list_client_side_access_tokens()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.clientSideAccessTokens.clientSideAccessTokensListClientSideAccessTokens();

```
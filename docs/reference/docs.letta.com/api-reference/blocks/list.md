# List Blocks

GET https://api.letta.com/v1/blocks/

## Examples

```shell
curl https://api.letta.com/v1/blocks/ \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.list();

```

```shell
curl -G https://api.letta.com/v1/blocks/ \
     -H "Authorization: Bearer <token>" \
     -d label=string \
     -d templates_only=true
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.blocks.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.blocks.list();

```
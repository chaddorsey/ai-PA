# List Groups

GET https://api.letta.com/v1/groups/

Fetch all multi-agent groups matching query.

## Examples

```shell
curl https://api.letta.com/v1/groups/ \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.list();

```

```shell
curl -G https://api.letta.com/v1/groups/ \
     -H "Authorization: Bearer <token>" \
     -d manager_type=round_robin \
     -d before=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.groups.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.groups.list();

```
# List Identities

GET https://api.letta.com/v1/identities/

Get a list of all identities in the database

## Examples

```shell
curl https://api.letta.com/v1/identities/ \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.list();

```

```shell
curl -G https://api.letta.com/v1/identities/ \
     -H "Authorization: Bearer <token>" \
     -d name=string \
     -d project_id=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.identities.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.identities.list();

```
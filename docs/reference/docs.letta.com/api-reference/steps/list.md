# List Steps

GET https://api.letta.com/v1/steps/

List steps with optional pagination and date filters.

## Examples

```shell
curl https://api.letta.com/v1/steps/ \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.list();

```

```shell
curl -G https://api.letta.com/v1/steps/ \
     -H "X-Project: string" \
     -H "Authorization: Bearer <token>" \
     -d before=string \
     -d after=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.list();

```
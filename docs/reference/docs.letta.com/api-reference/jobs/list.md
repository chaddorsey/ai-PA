# List Jobs

GET https://api.letta.com/v1/jobs/

List all jobs.

## Examples

```shell
curl https://api.letta.com/v1/jobs/ \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.list();

```

```shell
curl -G https://api.letta.com/v1/jobs/ \
     -H "Authorization: Bearer <token>" \
     -d source_id=string \
     -d before=string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.list()

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.list();

```
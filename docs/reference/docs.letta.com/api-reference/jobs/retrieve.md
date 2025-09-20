# Retrieve Job

GET https://api.letta.com/v1/jobs/{job_id}

Get the status of a job.

## Examples

```shell
curl https://api.letta.com/v1/jobs/job_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.retrieve(
    job_id="job_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.retrieve("job_id");

```

```shell
curl https://api.letta.com/v1/jobs/:job_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.retrieve(
    job_id="job_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.retrieve("job_id");

```
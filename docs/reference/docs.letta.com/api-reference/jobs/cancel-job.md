# Cancel Job

PATCH https://api.letta.com/v1/jobs/{job_id}/cancel

Cancel a job by its job_id.

This endpoint marks a job as cancelled, which will cause any associated
agent execution to terminate as soon as possible.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/jobs/job_id/cancel \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.cancel_job(
    job_id="job_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.cancelJob("job_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/jobs/:job_id/cancel \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.cancel_job(
    job_id="job_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.cancelJob("job_id");

```
# Delete Job

DELETE https://api.letta.com/v1/jobs/{job_id}

Delete a job by its job_id.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/jobs/job_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.delete(
    job_id="job_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.delete("job_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/jobs/:job_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.jobs.delete(
    job_id="job_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.jobs.delete("job_id");

```
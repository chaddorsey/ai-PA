# Retrieve Metrics For Step

GET https://api.letta.com/v1/steps/{step_id}/metrics

Get step metrics by step ID.

## Examples

```shell
curl https://api.letta.com/v1/steps/step_id/metrics \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.metrics.retrieve(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.metrics.retrieve("step_id");

```

```shell
curl https://api.letta.com/v1/steps/:step_id/metrics \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.metrics.retrieve(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.metrics.retrieve("step_id");

```
# Retrieve Trace For Step

GET https://api.letta.com/v1/steps/{step_id}/trace

## Examples

```shell
curl https://api.letta.com/v1/steps/step_id/trace \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.trace.retrieve(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.trace.retrieve("step_id");

```

```shell
curl https://api.letta.com/v1/steps/:step_id/trace \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.trace.retrieve(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.trace.retrieve("step_id");

```
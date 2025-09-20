# Retrieve Provider Trace

GET https://api.letta.com/v1/telemetry/{step_id}

**DEPRECATED**: Use `GET /steps/{step_id}/trace` instead.

Retrieve provider trace by step ID.

## Examples

```shell
curl https://api.letta.com/v1/telemetry/step_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.telemetry.retrieve_provider_trace(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.telemetry.retrieveProviderTrace("step_id");

```

```shell
curl https://api.letta.com/v1/telemetry/:step_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.telemetry.retrieve_provider_trace(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.telemetry.retrieveProviderTrace("step_id");

```
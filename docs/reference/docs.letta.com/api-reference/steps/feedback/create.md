# Modify Feedback For Step

PATCH https://api.letta.com/v1/steps/{step_id}/feedback
Content-Type: application/json

Modify feedback for a given step.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/steps/step_id/feedback \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.feedback.create(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.feedback.create("step_id");

```

```shell
curl -X PATCH https://api.letta.com/v1/steps/:step_id/feedback \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{}'
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.feedback.create(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.feedback.create("step_id");

```
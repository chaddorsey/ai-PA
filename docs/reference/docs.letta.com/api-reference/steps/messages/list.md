# List Messages For Step

GET https://api.letta.com/v1/steps/{step_id}/messages

List messages for a given step.

## Examples

```shell
curl https://api.letta.com/v1/steps/step_id/messages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.steps.messages.list(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.messages.list("step_id");

```

```shell
curl -G https://api.letta.com/v1/steps/:step_id/messages \
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
client.steps.messages.list(
    step_id="step_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.steps.messages.list("step_id");

```
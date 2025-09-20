# Retrieve Stream

POST https://api.letta.com/v1/runs/{run_id}/stream
Content-Type: application/json

## Examples

```shell
curl -X POST https://api.letta.com/v1/runs/run_id/stream \
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
response = client.runs.stream(
    run_id="run_id",
)
for chunk in response.data:
    yield chunk

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
const response = await client.runs.stream("run_id");
for await (const item of response) {
    console.log(item);
}

```

```shell
curl -X POST https://api.letta.com/v1/runs/:run_id/stream \
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
response = client.runs.stream(
    run_id="run_id",
)
for chunk in response.data:
    yield chunk

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
const response = await client.runs.stream("run_id");
for await (const item of response) {
    console.log(item);
}

```
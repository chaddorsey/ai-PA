# List Steps For Run

GET https://api.letta.com/v1/runs/{run_id}/steps

Get messages associated with a run with filtering options.

Args:
    run_id: ID of the run
    before: A cursor for use in pagination. `before` is an object ID that defines your place in the list. For instance, if you make a list request and receive 100 objects, starting with obj_foo, your subsequent call can include before=obj_foo in order to fetch the previous page of the list.
    after: A cursor for use in pagination. `after` is an object ID that defines your place in the list. For instance, if you make a list request and receive 100 objects, ending with obj_foo, your subsequent call can include after=obj_foo in order to fetch the next page of the list.
    limit: Maximum number of steps to return
    order: Sort order by the created_at timestamp of the objects. asc for ascending order and desc for descending order.

Returns:
    A list of steps associated with the run.

## Examples

```shell
curl https://api.letta.com/v1/runs/run_id/steps \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.runs.steps.list(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.steps.list("run_id");

```

```shell
curl -G https://api.letta.com/v1/runs/:run_id/steps \
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
client.runs.steps.list(
    run_id="run_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.runs.steps.list("run_id");

```
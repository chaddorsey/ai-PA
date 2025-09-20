# Modify Folder

PATCH https://api.letta.com/v1/folders/{folder_id}
Content-Type: application/json

Update the name or documentation of an existing data folder.

## Examples

```shell
curl -X PATCH https://api.letta.com/v1/folders/folder_id \
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
client.folders.modify(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.modify("folder_id", {});

```

```shell
curl -X PATCH https://api.letta.com/v1/folders/:folder_id \
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
client.folders.modify(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient, Letta } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.modify("folder_id", {});

```
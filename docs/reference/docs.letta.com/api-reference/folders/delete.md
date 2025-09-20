# Delete Folder

DELETE https://api.letta.com/v1/folders/{folder_id}

Delete a data folder.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/folders/folder_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.delete(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.delete("folder_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/folders/:folder_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.delete(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.delete("folder_id");

```
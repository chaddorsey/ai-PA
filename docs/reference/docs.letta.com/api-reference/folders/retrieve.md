# Retrieve Folder

GET https://api.letta.com/v1/folders/{folder_id}

Get a folder by ID

## Examples

```shell
curl https://api.letta.com/v1/folders/folder_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.retrieve(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.retrieve("folder_id");

```

```shell
curl https://api.letta.com/v1/folders/:folder_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.retrieve(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.retrieve("folder_id");

```
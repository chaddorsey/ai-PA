# Get Folder By Name

GET https://api.letta.com/v1/folders/name/{folder_name}

**Deprecated**: Please use the list endpoint `GET /v1/folders?name=` instead.


Get a folder by name.

## Examples

```shell
curl https://api.letta.com/v1/folders/name/folder_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.retrieve_by_name(
    folder_name="folder_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.retrieveByName("folder_name");

```

```shell
curl https://api.letta.com/v1/folders/name/:folder_name \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.retrieve_by_name(
    folder_name="folder_name",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.retrieveByName("folder_name");

```
# List Passages For Folder

GET https://api.letta.com/v1/folders/{folder_id}/passages

List all passages associated with a data folder.

## Examples

```shell
curl https://api.letta.com/v1/folders/folder_id/passages \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.passages.list(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.passages.list("folder_id");

```

```shell
curl -G https://api.letta.com/v1/folders/:folder_id/passages \
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
client.folders.passages.list(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.passages.list("folder_id");

```
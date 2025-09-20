# Delete File From Folder

DELETE https://api.letta.com/v1/folders/{folder_id}/{file_id}

Delete a file from a folder.

## Examples

```shell
curl -X DELETE https://api.letta.com/v1/folders/folder_id/file_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.files.delete(
    folder_id="folder_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.files.delete("folder_id", "file_id");

```

```shell
curl -X DELETE https://api.letta.com/v1/folders/:folder_id/:file_id \
     -H "Authorization: Bearer <token>"
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.files.delete(
    folder_id="folder_id",
    file_id="file_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.files.delete("folder_id", "file_id");

```
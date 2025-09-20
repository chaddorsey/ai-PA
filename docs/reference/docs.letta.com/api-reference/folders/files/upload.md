# Upload File To Folder

POST https://api.letta.com/v1/folders/{folder_id}/upload
Content-Type: multipart/form-data

Upload a file to a data folder.

## Examples

```shell
curl -X POST https://api.letta.com/v1/folders/folder_id/upload \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: multipart/form-data" \
     -F file=@string
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.files.upload(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";
import * as fs from "fs";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.files.upload(fs.createReadStream("/path/to/your/file"), "folder_id", {});

```

```shell
curl -X POST "https://api.letta.com/v1/folders/:folder_id/upload?duplicate_handling=skip&name=string" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: multipart/form-data" \
     -F file=@<filename1>
```

```python
from letta_client import Letta

client = Letta(
    project="YOUR_PROJECT",
    token="YOUR_TOKEN",
)
client.folders.files.upload(
    folder_id="folder_id",
)

```

```typescript
import { LettaClient } from "@letta-ai/letta-client";
import * as fs from "fs";

const client = new LettaClient({ token: "YOUR_TOKEN", project: "YOUR_PROJECT" });
await client.folders.files.upload(fs.createReadStream("/path/to/your/file"), "folder_id", {});

```
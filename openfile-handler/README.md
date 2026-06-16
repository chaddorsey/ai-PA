# OpenFileHandler

A macOS URL-scheme handler that opens local files via `openfile://` links. Used by
the work-packet system to provide offline access to staged resource copies.

## Installation

Run the install script on any Mac where you want `openfile://` links to resolve:

```bash
bash openfile-handler/install.sh
```

This builds `OpenFileHandler.app` from `main.swift` and places it in
`~/Applications/`.

## How it works

When the system (Slack, pa-web, or any tool) generates a work-packet "Resources"
block, offline copies are staged under `~/Dropbox/letta-shared-files/staged/` and
linked with `openfile:///absolute/path/to/file` URIs. Clicking such a link opens the
file in its default app on a Mac that has the handler installed.

## Cross-device behavior (work-packet staged materials)

Work-packet "Resources" links come in two flavors:

- **Live cloud links** (`https://…`) — the Slack message, Gmail permalink, Granola
  meeting note, or Google Doc. These resolve on **every device** (Mac, iPhone, iPad).
- **Offline copies** (`openfile://…`) — a staged local file under
  `~/Dropbox/letta-shared-files/staged/`. These open the file via this handler.

`openfile://` resolves **only** on a Mac that has BOTH:
1. `OpenFileHandler.app` installed (run `openfile-handler/install.sh` on that Mac), AND
2. the Dropbox-synced `letta-shared-files` folder present.

- The **home server** has the handler installed (`~/Applications/OpenFileHandler.app`).
- To use offline copies on the **laptop**, run `openfile-handler/install.sh` there.
- On **iPhone/iPad**, `openfile://` will NOT resolve — this is expected. Every staged
  resource also carries the universal cloud link, so you always have a way in. Staged
  offline copies are a desktop convenience, never the only access path.

Staged files are pruned after 30 days by `scripts/prune-staged-materials.sh`
(launchd `com.ai-pa.prune-staged-materials`, weekly).

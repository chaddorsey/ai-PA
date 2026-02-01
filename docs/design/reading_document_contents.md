**User**

Is there a way that my agent can access the content of PDFs stored in Google Drive?

---

**Cursor**

Good question! There are a few approaches, depending on the PDF type:

### Current Capabilities

Right now, your agent can:
- **Get PDF metadata** via `get_drive_file_info` (title, owner, dates, etc.)
- **Search for PDFs** via `get_drive_documents(file_type="pdf")`

But there's **no tool to extract PDF content**.

### Options to Add PDF Content Access

| Approach | Best For | Complexity |
|----------|----------|------------|
| **1. Google Drive export + PyPDF2** | Text-based PDFs | Medium |
| **2. Google Cloud Vision API** | Scanned/image PDFs (OCR) | Medium |
| **3. Google Document AI** | Complex documents, tables | Higher |
| **4. Convert to Google Doc** | Editable PDFs | Simple but lossy |

### Recommended: Export + PDF Parser

The simplest approach is:
1. Use Drive API to download the PDF bytes
2. Use `pdfplumber` or `PyPDF2` to extract text

```python
get_pdf_content(
    drive_url: str,        # URL or file ID
    pages: Optional[str] = None,  # "1-5" or "1,3,5" or None for all
    extract_tables: bool = False  # Also extract tables (pdfplumber)
) -> str
```

Would you like me to create this tool? I'd use `pdfplumber` since it handles both text extraction and tables well.

**Note**: This works for text-based PDFs. Scanned PDFs (images of documents) would need OCR via Cloud Vision API - that's a more involved setup.

```python
get_pdf_content(
    drive_url: str,        # URL or file ID
    pages: Optional[str] = None,  # "1-5" or "1,3,5" or None for all
    extract_tables: bool = False  # Also extract tables (pdfplumber)
) -> str
```

---

**User**

What happens right now when the agent uses get_drive_documents? Are they downloaded now?

---

**Cursor**

Based on my review of the `get_drive_documents` function, here's what happens when the agent uses it:

## Current Behavior of `get_drive_documents`

**It returns metadata only — files are NOT downloaded.**

The function queries the Google Drive API and returns document information including:
- `id` — The file ID
- `name` — The file name
- `type` — The MIME type (document, spreadsheet, presentation, pdf, etc.)
- `link` — The web view link (for opening in browser)
- `owner` — The owner's email address
- `modified` — Last modified timestamp
- `created` — Creation timestamp
- `shared` — Whether the file is shared
- `size` — File size

```2573:2583:/Volumes/main-drive/ai-PA/letta/drive_analytics_tools.py
                doc = {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "type": f.get("mimeType", "").replace("application/vnd.google-apps.", ""),
                    "link": f.get("webViewLink", ""),
                    "owner": f.get("owners", [{}])[0].get("emailAddress", "") if f.get("owners") else "",
                    "modified": f.get("modifiedTime", ""),
                    "created": f.get("createdTime", ""),
                    "shared": f.get("shared", False),
                    "size": f.get("size", ""),
                }
```

So the agent can **search for** and **list** documents, but cannot access their actual content. This answers your earlier question about PDFs — currently there's no tool that extracts or reads the content from PDF files (or any other file type) stored in Google Drive.

Would you like me to explore options for adding content extraction capabilities?

```python
                doc = {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "type": f.get("mimeType", "").replace("application/vnd.google-apps.", ""),
                    "link": f.get("webViewLink", ""),
                    "owner": f.get("owners", [{}])[0].get("emailAddress", "") if f.get("owners") else "",
                    "modified": f.get("modifiedTime", ""),
                    "created": f.get("createdTime", ""),
                    "shared": f.get("shared", False),
                    "size": f.get("size", ""),
                }
```

---

**User**

How would we go about downloading and examining these? Look at the analytics examples from Slack for a potential pattern. The files used would likely be temporary, not stored in long-term storage archives, etc.

---

**Cursor**

I can see the Slack pattern clearly. Let me also check if there's any existing PDF processing capability in the codebase:

Now I have a clear picture. Here's how we could approach this, following the Slack analytics pattern:

## Proposed Pattern for Drive File Content Extraction

### 1. **The Slack Pattern (as reference)**

```323:374:/Volumes/main-drive/ai-PA/letta/slack_analytics_tools.py
def download_slack_file(file_url: str, save_path: Optional[str] = None) -> str:
    """
    Download a file from Slack using its private download URL.
    ...
    """
    # Downloads to /tmp/ by default
    if not save_path:
        filename = file_url.split("/")[-1].split("?")[0]
        save_path = f"/tmp/{filename}"
    
    with open(save_path, 'wb') as f:
        f.write(response.content)
    # ... returns path
```

### 2. **Proposed Drive Implementation**

For Google Drive, we'd need a tool like `get_drive_file_content()` that:

1. **Downloads to `/tmp/`** — temporary storage, no archiving
2. **Handles two file types differently:**
   - **Binary files (PDFs, images):** Use `files().get_media()` to download directly
   - **Native Google Docs:** Use `files().export()` to export as text/PDF

3. **Extracts text content:**
   - For **PDFs**: Use `pypdf` library to extract text
   - For **Google Docs/Sheets/Slides**: Export as plain text directly via API
   - For **images**: Optionally OCR (but that's more complex)

4. **Cleans up** — delete temp file after extraction

### Key API Methods

```python
# For binary files (PDFs, Word docs, etc.):
request = service.files().get_media(fileId=file_id)

# For native Google Docs → export as text:
request = service.files().export_media(fileId=file_id, mimeType='text/plain')

# For native Google Docs → export as PDF:
request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
```

### Dependencies Needed

- `pypdf` — for PDF text extraction (lightweight, pure Python)
- Already have: `googleapiclient`, `google-auth`, etc.

### Proposed Tool Signature

```python
def get_drive_file_content(
    drive_url: str,                    # URL or file ID
    extract_text: bool = True,         # Return text content (vs raw download path)
    max_pages: Optional[int] = None,   # Limit PDF pages to extract
    output_format: str = "text"        # "text" or "summary" 
) -> str:
    """
    Download and extract content from a Google Drive file.
    
    Handles:
    - PDFs: Downloads and extracts text using pypdf
    - Google Docs: Exports as plain text
    - Google Sheets: Exports as CSV
    - Google Slides: Exports as plain text
    
    Files are downloaded to /tmp/ and deleted after extraction.
    """
```

### Questions Before Proceeding

1. **Scope**: Should this be a single tool that handles all file types, or separate tools (`get_pdf_content`, `get_doc_content`)?

2. **Size limits**: Should we limit file size or page count to prevent long-running operations?

3. **Should we create a PBI/task for this**, or is this exploratory for now?

```python
def download_slack_file(file_url: str, save_path: Optional[str] = None) -> str:
    """
    Download a file from Slack using its private download URL.
    ...
    """
    # Downloads to /tmp/ by default
    if not save_path:
        filename = file_url.split("/")[-1].split("?")[0]
        save_path = f"/tmp/{filename}"
    
    with open(save_path, 'wb') as f:
        f.write(response.content)
    # ... returns path
```

```python
# For binary files (PDFs, Word docs, etc.):
request = service.files().get_media(fileId=file_id)

# For native Google Docs → export as text:
request = service.files().export_media(fileId=file_id, mimeType='text/plain')

# For native Google Docs → export as PDF:
request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
```

```python
def get_drive_file_content(
    drive_url: str,                    # URL or file ID
    extract_text: bool = True,         # Return text content (vs raw download path)
    max_pages: Optional[int] = None,   # Limit PDF pages to extract
    output_format: str = "text"        # "text" or "summary" 
) -> str:
    """
    Download and extract content from a Google Drive file.
    
    Handles:
    - PDFs: Downloads and extracts text using pypdf
    - Google Docs: Exports as plain text
    - Google Sheets: Exports as CSV
    - Google Slides: Exports as plain text
    
    Files are downloaded to /tmp/ and deleted after extraction.
    """
```

---

**User**

This is exploratory for now.

---

**Cursor**

Got it — keeping this exploratory.

## Summary of Options

| File Type | Download Method | Text Extraction | Complexity |
|-----------|----------------|-----------------|------------|
| **PDFs** | `get_media()` → `/tmp/` | `pypdf` library | Low — straightforward |
| **Google Docs** | `export_media(mimeType='text/plain')` | Direct from API | Very low — no library needed |
| **Google Sheets** | `export_media(mimeType='text/csv')` | Direct from API | Very low |
| **Google Slides** | `export_media(mimeType='text/plain')` | Direct from API | Very low |
| **Word/PowerPoint** | `get_media()` → `/tmp/` | `python-docx`, `python-pptx` | Medium |
| **Images (OCR)** | `get_media()` → `/tmp/` | `pytesseract` or Vision API | Higher |

### Quickest Win

**Native Google Docs** are the easiest — no download or parsing library needed. The API can export them directly as plain text. If most of your important documents are Google Docs, that's a fast path.

**PDFs** are the next easiest — just need to add `pypdf` as a dependency.
"""Drive API enricher for drive comment task queue entries."""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = structlog.get_logger()

# Mime type to doc_type mapping
MIME_TO_DOC_TYPE = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.presentation": "presentation",
}

# Doc type to URL path segment
DOC_TYPE_TO_PATH = {
    "document": "document",
    "spreadsheet": "spreadsheets",
    "presentation": "presentation",
}


class DriveEnricher:
    """Enriches drive comment queue entries via Google Drive API.

    Provides file metadata, comment data, and surrounding document context
    for queued drive comment task entries.
    """

    def __init__(self, token_path: str) -> None:
        self._token_path = token_path
        self._creds: Optional[Credentials] = None
        self._drive_service = None

    def _ensure_auth(self) -> None:
        """Load and refresh credentials, build Drive service."""
        if self._creds is None:
            self._creds = Credentials.from_authorized_user_file(
                self._token_path
            )

        if not self._creds.valid:
            self._creds.refresh(Request())
            token_data = {
                "token": self._creds.token,
                "refresh_token": self._creds.refresh_token,
                "token_uri": self._creds.token_uri,
                "client_id": self._creds.client_id,
                "client_secret": self._creds.client_secret,
                "scopes": list(self._creds.scopes) if self._creds.scopes else [],
            }
            with open(self._token_path, "w") as f:
                json.dump(token_data, f, indent=2)

        if self._drive_service is None:
            self._drive_service = build(
                "drive", "v3", credentials=self._creds
            )

    def enrich(
        self,
        doc_id: str,
        comment_id: Optional[str],
    ) -> dict[str, Any]:
        """Enrich a queue entry with Drive API data.

        Args:
            doc_id: Google Drive file ID.
            comment_id: Google Drive comment ID (may be None).

        Returns:
            Dict with enriched fields. Keys present only when data
            was successfully fetched:
            - doc_title, doc_type, doc_link, mime_type
            - comment_text, comment_author, comment_author_email,
              quoted_passage, comment_date
            - surrounding_context
        """
        result: dict[str, Any] = {}

        try:
            self._ensure_auth()
        except Exception as e:
            logger.warning("drive_enricher_auth_failed", error=str(e))
            return result

        # File metadata
        try:
            file_meta = (
                self._drive_service.files()
                .get(fileId=doc_id, fields="id,name,mimeType,webViewLink")
                .execute()
            )
            result["doc_title"] = file_meta.get("name", "")
            mime_type = file_meta.get("mimeType", "")
            result["doc_type"] = MIME_TO_DOC_TYPE.get(mime_type, "document")

            path_seg = DOC_TYPE_TO_PATH.get(result["doc_type"], "document")
            doc_link = f"https://docs.google.com/{path_seg}/d/{doc_id}/edit"
            if comment_id:
                doc_link += f"?disco={comment_id}"
            result["doc_link"] = doc_link
        except Exception as e:
            logger.warning(
                "drive_enricher_file_meta_failed",
                doc_id=doc_id,
                error=str(e),
            )
            return result

        # Comment metadata
        if comment_id:
            try:
                comment_data = (
                    self._drive_service.comments()
                    .get(
                        fileId=doc_id,
                        commentId=comment_id,
                        fields="content,author,quotedFileContent,createdTime",
                    )
                    .execute()
                )
                result["comment_text"] = comment_data.get("content", "")
                author = comment_data.get("author", {})
                result["comment_author"] = author.get("displayName", "")
                result["comment_author_email"] = author.get(
                    "emailAddress", ""
                )
                quoted_fc = comment_data.get("quotedFileContent", {})
                result["quoted_passage"] = quoted_fc.get("value", "")
                result["comment_date"] = comment_data.get("createdTime", "")
            except Exception as e:
                logger.debug(
                    "drive_enricher_comment_failed",
                    doc_id=doc_id,
                    comment_id=comment_id,
                    error=str(e),
                )

        # Surrounding context (best-effort)
        quoted = result.get("quoted_passage", "")
        doc_type = result.get("doc_type", "")
        if quoted and doc_type:
            try:
                ctx = self._get_surrounding_context(
                    doc_id, doc_type, quoted
                )
                if ctx:
                    result["surrounding_context"] = ctx
            except Exception:
                pass

        return result

    def _get_surrounding_context(
        self, doc_id: str, doc_type: str, quoted: str
    ) -> str:
        """Fetch surrounding context for a quoted passage."""
        if doc_type == "document":
            return self._context_from_doc(doc_id, quoted)
        if doc_type == "spreadsheet":
            return self._context_from_sheet(doc_id, quoted)
        if doc_type == "presentation":
            return self._context_from_slides(doc_id, quoted)
        return ""

    def _context_from_doc(self, doc_id: str, quoted: str) -> str:
        docs_svc = build("docs", "v1", credentials=self._creds)
        doc_data = docs_svc.documents().get(documentId=doc_id).execute()
        body_content = doc_data.get("body", {}).get("content", [])

        paragraphs = []
        for element in body_content:
            paragraph = element.get("paragraph", {})
            if paragraph:
                para_text = "".join(
                    tr.get("textRun", {}).get("content", "")
                    for tr in paragraph.get("elements", [])
                )
                if para_text.strip():
                    paragraphs.append(para_text.strip())

        for idx, p in enumerate(paragraphs):
            if quoted in p:
                start = max(0, idx - 3)
                end = min(len(paragraphs), idx + 4)
                parts = []
                for cp in paragraphs[start:end]:
                    if quoted in cp:
                        parts.append(f">> {cp} <<")
                    else:
                        parts.append(cp)
                return "\n".join(parts)
        return ""

    def _context_from_sheet(self, doc_id: str, quoted: str) -> str:
        sheets_svc = build("sheets", "v4", credentials=self._creds)
        data = (
            sheets_svc.spreadsheets()
            .get(
                spreadsheetId=doc_id,
                fields="sheets.data.rowData.values.formattedValue",
            )
            .execute()
        )
        rows = []
        for sheet in data.get("sheets", []):
            for grid in sheet.get("data", []):
                for row in grid.get("rowData", []):
                    vals = [
                        c.get("formattedValue", "")
                        for c in row.get("values", [])
                    ]
                    if any(vals):
                        rows.append(" | ".join(vals))
        for idx, row_text in enumerate(rows):
            if quoted in row_text:
                start = max(0, idx - 2)
                end = min(len(rows), idx + 3)
                return "\n".join(rows[start:end])
        return ""

    def _context_from_slides(self, doc_id: str, quoted: str) -> str:
        slides_svc = build("slides", "v1", credentials=self._creds)
        pres = (
            slides_svc.presentations()
            .get(
                presentationId=doc_id,
                fields="slides.pageElements.shape.text.textElements.textRun.content",
            )
            .execute()
        )
        for slide in pres.get("slides", []):
            parts = []
            for elem in slide.get("pageElements", []):
                shape = elem.get("shape", {})
                for te in shape.get("text", {}).get("textElements", []):
                    content = te.get("textRun", {}).get("content", "")
                    if content.strip():
                        parts.append(content.strip())
            slide_text = "\n".join(parts)
            if quoted in slide_text:
                return slide_text
        return ""

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
            - urls: list of hyperlink URLs found in the document context
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

        # Surrounding context + URL extraction (best-effort)
        quoted = result.get("quoted_passage", "")
        doc_type = result.get("doc_type", "")
        urls: list[str] = []
        if quoted and doc_type:
            try:
                ctx = self._get_surrounding_context(
                    doc_id, doc_type, quoted, urls
                )
                if ctx:
                    result["surrounding_context"] = ctx
            except Exception:
                pass

        if urls:
            result["urls"] = urls

        return result

    def _get_surrounding_context(
        self,
        doc_id: str,
        doc_type: str,
        quoted: str,
        urls_out: list[str] | None = None,
    ) -> str:
        """Fetch surrounding context for a quoted passage."""
        if doc_type == "document":
            return self._context_from_doc(doc_id, quoted, urls_out)
        if doc_type == "spreadsheet":
            return self._context_from_sheet(doc_id, quoted, urls_out)
        if doc_type == "presentation":
            return self._context_from_slides(doc_id, quoted, urls_out)
        return ""

    @staticmethod
    def _extract_paragraph_text(
        paragraph: dict[str, Any],
        urls_out: list[str] | None = None,
    ) -> tuple[str, str]:
        """Extract plain text and link-enriched text from a paragraph.

        Args:
            paragraph: Google Docs paragraph element.
            urls_out: If provided, hyperlink URLs found in this paragraph
                are appended to this list (for separate URL collection).

        Returns:
            Tuple of (plain_text, enriched_text). The enriched version
            appends hyperlink URLs inline when the display text differs
            from the URL target.
        """
        plain_parts: list[str] = []
        rich_parts: list[str] = []

        for elem in paragraph.get("elements", []):
            text_run = elem.get("textRun", {})
            content = text_run.get("content", "")
            link_url = (
                text_run.get("textStyle", {})
                .get("link", {})
                .get("url", "")
            )
            plain_parts.append(content)
            if link_url and content.strip() and link_url != content.strip():
                rich_parts.append(f"{content.rstrip()} ({link_url})")
                if urls_out is not None and link_url not in urls_out:
                    urls_out.append(link_url)
            else:
                rich_parts.append(content)

        return "".join(plain_parts).strip(), "".join(rich_parts).strip()

    def _context_from_doc(
        self,
        doc_id: str,
        quoted: str,
        urls_out: list[str] | None = None,
    ) -> str:
        docs_svc = build("docs", "v1", credentials=self._creds)
        doc_data = docs_svc.documents().get(documentId=doc_id).execute()
        body_content = doc_data.get("body", {}).get("content", [])

        # Build parallel plain/enriched paragraph lists
        plain_paragraphs: list[str] = []
        rich_paragraphs: list[str] = []
        for element in body_content:
            paragraph = element.get("paragraph", {})
            if paragraph:
                plain, rich = self._extract_paragraph_text(
                    paragraph, urls_out
                )
                if plain:
                    plain_paragraphs.append(plain)
                    rich_paragraphs.append(rich)

        for idx, p in enumerate(plain_paragraphs):
            if quoted in p:
                start = max(0, idx - 3)
                end = min(len(plain_paragraphs), idx + 4)
                parts = []
                for i in range(start, end):
                    if quoted in plain_paragraphs[i]:
                        parts.append(f">> {rich_paragraphs[i]} <<")
                    else:
                        parts.append(rich_paragraphs[i])
                return "\n".join(parts)
        return ""

    def _context_from_sheet(
        self,
        doc_id: str,
        quoted: str,
        urls_out: list[str] | None = None,
    ) -> str:
        sheets_svc = build("sheets", "v4", credentials=self._creds)
        data = (
            sheets_svc.spreadsheets()
            .get(
                spreadsheetId=doc_id,
                fields="sheets.data.rowData.values(formattedValue,hyperlink)",
            )
            .execute()
        )
        plain_rows: list[str] = []
        rich_rows: list[str] = []
        for sheet in data.get("sheets", []):
            for grid in sheet.get("data", []):
                for row in grid.get("rowData", []):
                    plain_vals: list[str] = []
                    rich_vals: list[str] = []
                    for c in row.get("values", []):
                        fv = c.get("formattedValue", "")
                        link = c.get("hyperlink", "")
                        plain_vals.append(fv)
                        if link and fv and link != fv:
                            rich_vals.append(f"{fv} ({link})")
                            if urls_out is not None and link not in urls_out:
                                urls_out.append(link)
                        else:
                            rich_vals.append(fv)
                    if any(plain_vals):
                        plain_rows.append(" | ".join(plain_vals))
                        rich_rows.append(" | ".join(rich_vals))
        for idx, row_text in enumerate(plain_rows):
            if quoted in row_text:
                start = max(0, idx - 2)
                end = min(len(rich_rows), idx + 3)
                return "\n".join(rich_rows[start:end])
        return ""

    def _context_from_slides(
        self,
        doc_id: str,
        quoted: str,
        urls_out: list[str] | None = None,
    ) -> str:
        slides_svc = build("slides", "v1", credentials=self._creds)
        pres = (
            slides_svc.presentations()
            .get(
                presentationId=doc_id,
                fields=(
                    "slides.pageElements.shape.text.textElements"
                    ".textRun(content,style.link.url)"
                ),
            )
            .execute()
        )
        for slide in pres.get("slides", []):
            plain_parts: list[str] = []
            rich_parts: list[str] = []
            for elem in slide.get("pageElements", []):
                shape = elem.get("shape", {})
                for te in shape.get("text", {}).get("textElements", []):
                    text_run = te.get("textRun", {})
                    content = text_run.get("content", "")
                    link_url = (
                        text_run.get("style", {})
                        .get("link", {})
                        .get("url", "")
                    )
                    if content.strip():
                        plain_parts.append(content.strip())
                        if link_url and link_url != content.strip():
                            rich_parts.append(
                                f"{content.strip()} ({link_url})"
                            )
                            if (
                                urls_out is not None
                                and link_url not in urls_out
                            ):
                                urls_out.append(link_url)
                        else:
                            rich_parts.append(content.strip())
            plain_text = "\n".join(plain_parts)
            if quoted in plain_text:
                return "\n".join(rich_parts)
        return ""

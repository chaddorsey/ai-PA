"""Google OAuth authentication for Drive and Docs APIs.

This module handles OAuth2 authentication for accessing Google Drive and Docs APIs.
It can use either:
- Service account credentials (for server-to-server)
- OAuth2 user credentials (for accessing user's files)
"""

import os
from pathlib import Path
from typing import Optional

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from drive_rag.settings import get_settings

logger = structlog.get_logger()

# Scopes required for Drive and Docs access
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]


def get_credentials(
    credentials_path: Optional[str] = None,
    token_path: Optional[str] = None,
) -> Credentials:
    """Get or refresh OAuth2 credentials.

    Args:
        credentials_path: Path to OAuth client credentials JSON
        token_path: Path to store/load token

    Returns:
        Valid OAuth2 credentials
    """
    settings = get_settings()

    creds_dir = Path(credentials_path or settings.google_credentials_path)
    token_file = Path(token_path or settings.google_token_path or creds_dir / "drive-docs-token.json")
    creds_file = creds_dir / "gcp-oauth.calendar.desktop.json"

    creds = None

    # Load existing token if available
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        logger.debug("loaded_existing_token", path=str(token_file))

    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("refreshing_token")
            creds.refresh(Request())
        else:
            if not creds_file.exists():
                raise FileNotFoundError(
                    f"Credentials file not found at {creds_file}. "
                    "Please download OAuth client credentials from Google Cloud Console."
                )

            logger.info("running_oauth_flow")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token for next run
        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
        logger.info("saved_token", path=str(token_file))

    return creds


def get_drive_service(creds: Optional[Credentials] = None) -> Resource:
    """Get Google Drive API service.

    Args:
        creds: OAuth2 credentials (will be obtained if not provided)

    Returns:
        Google Drive API service resource
    """
    if creds is None:
        creds = get_credentials()

    return build("drive", "v3", credentials=creds)


def get_docs_service(creds: Optional[Credentials] = None) -> Resource:
    """Get Google Docs API service.

    Args:
        creds: OAuth2 credentials (will be obtained if not provided)

    Returns:
        Google Docs API service resource
    """
    if creds is None:
        creds = get_credentials()

    return build("docs", "v1", credentials=creds)


class GoogleClient:
    """Unified client for Google Drive and Docs APIs."""

    def __init__(self, credentials_path: Optional[str] = None):
        """Initialize the Google client.

        Args:
            credentials_path: Path to OAuth credentials directory
        """
        self.creds = get_credentials(credentials_path)
        self._drive: Optional[Resource] = None
        self._docs: Optional[Resource] = None

    @property
    def drive(self) -> Resource:
        """Get Drive API service (lazy initialization)."""
        if self._drive is None:
            self._drive = get_drive_service(self.creds)
        return self._drive

    @property
    def docs(self) -> Resource:
        """Get Docs API service (lazy initialization)."""
        if self._docs is None:
            self._docs = get_docs_service(self.creds)
        return self._docs

    def get_file_metadata(self, file_id: str) -> dict:
        """Get file metadata from Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata including name, mimeType, modifiedTime, etc.
        """
        return (
            self.drive.files()
            .get(
                fileId=file_id,
                fields="id,name,mimeType,modifiedTime,version,headRevisionId,owners,md5Checksum",
            )
            .execute()
        )

    def list_revisions(self, file_id: str) -> list[dict]:
        """List revisions for a file.

        Args:
            file_id: Google Drive file ID

        Returns:
            List of revision metadata
        """
        result = (
            self.drive.revisions()
            .list(
                fileId=file_id,
                fields="revisions(id,modifiedTime,lastModifyingUser)",
            )
            .execute()
        )
        return result.get("revisions", [])

    def get_document(self, document_id: str) -> dict:
        """Get full document content from Docs API.

        Args:
            document_id: Google Docs document ID (same as Drive file ID)

        Returns:
            Full document JSON including body content
        """
        return self.docs.documents().get(documentId=document_id).execute()

    def export_document_as_text(self, file_id: str) -> str:
        """Export a Google Doc as plain text using Drive API.

        This is a fallback when the Docs API is not available.

        Args:
            file_id: Google Drive file ID

        Returns:
            Plain text content of the document
        """
        content = self.drive.files().export(
            fileId=file_id,
            mimeType="text/plain"
        ).execute()

        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content

    def list_files_in_folder(
        self,
        folder_id: str,
        mime_type: Optional[str] = None,
        page_size: int = 100,
    ) -> list[dict]:
        """List files in a Drive folder.

        Args:
            folder_id: Google Drive folder ID
            mime_type: Optional MIME type filter (e.g., 'application/vnd.google-apps.document')
            page_size: Results per page

        Returns:
            List of file metadata
        """
        query = f"'{folder_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"

        files = []
        page_token = None

        while True:
            result = (
                self.drive.files()
                .list(
                    q=query,
                    fields="nextPageToken,files(id,name,mimeType,modifiedTime,owners)",
                    pageSize=page_size,
                    pageToken=page_token,
                )
                .execute()
            )

            files.extend(result.get("files", []))
            page_token = result.get("nextPageToken")

            if not page_token:
                break

        return files


# Module-level singleton
_google_client: Optional[GoogleClient] = None


def get_google_client() -> GoogleClient:
    """Get or create the global Google client."""
    global _google_client
    if _google_client is None:
        _google_client = GoogleClient()
    return _google_client

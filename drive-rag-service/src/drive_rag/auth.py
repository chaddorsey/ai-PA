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
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents.readonly",
    # Activity API for view/edit tracking (optional - will gracefully degrade if not granted)
    "https://www.googleapis.com/auth/drive.activity.readonly",
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
    """Unified client for Google Drive, Docs, and Sheets APIs."""

    def __init__(self, credentials_path: Optional[str] = None):
        """Initialize the Google client.

        Args:
            credentials_path: Path to OAuth credentials directory
        """
        self.creds = get_credentials(credentials_path)
        self._drive: Optional[Resource] = None
        self._docs: Optional[Resource] = None
        self._sheets: Optional[Resource] = None

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

    @property
    def sheets(self) -> Resource:
        """Get Sheets API service (lazy initialization)."""
        if self._sheets is None:
            from googleapiclient.discovery import build
            self._sheets = build("sheets", "v4", credentials=self.creds)
        return self._sheets

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
                supportsAllDrives=True,
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
        # Note: revisions.list does not support supportsAllDrives parameter
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
            mimeType="text/plain",
        ).execute()

        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content

    def export_spreadsheet_as_csv(self, file_id: str) -> str:
        """Export a Google Sheet as CSV using Drive API.

        Only exports the first sheet. For multi-sheet spreadsheets,
        consider using the Sheets API for more control.

        Args:
            file_id: Google Drive file ID

        Returns:
            CSV content of the spreadsheet
        """
        content = self.drive.files().export(
            fileId=file_id,
            mimeType="text/csv",
        ).execute()

        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content

    def get_all_sheets_as_csv(self, file_id: str) -> list[dict]:
        """Get all sheets from a spreadsheet as CSV via Sheets API.

        Args:
            file_id: Google Drive file ID of a spreadsheet

        Returns:
            List of dicts with 'sheet_name' and 'csv' keys
        """
        import csv
        import io

        # Get spreadsheet metadata for sheet names
        spreadsheet = self.sheets.spreadsheets().get(
            spreadsheetId=file_id, fields="sheets.properties"
        ).execute()

        sheets_data = []
        for sheet in spreadsheet.get("sheets", []):
            props = sheet["properties"]
            sheet_name = props["title"]
            # Fetch all values from this sheet
            result = self.sheets.spreadsheets().values().get(
                spreadsheetId=file_id,
                range=f"'{sheet_name}'",
            ).execute()
            rows = result.get("values", [])
            # Convert rows to CSV string
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerows(rows)
            sheets_data.append({"sheet_name": sheet_name, "csv": buf.getvalue()})

        return sheets_data

    def export_presentation_as_text(self, file_id: str) -> str:
        """Export a Google Slides presentation as plain text.

        Exports slide content and speaker notes as text.

        Args:
            file_id: Google Drive file ID

        Returns:
            Plain text content of the presentation
        """
        content = self.drive.files().export(
            fileId=file_id,
            mimeType="text/plain",
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
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )

            files.extend(result.get("files", []))
            page_token = result.get("nextPageToken")

            if not page_token:
                break

        return files

    def get_file_metadata_extended(self, file_id: str) -> dict:
        """Get extended file metadata including all fields for comprehensive tracking.

        Args:
            file_id: Google Drive file ID

        Returns:
            Extended file metadata dict
        """
        fields = ",".join([
            "id", "name", "mimeType", "description",
            "createdTime", "modifiedTime", "viewedByMeTime", "sharedWithMeTime",
            "version", "headRevisionId",
            "owners", "lastModifyingUser", "sharingUser",
            "parents", "shared",
            "webViewLink", "webContentLink",
            "size", "starred", "trashed",
            "capabilities",
        ])

        return (
            self.drive.files()
            .get(fileId=file_id, fields=fields, supportsAllDrives=True)
            .execute()
        )

    def get_folder_metadata(self, folder_id: str) -> dict:
        """Get folder metadata for hierarchy building.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            Folder metadata dict
        """
        fields = "id,name,mimeType,parents,createdTime,modifiedTime,owners,shared"

        return (
            self.drive.files()
            .get(fileId=folder_id, fields=fields, supportsAllDrives=True)
            .execute()
        )

    def build_folder_path(self, file_id: str, max_depth: int = 20) -> tuple[list[str], list[str]]:
        """Build the full folder path from root to the given file/folder.

        Args:
            file_id: Google Drive file or folder ID
            max_depth: Maximum depth to traverse (prevents infinite loops)

        Returns:
            Tuple of (folder_path_names, folder_path_ids) from root to parent
        """
        path_names: list[str] = []
        path_ids: list[str] = []
        current_id = file_id

        for _ in range(max_depth):
            try:
                meta = self.drive.files().get(
                    fileId=current_id,
                    fields="id,name,parents,mimeType",
                    supportsAllDrives=True,
                ).execute()

                # Only add to path if it's a folder (not the file itself on first iteration)
                if meta.get("mimeType") == "application/vnd.google-apps.folder":
                    path_names.insert(0, meta["name"])
                    path_ids.insert(0, meta["id"])

                parents = meta.get("parents", [])
                if not parents:
                    break
                current_id = parents[0]

            except Exception as e:
                logger.warning("folder_path_traversal_error", file_id=current_id, error=str(e))
                break

        return path_names, path_ids

    def download_file_content(self, file_id: str) -> bytes:
        """Download file content as bytes.

        This is used for binary files like PDFs that need to be downloaded
        rather than exported.

        Args:
            file_id: Google Drive file ID

        Returns:
            File content as bytes
        """
        from googleapiclient.http import MediaIoBaseDownload
        import io

        request = self.drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.debug("download_progress", file_id=file_id, progress=int(status.progress() * 100))

        buffer.seek(0)
        return buffer.read()

    def extract_sharing_domains(self, file_meta: dict) -> tuple[list[str], bool]:
        """Extract sharing domains and external access flag from file metadata.

        Note: Requires reading permissions which may not be available for all files.

        Args:
            file_meta: File metadata dict (should include owner info)

        Returns:
            Tuple of (domains_list, has_external_access)
        """
        domains = set()
        has_external = False

        # Extract owner domain
        owners = file_meta.get("owners", [])
        for owner in owners:
            email = owner.get("emailAddress", "")
            if "@" in email:
                domain = email.split("@")[1]
                domains.add(domain)

        # Check last modifier domain
        last_modifier = file_meta.get("lastModifyingUser", {})
        email = last_modifier.get("emailAddress", "")
        if "@" in email:
            domain = email.split("@")[1]
            domains.add(domain)

        # Check sharing user domain
        sharing_user = file_meta.get("sharingUser", {})
        email = sharing_user.get("emailAddress", "")
        if "@" in email:
            domain = email.split("@")[1]
            domains.add(domain)

        # Determine if there's external access (any non-primary domain)
        # Assuming concord.org is the primary domain
        primary_domain = "concord.org"
        for domain in domains:
            if domain != primary_domain and domain != "gmail.com":  # gmail might be personal accounts
                has_external = True
                break

        return list(domains), has_external

    def get_changes_start_token(self) -> str:
        """Get the starting page token for tracking future changes.

        This should be called once to initialize change tracking.
        The returned token represents the current state - all subsequent
        changes.list calls with this token will return changes that
        occurred after this point.

        Returns:
            The start page token string
        """
        result = self.drive.changes().getStartPageToken(
            supportsAllDrives=True,
        ).execute()
        return result.get("startPageToken", "")

    def list_changes(
        self,
        page_token: str,
        page_size: int = 100,
    ) -> dict:
        """List changes since the given page token.

        This method returns changes across all drives the user has access to,
        including shared drives. It handles pagination internally.

        Args:
            page_token: The token from getStartPageToken or previous list call
            page_size: Number of changes per page (max 1000)

        Returns:
            Dictionary with:
            - changes: List of change objects
            - nextPageToken: Token for next page (if more results)
            - newStartPageToken: Token for next sync (only on last page)
        """
        result = self.drive.changes().list(
            pageToken=page_token,
            pageSize=page_size,
            spaces="drive",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,trashed,headRevisionId,owners,lastModifyingUser))",
        ).execute()

        return {
            "changes": result.get("changes", []),
            "nextPageToken": result.get("nextPageToken"),
            "newStartPageToken": result.get("newStartPageToken"),
        }

    def list_all_changes(
        self,
        page_token: str,
        max_changes: int = 10000,
    ) -> tuple[list[dict], str]:
        """List all changes since page token, handling pagination.

        This method fetches all pages of changes and returns them together
        with the new start token for the next sync.

        Args:
            page_token: Starting page token
            max_changes: Maximum total changes to retrieve (safety limit)

        Returns:
            Tuple of (all_changes, new_start_token)
        """
        all_changes = []
        current_token = page_token
        new_start_token = None

        while len(all_changes) < max_changes:
            result = self.list_changes(current_token)
            all_changes.extend(result["changes"])

            if result.get("newStartPageToken"):
                # Last page - save the new token for next sync
                new_start_token = result["newStartPageToken"]
                break
            elif result.get("nextPageToken"):
                # More pages to fetch
                current_token = result["nextPageToken"]
            else:
                # No more results and no new token (shouldn't happen)
                logger.warning("changes_list_no_token", changes_count=len(all_changes))
                break

        if new_start_token is None:
            logger.warning(
                "changes_truncated",
                retrieved=len(all_changes),
                max_changes=max_changes,
            )

        return all_changes, new_start_token or current_token


# Module-level singleton
_google_client: Optional[GoogleClient] = None


def get_google_client() -> GoogleClient:
    """Get or create the global Google client."""
    global _google_client
    if _google_client is None:
        _google_client = GoogleClient()
    return _google_client

#!/usr/bin/env python3
"""Simple Python client for Agent01 REST API.

This module provides a simple Python client for interacting with the
Agent01 REST API using standard HTTP requests.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

from . import requests_shim as requests
import json
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AigonClient:
    """Python client for Aigon REST API.

    This client provides a simple interface for interacting with the
    auto-generated REST API endpoints from Aigon bot ecosystem.
    """

    def __init__(self, base_url: str = "https://api.aigon.ai", api_token: str = None):
        """Initialize the client.

        Args:
            base_url: Base URL of the REST API server
            api_token: User authentication token from auth bot
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token  # Store for error messages

        # Store headers for all requests
        self.headers = {}
        if api_token:
            self.headers = {
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json'
            }

        # Test connection on initialization
        try:
            response = requests.get(f"{self.base_url}/health", headers=self.headers)
            if response.status_code == 200:
                logger.info(f"Connected to Agent01 REST API at {self.base_url}")
            else:
                logger.warning(f"API health check failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to connect to API: {e}")

    def _handle_auth_error(self, response):
        """Handle authentication errors with clear messages.

        Args:
            response: The HTTP response object

        Raises:
            Exception: With clear error message about authentication
        """
        if response.status_code == 401:
            raise Exception(f"\n❌ Authentication required - No API token provided!\n"
                          f"\nTo fix this:\n"
                          f"1. Get a token from @aigon_auth_bot on Telegram (https://t.me/aigon_auth_bot)\n"
                          f"2. Send the command: /get\n"
                          f"3. Copy the token and set the environment variable:\n"
                          f"   export AIGON_API_TOKEN=<your-token>\n"
                          f"\nThe AIGON_API_TOKEN environment variable is required for authentication.")
        elif response.status_code == 403:
            if not self.api_token:
                raise Exception(f"\n❌ Access denied - No API token provided!\n"
                              f"\nTo fix this:\n"
                              f"1. Get a token from @aigon_auth_bot on Telegram (https://t.me/aigon_auth_bot)\n"
                              f"2. Send the command: /get\n"
                              f"3. Copy the token and set the environment variable:\n"
                              f"   export AIGON_API_TOKEN=<your-token>\n"
                              f"\nThe AIGON_API_TOKEN environment variable is required for authentication.")
            else:
                raise Exception(f"\n❌ Access denied - Invalid or expired API token!\n"
                              f"\nYour current token may be invalid or expired.\n"
                              f"\nTo fix this:\n"
                              f"1. Get a new token from @aigon_auth_bot on Telegram (https://t.me/aigon_auth_bot)\n"
                              f"2. Send the command: /get\n"
                              f"3. Copy the new token and update the environment variable:\n"
                              f"   export AIGON_API_TOKEN=<your-new-token>\n"
                              f"\nMake sure the AIGON_API_TOKEN environment variable has the latest token.")

    def search_notes(self,
                    query: str,
                    content_type: str = None,
                    limit: int = 10,
                    scope: str = "all",
                    time_window_start: Optional[float] = None,
                    time_window_end: float = 0.0,
                    start_ts: Optional[int] = None,
                    end_ts: Optional[int] = None,
                    time_field: Optional[str] = None,
                    export_status: str = "all",
                    processed_status: str = "all",
                    deleted_status: str = "active",
                    max_content_length: int = -1,
                    note_type: str = "user",
                    reverse: bool = False,
                    agent_filter: Optional[str] = None,
                    show_delegated: bool = True,
                    with_attachments: bool = False,
                    strategy: str = "hybrid",
                    mode: str = "websearch",
                    similarity_threshold: float = 0.3,
                    order_by: str = "relevance",
                    order_dir: str = "desc",
                    offset: int = 0,
                    file_type: Optional[str] = None,
                    mime_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search through notetaker notes with comprehensive filtering.

        Args:
            query: Search query string
            content_type: Optional content type filter
            limit: Maximum number of results
            scope: Search scope (notes, attachments, all) - default: all
            time_window_start: Days back from now to start (None = all time). Ignored if start_ts is set.
            time_window_end: Days back from now to end (default: 0.0 for now). Ignored if end_ts is set.
            start_ts: Absolute start timestamp (Unix seconds). Overrides time_window_start.
            end_ts: Absolute end timestamp (Unix seconds). Overrides time_window_end.
            time_field: Which timestamp to filter on: 'created' or 'updated'.
                       Default: 'created' for absolute, 'updated' for relative.
            export_status: Filter by export status (all, unexported, exported)
            processed_status: Filter by processed status (all, unprocessed, processed)
            deleted_status: Filter by deleted status (active, deleted, all) - default: active
            max_content_length: Maximum length of content field (-1 = no limit)
            note_type: Filter by note type (user, system, all) - default: user
            reverse: If true with limit, get the N most recent notes instead of oldest N
            agent_filter: Filter by agent (shows notes owned by OR delegated to this agent)
            show_delegated: Include notes delegated to you (default: True)
            with_attachments: Include attachment metadata in results (default: False)

        Returns:
            List of matching notes
        """
        params = {
            'query': query,
            'format': 'full',  # Always request full format to get content
            'limit': limit,
            'scope': scope,
            'time_window_end': time_window_end,
            'export_status': export_status,
            'processed_status': processed_status,
            'deleted_status': deleted_status,
            'max_content_length': max_content_length,
            'note_type': note_type,
            'reverse': reverse,
            'show_delegated': show_delegated,
            'with_attachments': with_attachments,
            'strategy': strategy,
            'mode': mode,
            'similarity_threshold': similarity_threshold,
            'order_by': order_by,
            'order_dir': order_dir,
            'offset': offset,
        }

        if file_type:
            params['file_type'] = file_type
        if mime_type:
            params['mime_type'] = mime_type

        if content_type:
            params['content_type'] = content_type

        if time_window_start is not None:
            params['time_window_start'] = time_window_start

        if start_ts is not None:
            params['start_ts'] = start_ts

        if end_ts is not None:
            params['end_ts'] = end_ts

        if time_field is not None:
            params['time_field'] = time_field

        if agent_filter is not None:
            params['agent_filter'] = agent_filter

        response = requests.get(f"{self.base_url}/notetaker/search", headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        data = response.json()
        # API returns {"results": [...], "total": ...} - extract results list
        return data.get('results', []) if isinstance(data, dict) else data

    def global_search(self,
                     query: str,
                     scope: str = "all",
                     grouping: str = "merged",
                     note_type: str = "all",
                     file_versions: str = "latest",
                     time_window_start: Optional[float] = None,
                     time_window_end: float = 0.0,
                     start_ts: Optional[int] = None,
                     end_ts: Optional[int] = None,
                     time_field: str = "created",
                     export_status: str = "all",
                     processed_status: str = "all",
                     deleted_status: str = "active",
                     agent: Optional[str] = None,
                     include_delegated: bool = True,
                     limit: int = 50,
                     offset: int = 0,
                     order_by: str = "relevance",
                     order_dir: str = "desc") -> Dict[str, Any]:
        """Global search across notes, attachments, and files.

        Args:
            query: Search query string (websearch syntax: "phrase", OR, -exclude)
            scope: Comma-separated scopes (notes,system,attachments,files,all)
            grouping: Result grouping (merged, grouped)
            note_type: Note type filter (user, system, ephemeral, all)
            file_versions: File versions (latest, all)
            time_window_start: Days back from now (None = all time)
            time_window_end: Days back to end (default: 0.0 = now)
            start_ts: Absolute start timestamp (overrides window)
            end_ts: Absolute end timestamp (overrides window)
            time_field: Which timestamp to filter on (created, updated)
            export_status: Filter by export status (all, unexported, exported)
            processed_status: Filter by processed status (all, unprocessed, processed)
            deleted_status: Filter by deleted status (active, deleted, all)
            agent: Filter notes by agent
            include_delegated: Include notes delegated to agent
            limit: Maximum number of results
            offset: Skip first N results
            order_by: Sort order (relevance, created, updated)
            order_dir: Sort direction (desc, asc)

        Returns:
            Search results with grouping depending on 'grouping' parameter
        """
        params = {
            'q': query,
            'scope': scope,
            'grouping': grouping,
            'note_type': note_type,
            'file_versions': file_versions,
            'time_window_end': time_window_end,
            'time_field': time_field,
            'export_status': export_status,
            'processed_status': processed_status,
            'deleted_status': deleted_status,
            'include_delegated': include_delegated,
            'limit': limit,
            'offset': offset,
            'order_by': order_by,
            'order_dir': order_dir
        }

        if time_window_start is not None:
            params['time_window_start'] = time_window_start

        if start_ts is not None:
            params['start_ts'] = start_ts

        if end_ts is not None:
            params['end_ts'] = end_ts

        if agent is not None:
            params['agent'] = agent

        response = requests.get(f"{self.base_url}/search", headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def get_recent_notes(self, limit: int = 10, max_bytes: int = -1,
                         processed_status: str = 'unprocessed',
                         note_type: str = 'user',
                         time_window_start: Optional[float] = 1.0,
                         time_window_end: float = 0.0,
                         start_ts: Optional[int] = None,
                         end_ts: Optional[int] = None,
                         time_field: Optional[str] = None,
                         reverse: bool = False,
                         agent_filter: Optional[str] = None,
                         show_delegated: bool = True,
                         with_attachments: bool = False,
                         event: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent notes from notetaker (filtered retrieval with defaults).

        Defaults: last 1 day, unprocessed notes only, all export statuses, user notes only.

        Args:
            limit: Maximum number of notes to return
            max_bytes: Maximum total response size in bytes (-1 = no limit)
                       If exceeded, content fields are replaced with "(truncated)"
            processed_status: Filter by processed status (unprocessed, all, processed)
            note_type: Filter by note type (user, system, all) - default: user
            time_window_start: Days back to start (1.0 = 1 day ago, None = all time). Ignored if start_ts is set.
            time_window_end: Days back to end (0.0 = now). Ignored if end_ts is set.
            start_ts: Absolute start timestamp (Unix seconds). Overrides time_window_start.
            end_ts: Absolute end timestamp (Unix seconds). Overrides time_window_end.
            time_field: Which timestamp to filter on: 'created' or 'updated'.
                       Default: 'created' for absolute, 'updated' for relative.
            reverse: If true with limit, get the N most recent notes instead of oldest N
            agent_filter: Filter by agent (shows notes owned by OR delegated to this agent)
            show_delegated: Include notes delegated to you (default: True)
            with_attachments: Include attachment metadata in response (default: False)
            event: Event name to query participant notes (admin access only).
                   Empty results may indicate user is not authorized as event_admin.

        Returns:
            List of recent notes
        """
        # Use POST /notetaker/notes with filter parameters (no unique_ids)
        body = {
            'limit': limit,
            'processed_status': processed_status,
            'note_type': note_type,
            'time_window_start': time_window_start,  # None = all time (sent as null)
            'time_window_end': time_window_end,
            'reverse': reverse,
            'show_delegated': show_delegated,
            'with_attachments': with_attachments
        }

        # Add max_bytes if specified
        if max_bytes > 0:
            body['max_bytes'] = max_bytes

        # Add absolute timestamps if specified
        if start_ts is not None:
            body['start_ts'] = start_ts

        if end_ts is not None:
            body['end_ts'] = end_ts

        if time_field is not None:
            body['time_field'] = time_field

        if agent_filter is not None:
            body['agent_filter'] = agent_filter

        # Event mode: admin access to participant notes
        if event is not None:
            body['event'] = event

        response = requests.post(f"{self.base_url}/notetaker/notes", headers=self.headers, json=body)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def get_note_by_id(self, unique_id: str,
                       context_before: int = 0,
                       context_after: int = 0) -> List[Dict[str, Any]]:
        """Get note(s) by unique_id (supports prefix matching, minimum 2 characters).

        Args:
            unique_id: Unique ID or prefix (minimum 2 characters)
            context_before: Number of notes before to include
            context_after: Number of notes after to include

        Returns:
            List of matching notes (with context if requested)
        """
        params = {}
        if context_before > 0:
            params['context_before'] = context_before
        if context_after > 0:
            params['context_after'] = context_after

        response = requests.get(f"{self.base_url}/notetaker/notes/{unique_id}",
                               headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def get_notes_by_ids(self, unique_ids: List[str],
                         context_before: int = 0,
                         context_after: int = 0,
                         with_attachments: bool = False,
                         with_share_signature: bool = False) -> List[Dict[str, Any]]:
        """Get notes by multiple unique_ids (supports prefix matching).

        Args:
            unique_ids: List of unique IDs or prefixes (each minimum 2 characters)
            context_before: Number of notes before each target to include
            context_after: Number of notes after each target to include
            with_attachments: Include attachment metadata (default False for performance)
            with_share_signature: Include share_signature for public URL generation

        Returns:
            List of matching notes (with context if requested)
        """
        body = {'unique_ids': unique_ids, 'with_attachments': with_attachments}
        if context_before > 0:
            body['context_before'] = context_before
        if context_after > 0:
            body['context_after'] = context_after
        if with_share_signature:
            body['with_share_signature'] = True

        response = requests.post(f"{self.base_url}/notetaker/notes", headers=self.headers, json=body)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def mark_notes(self, unique_ids: List[str], processed: Optional[bool] = None,
                   exported: Optional[bool] = None, deleted: Optional[bool] = None) -> Dict[str, Any]:
        """Mark or unmark notes as processed, exported, and/or deleted.

        Args:
            unique_ids: List of unique IDs or prefixes (each minimum 2 characters)
            processed: True to mark, False to unmark, None for no change
            exported: True to mark, False to unmark, None for no change
            deleted: True to delete (soft), False to undelete, None for no change

        Returns:
            Dictionary with marking result information

        Note: At least one of processed, exported, or deleted must be specified (not None).
        """
        if processed is None and exported is None and deleted is None:
            raise ValueError("At least one of 'processed', 'exported', or 'deleted' must be specified")

        body = {'unique_ids': unique_ids}
        if processed is not None:
            body['processed'] = processed
        if exported is not None:
            body['exported'] = exported
        if deleted is not None:
            body['deleted'] = deleted

        response = requests.post(f"{self.base_url}/notetaker/notes/mark", headers=self.headers, json=body)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def update_notes(self, unique_ids: List[str],
                     tags_set: Optional[List[str]] = None,
                     tags_add: Optional[List[str]] = None,
                     tags_remove: Optional[List[str]] = None,
                     summary: Optional[str] = None,
                     metadata_set: Optional[Dict[str, Any]] = None,
                     metadata_merge: Optional[Dict[str, Any]] = None,
                     metadata_remove_keys: Optional[List[str]] = None,
                     delegates_add: Optional[List[str]] = None,
                     delegates_remove: Optional[List[str]] = None) -> Dict[str, Any]:
        """Bulk update note metadata: tags, summary, metadata, delegates.

        Args:
            unique_ids: List of unique IDs or prefixes (each minimum 2 characters)
            tags_set: Replace all tags with this list
            tags_add: Add these tags
            tags_remove: Remove these tags
            summary: Set summary (empty string clears)
            metadata_set: Replace entire metadata dict
            metadata_merge: Upsert keys into metadata
            metadata_remove_keys: Remove keys from metadata
            delegates_add: Add delegate agents
            delegates_remove: Remove delegate agents

        Returns:
            Dictionary with update result (success, batch_size, operations)
        """
        body: Dict[str, Any] = {'unique_ids': unique_ids}
        if tags_set is not None:
            body['tags_set'] = tags_set
        if tags_add is not None:
            body['tags_add'] = tags_add
        if tags_remove is not None:
            body['tags_remove'] = tags_remove
        if summary is not None:
            body['summary'] = summary
        if metadata_set is not None:
            body['metadata_set'] = metadata_set
        if metadata_merge is not None:
            body['metadata_merge'] = metadata_merge
        if metadata_remove_keys is not None:
            body['metadata_remove_keys'] = metadata_remove_keys
        if delegates_add is not None:
            body['delegates_add'] = delegates_add
        if delegates_remove is not None:
            body['delegates_remove'] = delegates_remove

        response = requests.patch(f"{self.base_url}/notetaker/notes", headers=self.headers, json=body)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def save_report(self, content: str, agent: Optional[str] = None,
                    report_type: str = 'user', date: Optional[str] = None,
                    event: Optional[str] = None,
                    visible_to_participants: Optional[bool] = None) -> Dict[str, Any]:
        """Save a user-provided report as a system note.

        Args:
            content: Markdown content (may include YAML frontmatter)
            agent: Agent name (extracted from frontmatter if not provided)
            report_type: Report type (default: 'user')
            date: Report date in ISO format (extracted from frontmatter if not provided)
            event: Event name for visibility scoping (optional)
            visible_to_participants: If True, participants can see; if False, admin-only (optional)

        Returns:
            Dictionary with saved note info including unique_id
        """
        body = {'content': content, 'report_type': report_type}
        if agent is not None:
            body['agent'] = agent
        if date is not None:
            body['date'] = date
        if event is not None:
            body['event'] = event
        if visible_to_participants is not None:
            body['visible_to_participants'] = visible_to_participants

        response = requests.post(f"{self.base_url}/notetaker/reports/save", headers=self.headers, json=body)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def get_attachment(self, attachment_id: int) -> bytes:
        """Get attachment content by ID.

        Args:
            attachment_id: Attachment database ID

        Returns:
            Attachment content as bytes
        """
        response = requests.get(f"{self.base_url}/notetaker/attachments/{attachment_id}", headers=self.headers)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.content

    def get_attachment_by_unique_id(self, unique_id: str) -> Tuple[bytes, str, str]:
        """Get attachment content by unique_id (supports prefix matching).

        Args:
            unique_id: Attachment unique ID or prefix (minimum 2 characters)

        Returns:
            Tuple of (content_bytes, mime_type, filename)
        """
        response = requests.get(
            f"{self.base_url}/notetaker/attachments/{unique_id}",
            headers=self.headers
        )
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()

        # Extract filename from Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        filename = 'attachment'
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[1].strip('"')

        mime_type = response.headers.get('Content-Type', 'application/octet-stream')

        return response.content, mime_type, filename

    def download_resource(self, unique_id: str) -> Tuple[bytes, str, str]:
        """Download note, attachment, or file by unique_id.

        Auto-detects resource type from unique_id case pattern.
        Supports prefix matching (minimum 2 characters).
        Supports version syntax for files (AB12345678+2).

        Args:
            unique_id: Resource unique ID or prefix

        Returns:
            Tuple of (content_bytes, mime_type, filename)
        """
        response = requests.get(
            f"{self.base_url}/download/{unique_id}",
            headers=self.headers
        )
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()

        # Extract filename from Content-Disposition header
        content_disp = response.headers.get('Content-Disposition', '')
        filename = 'download'
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[1].strip('"')

        mime_type = response.headers.get('Content-Type', 'application/octet-stream')

        return response.content, mime_type, filename

    def list_files(self, system: bool = False) -> Dict[str, Any]:
        """List files in filedb.

        Args:
            system: Whether to access system namespace (superuser only)

        Returns:
            Dictionary with file listing
        """
        params = {'system': system}
        response = requests.get(f"{self.base_url}/filedb/files", headers=self.headers, params=params)
        if response.status_code == 404:
            raise Exception(f"Endpoint not found: GET /filedb/files - FileDB endpoints may not be registered on the server")
        elif response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def read_file(self, basename: str, system: bool = False, version: int = None) -> Dict[str, Any]:
        """Read a file from filedb.

        Args:
            basename: Base filename without extension
            system: Whether to access system namespace (superuser only)
            version: Optional version number

        Returns:
            Dictionary with file content and metadata
        """
        params = {'system': system}
        if version is not None:
            params['version'] = version

        response = requests.get(f"{self.base_url}/filedb/files/{basename}", headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def write_file(self, basename: str, content: str, system: bool = False,
                   reshare: bool = False, share_with: Optional[List[int]] = None) -> Dict[str, Any]:
        """Write content to a file in filedb.

        Args:
            basename: Base filename without extension
            content: Content to write to the file
            system: Whether to access system namespace (superuser only)
            reshare: If True, copy sharing from previous version to new version
            share_with: List of user IDs to share the new version with

        Returns:
            Dictionary with operation result and file metadata
        """
        data = {
            'content': content,
            'system': system
        }
        if reshare:
            data['reshare'] = True
        if share_with:
            data['share_with'] = share_with

        response = requests.put(
            f"{self.base_url}/filedb/files/{basename}",
            headers=self.headers,
            json=data
        )
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        elif response.status_code == 400:
            # Handle specific case where file doesn't exist
            try:
                error_data = response.json()
                error_msg = error_data.get('detail', 'Bad Request')
                if 'not found' in error_msg.lower() or 'does not exist' in error_msg.lower():
                    namespace = "system" if system else "user"
                    raise Exception(f"File '{basename}' does not exist in {namespace} namespace. "
                                  f"Create it first with: aigon filedb create {basename}" +
                                  (" --sys" if system else ""))
                else:
                    raise Exception(f"Bad Request: {error_msg}")
            except ValueError:
                # Response is not JSON
                raise Exception(f"Bad Request: {response.text}")
        response.raise_for_status()
        return response.json()

    def create_file(self, basename: str, system: bool = False) -> Dict[str, Any]:
        """Create a new empty file in filedb.

        Args:
            basename: Base filename without extension
            system: Whether to access system namespace (superuser only)

        Returns:
            Dictionary with operation result and file metadata
        """
        params = {'system': system}

        response = requests.post(f"{self.base_url}/filedb/files/{basename}/create",
                                headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def delete_file(self, basename: str, system: bool = False) -> Dict[str, Any]:
        """Delete a file from filedb.

        Args:
            basename: Base filename without extension
            system: Whether to access system namespace (superuser only)

        Returns:
            Dictionary with operation result
        """
        params = {'system': system}

        response = requests.delete(f"{self.base_url}/filedb/files/{basename}",
                                  headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def archive_file(self, basename: str, system: bool = False) -> Dict[str, Any]:
        """Archive a file (set status to 'archived').

        Archived files are hidden from normal listings but preserved and can be restored.

        Args:
            basename: Base filename without extension
            system: Whether to access system namespace (superuser only)

        Returns:
            Dictionary with operation result
        """
        params = {'system': system}

        response = requests.post(f"{self.base_url}/filedb/files/{basename}/archive",
                                headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def unarchive_file(self, basename: str, system: bool = False) -> Dict[str, Any]:
        """Restore archived or deleted file to active status.

        Args:
            basename: Base filename without extension
            system: Whether to access system namespace (superuser only)

        Returns:
            Dictionary with operation result
        """
        params = {'system': system}

        response = requests.post(f"{self.base_url}/filedb/files/{basename}/unarchive",
                                headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def search_files(self,
                    query: str,
                    filename: Optional[str] = None,
                    include_current: bool = True,
                    include_archived: bool = False,
                    include_deleted: bool = False,
                    include_all_versions: bool = False,
                    limit: int = 10,
                    max_content_length: int = -1,
                    system: bool = False) -> Dict[str, Any]:
        """Search through FileDB files by content and/or filename with flexible constraints.

        Args:
            query: Search query string for content matching
            filename: Optional filename pattern with wildcards (*, ?)
            include_current: Include active files in results
            include_archived: Include archived files in results
            include_deleted: Include deleted files in results
            include_all_versions: Include all versions, not just latest
            limit: Maximum number of results to return
            max_content_length: Maximum content length to return (-1 = no limit)
            system: Access system namespace (superuser only)

        Returns:
            Dictionary with search results and metadata
        """
        params = {
            'query': query,
            'include_current': include_current,
            'include_archived': include_archived,
            'include_deleted': include_deleted,
            'include_all_versions': include_all_versions,
            'limit': limit,
            'max_content_length': max_content_length,
            'system': system
        }

        # Add filename parameter only if provided
        if filename is not None:
            params['filename'] = filename

        response = requests.get(f"{self.base_url}/filedb/search", headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def share_file(self, basename: str, user_ids: List[int],
                   version: int = None, system: bool = False) -> Dict[str, Any]:
        """Share file with users.

        Args:
            basename: Base filename without extension
            user_ids: List of user IDs to share with
            version: Specific version to share (None for latest)
            system: Whether to access system namespace

        Returns:
            Dictionary with operation result
        """
        data = {
            'user_ids': user_ids,
            'system': system
        }
        if version is not None:
            data['version'] = version

        response = requests.post(
            f"{self.base_url}/filedb/files/{basename}/share",
            headers=self.headers,
            json=data
        )
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def unshare_file(self, basename: str, system: bool = False) -> Dict[str, Any]:
        """Remove all sharing from all versions of file.

        Args:
            basename: Base filename without extension
            system: Whether to access system namespace

        Returns:
            Dictionary with operation result
        """
        data = {'system': system}

        response = requests.post(
            f"{self.base_url}/filedb/files/{basename}/unshare",
            headers=self.headers,
            json=data
        )
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def list_shared_files(self) -> Dict[str, Any]:
        """List files shared with current user.

        Returns:
            Dictionary with list of shared files
        """
        response = requests.get(f"{self.base_url}/filedb/shared", headers=self.headers)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def list_files_i_shared(self, system: bool = False) -> Dict[str, Any]:
        """List files that current user has shared with others.

        Args:
            system: Whether to access system namespace

        Returns:
            Dictionary with list of shared files and details
        """
        params = {'system': system}
        response = requests.get(f"{self.base_url}/filedb/sharing", headers=self.headers, params=params)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def get_api_info(self) -> Dict[str, Any]:
        """Get API server information.

        Returns:
            Dictionary with API information
        """
        response = requests.get(f"{self.base_url}/", headers=self.headers)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def get_health(self) -> Dict[str, Any]:
        """Get API health status.

        Returns:
            Dictionary with health information
        """
        response = requests.get(f"{self.base_url}/health", headers=self.headers)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()

    def list_endpoints(self) -> Dict[str, Any]:
        """List all available API endpoints (requires authentication).

        Returns:
            Dictionary with endpoint information
        """
        response = requests.get(f"{self.base_url}/endpoints", headers=self.headers)
        if response.status_code in [401, 403]:
            self._handle_auth_error(response)
        response.raise_for_status()
        return response.json()


def main():
    """Example usage of the Agent01 client."""
    import os

    # Get API token from environment or prompt user
    api_token = os.getenv("AGENT01_API_TOKEN")
    if not api_token:
        print("No API token found. Set AGENT01_API_TOKEN environment variable")
        print("or get a token from the auth bot.")
        return

    # Create client
    client = Agent01Client(api_token=api_token)

    try:
        # Test basic endpoints
        print("=== API Information ===")
        info = client.get_api_info()
        print(json.dumps(info, indent=2))

        print("\n=== Health Check ===")
        health = client.get_health()
        print(json.dumps(health, indent=2))

        print("\n=== Available Endpoints ===")
        endpoints = client.list_endpoints()
        for endpoint in endpoints.get('endpoints', []):
            print(f"{endpoint['method']} {endpoint['path']} - {endpoint.get('description', 'No description')}")

        print("\n=== Recent Notes ===")
        notes = client.get_recent_notes(limit=5)
        print(f"Found {len(notes)} recent notes")
        for note in notes[:3]:  # Show first 3
            print(f"- {note.get('content_type', 'text')}: {note.get('processed_content', '')[:100]}...")

        print("\n=== Search Notes ===")
        search_results = client.search_notes("test", limit=3)
        print(f"Found {len(search_results)} notes matching 'test'")

        print("\n=== FileDB Operations ===")

        # List files
        files = client.list_files()
        print(f"Files in user namespace: {len(files.get('files', []))}")

        # Write a test file
        print("Writing test file...")
        write_result = client.write_file("test-api", "Hello from REST API!")
        print(f"Write result: {write_result.get('success', False)}")

        # Read the file back
        print("Reading test file...")
        file_content = client.read_file("test-api")
        if file_content.get('success'):
            print(f"File content: {file_content.get('content', '')[:100]}...")
        else:
            print("Failed to read file")

        # List files again to show the new file
        files_after = client.list_files()
        print(f"Files after write: {len(files_after.get('files', []))}")

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
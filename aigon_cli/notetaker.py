"""Notetaker commands for Aigon CLI.

This module provides command-line interface functions for Notetaker operations
including search and recent notes retrieval.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

from .client import AigonClient


def parse_date_to_timestamp(date_str: str) -> int:
    """Parse ISO date string to Unix timestamp.

    Supports:
    - ISO format: 2025-12-13, 2025-12-13T10:30:00, 2025-12-13T10:30:00Z
    - Unix timestamp: 1733011200 (passed through if already numeric)

    Args:
        date_str: Date string in ISO format or Unix timestamp

    Returns:
        Unix timestamp (seconds)

    Raises:
        ValueError: If date string cannot be parsed
    """
    # Check if it's already a Unix timestamp
    try:
        ts = int(date_str)
        if ts > 1000000000:  # Reasonable Unix timestamp (after 2001)
            return ts
    except ValueError:
        pass

    # Parse ISO format using stdlib
    try:
        # Try full ISO format with timezone
        if 'T' in date_str:
            # Handle Z suffix
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(date_str)
        else:
            # Date only - assume start of day UTC
            dt = datetime.fromisoformat(date_str)
            dt = dt.replace(tzinfo=timezone.utc)

        # Ensure timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return int(dt.timestamp())
    except ValueError as e:
        raise ValueError(f"Cannot parse date '{date_str}'. Use ISO format (e.g., 2025-12-13) or Unix timestamp.") from e


def parse_context(context_str: str) -> tuple:
    """Parse context string into (before_count, after_count).

    Args:
        context_str: Context specification string:
            - "0" = no context
            - "-N" = N notes before only
            - "+N" = N notes after only
            - "N" = symmetric (N before and N after)

    Returns:
        (before, after) tuple of ints

    Raises:
        ValueError: If context string cannot be parsed
    """
    context_str = context_str.strip()
    if not context_str or context_str == '0':
        return (0, 0)

    if context_str.startswith('-'):
        n = int(context_str[1:])
        return (n, 0)  # N before, 0 after
    elif context_str.startswith('+'):
        n = int(context_str[1:])
        return (0, n)  # 0 before, N after
    else:
        n = int(context_str)
        return (n, n)  # Symmetric


def clear_local(directory: str = "_notes") -> None:
    """Clear local notes directory.

    Args:
        directory: Directory to clear (default: _notes)
    """
    if os.path.exists(directory):
        shutil.rmtree(directory)
        print(f"Cleared directory: {directory}")
    else:
        print(f"Directory does not exist: {directory}")


def _format_note_snippet(note: dict, max_content_chars: int = 100) -> str:
    """Format a single note as ultra-concise one-liner for quick scanning.

    Args:
        note: Note dictionary from API
        max_content_chars: Maximum characters of content to show (default: 100)

    Returns:
        Single-line formatted string: "abc123 | 2025-12-01 | Content preview..."
    """
    # Short ID (6 chars)
    unique_id = note.get('unique_id', 'unknown')
    short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id

    # Date and time (compact format, no separators)
    created_at = note.get('created_at')
    if created_at:
        try:
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
            date_str = dt.strftime('%Y%m%d %H%M')
        except (ValueError, TypeError):
            date_str = 'unknown'
    else:
        date_str = 'unknown'

    # Content preview (first N chars, replace newlines with spaces)
    content = note.get('content', '')
    content_preview = content.replace('\n', ' ').replace('\r', '')[:max_content_chars]
    if len(content) > max_content_chars:
        content_preview += '...'

    return f"{short_id} | {date_str} | {content_preview}"


def _format_note_summary(note: dict) -> str:
    """Format a single note showing only summary and content length.

    Args:
        note: Note dictionary from API

    Returns:
        Single-line formatted string: "abc123 | 2025-12-01 | len:1234 | Summary text..."
    """
    # Short ID (6 chars)
    unique_id = note.get('unique_id', 'unknown')
    short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id

    # Date and time (compact format)
    created_at = note.get('created_at')
    if created_at:
        try:
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
            date_str = dt.strftime('%Y%m%d %H%M')
        except (ValueError, TypeError):
            date_str = 'unknown'
    else:
        date_str = 'unknown'

    # Content length
    content = note.get('content', '')
    content_len = len(content)

    # Summary (or placeholder if not set)
    summary = note.get('summary', '(no summary)')

    return f"{short_id} | {date_str} | len:{content_len} | {summary}"


def _format_note_llm(note: dict, show_user_id: bool = False) -> str:
    """Format a single note in LLM-friendly YAML-lite format.

    Args:
        note: Note dictionary from API
        show_user_id: Whether to include user_id (for event mode when viewing other users' notes)

    Returns:
        Formatted string for LLM consumption
    """
    # Extract fields
    unique_id = note.get('unique_id', 'unknown')
    short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
    content_type = note.get('content_type', 'text')
    content = note.get('content', '')
    processed = 'yes' if note.get('processed_at') else 'no'

    # Format created_at with full date including day of week
    created_at_ts = note.get('created_at')
    if created_at_ts:
        try:
            dt = datetime.fromtimestamp(int(created_at_ts), tz=timezone.utc)
            created_at = dt.strftime('%a %Y-%m-%d %H:%M:%S UTC')
        except (ValueError, TypeError):
            created_at = 'unknown'
    else:
        created_at = 'unknown'

    # Format updated_at with full date including day of week
    updated_at_ts = note.get('updated_at')
    if updated_at_ts:
        try:
            dt = datetime.fromtimestamp(int(updated_at_ts), tz=timezone.utc)
            updated_at = dt.strftime('%a %Y-%m-%d %H:%M:%S UTC')
        except (ValueError, TypeError):
            updated_at = None
    else:
        updated_at = None

    # Build formatted output
    lines = [
        "--- BEGIN NOTE ---",
        f"unique_id: {short_id} [{unique_id}]",
    ]

    # Only show user_id_pk_int in event mode (viewing other users' notes)
    if show_user_id:
        user_id_pk_int = note.get('user_id_pk_int', 'unknown')
        lines.append(f"user_id_pk_int: {user_id_pk_int}")

    lines.append(f"created_at: {created_at}")

    # Only show updated_at if different from created_at
    if updated_at and updated_at != created_at:
        lines.append(f"updated_at: {updated_at}")

    lines.append(f"content_type: {content_type}")
    lines.append(f"processed: {processed}")

    # Add new metadata fields
    summary = note.get('summary')
    if summary:
        lines.append(f"summary: {summary}")

    # Always show tags and delegates (even if empty)
    tags = note.get('tags', [])
    tags_str = ', '.join(tags) if tags else '[]'
    lines.append(f"tags: {tags_str}")

    delegates = note.get('delegates', [])
    delegates_str = ', '.join(delegates) if delegates else '[]'
    lines.append(f"delegates: {delegates_str}")

    # Show attachments (unique_id and filename)
    attachment_list = []
    for att in note.get('attachments', []):
        unique_id = att.get('unique_id', 'unknown')
        filename = att.get('filename', 'unknown')
        size = att.get('size') or att.get('content_size') or 0
        # Format: unique_id:filename (size bytes)
        attachment_list.append(f"{unique_id}:{filename} ({size} bytes)")

    attachments_str = str(attachment_list) if attachment_list else '[]'
    lines.append(f"attachments: {attachments_str}")

    # Show public URL if share_signature is present
    share_signature = note.get('share_signature')
    if share_signature:
        note_unique_id = note.get('unique_id', '')
        public_url = f"https://api.aigon.ai/n/{note_unique_id}:{share_signature}"
        lines.append(f"public_url: {public_url}")

    lines.extend([
        "content: ---",
        content,
        "---",
        "--- END NOTE ---"
    ])

    return '\n'.join(lines)


def _save_notes_to_files(notes, directory: str, clear_directory: bool = False, client=None):
    """Save notes as individual markdown files, with attachments if client provided.

    Args:
        notes: List of note dictionaries
        directory: Directory to save files to
        clear_directory: Whether to clear directory before saving
        client: AigonClient instance for downloading attachments (optional)
    """
    # Clear directory before saving notes if requested
    if clear_directory:
        clear_local(directory)

    # Create directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)

    if not notes:
        print("No notes found to save")
        return []

    saved_files = []
    for note in notes:
        # Generate filename from created_at timestamp
        unique_id = note.get('unique_id', note.get('id', 'unknown'))
        content_type = note.get('content_type', 'text')
        created_at = note.get('created_at')

        # Convert created_at to proper datetime format for filename
        try:
            if created_at:
                # Convert Unix timestamp to datetime
                dt_utc = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
                # Format as YYYYMMDD_HHMM
                date_prefix = dt_utc.strftime("%Y%m%d_%H%M")
            else:
                date_prefix = "unknown"
        except (ValueError, TypeError):
            date_prefix = "unknown"

        # Create filename with date prefix and unique_id
        uid_short = unique_id[:6] if unique_id and unique_id != 'unknown' else 'unknown'
        filename = f"{date_prefix}_{content_type}_{uid_short}.md"
        filepath = os.path.join(directory, filename)

        # Prepare content - use full content, no truncation
        content = note.get('content', note.get('processed_content', note.get('original_content', '')))

        # Create metadata header with proper YAML frontmatter
        metadata = "---\n"
        metadata += f"type: {content_type}\n"

        # Add time information in multiple formats
        if created_at:
            try:
                created_ts = int(created_at)
                dt_utc = datetime.fromtimestamp(created_ts, tz=timezone.utc)
                dt_local = datetime.fromtimestamp(created_ts)

                local_tz = dt_local.strftime('%Z') or time.tzname[0]
                metadata += f"created_at: \"{dt_local.strftime('%Y-%m-%d %H:%M:%S')} {local_tz}\"\n"
                metadata += f"created_at_utc: \"{dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}\"\n"
                metadata += f"created_at_ts: {created_ts}\n"
            except (ValueError, TypeError):
                metadata += f"created_at: {created_at}\n"
        else:
            metadata += "created_at: unknown\n"

        # Add export and processed timestamps in Zulu format
        exported_at = note.get('exported_at')
        if exported_at:
            try:
                exported_ts = int(exported_at)
                exported_dt = datetime.fromtimestamp(exported_ts, tz=timezone.utc)
                metadata += f"exported_at: \"{exported_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}\"\n"
            except (ValueError, TypeError):
                metadata += f"exported_at: {exported_at}\n"

        processed_at = note.get('processed_at')
        if processed_at:
            try:
                processed_ts = int(processed_at)
                processed_dt = datetime.fromtimestamp(processed_ts, tz=timezone.utc)
                metadata += f"processed_at: \"{processed_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}\"\n"
            except (ValueError, TypeError):
                metadata += f"processed_at: {processed_at}\n"

        # Add new metadata fields
        summary = note.get('summary')
        if summary:
            # Escape quotes in summary for YAML
            escaped_summary = summary.replace('"', '\\"')
            metadata += f"summary: \"{escaped_summary}\"\n"

        # Always include tags and delegates (even if empty)
        tags = note.get('tags', [])
        metadata += f"tags: {tags}\n"

        delegates = note.get('delegates', [])
        metadata += f"delegates: {delegates}\n"

        metadata += "---\n\n"
        metadata += f"# Note {unique_id}\n\n"

        full_content = metadata + content

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)

        saved_files.append(filepath)

        # Download attachments if client is available (skip voice/audio — use `aigon download` for those)
        if client:
            attachments = note.get('attachments', [])
            for i, att in enumerate(attachments, 1):
                att_uid = att.get('unique_id')
                if not att_uid:
                    continue
                att_type = (att.get('file_type') or att.get('content_type') or '').lower()
                if att_type == 'voice':
                    continue
                try:
                    att_data, _mime_type, original_name = client.get_attachment_by_unique_id(att_uid)
                    if att_data:
                        att_type = att.get('file_type') or att.get('content_type') or 'file'
                        att_filename = _attachment_download_filename(unique_id, i, att_uid, att_type, original_name)
                        att_path = os.path.join(directory, att_filename)
                        with open(att_path, 'wb') as f:
                            f.write(att_data)
                        saved_files.append(att_path)
                except Exception as e:
                    print(f"  Warning: failed to download attachment {att_uid}: {e}", file=sys.stderr)

    print(f"Saved {len(saved_files)} files to {directory}/:")
    for filepath in saved_files:
        print(f"  - {os.path.basename(filepath)}")

    return saved_files


def _sanitize_note_for_output(note: dict) -> dict:
    """Remove internal fields from note before outputting.

    Args:
        note: Note dictionary from API

    Returns:
        Sanitized note dictionary without internal fields
    """
    # Fields that should never be exposed externally
    internal_fields = {'id', 'user_id_pk_int', 'agent', 'att_id', 'att_filename',
                       'att_original_filename', 'att_file_type', 'att_mime_type',
                       'att_content_size'}

    return {k: v for k, v in note.items() if k not in internal_fields}


def search_notes(client: AigonClient, query: str, content_type: Optional[str] = None,
                limit: int = 10, output_format: Optional[str] = None,
                download_directory: Optional[str] = None,
                clear_directory: bool = False,
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
                strategy: str = "hybrid",
                mode: str = "websearch",
                similarity_threshold: float = 0.3,
                order_by: str = "relevance",
                order_dir: str = "desc",
                offset: int = 0,
                file_type: Optional[str] = None,
                mime_type: Optional[str] = None,
                tags: Optional[str] = None,
                exclude_tags: Optional[str] = None) -> None:
    """Search notes in Notetaker with advanced filtering.

    Args:
        client: Authenticated Aigon client
        query: Search query string
        content_type: Optional content type filter (text, audio, image)
        limit: Maximum number of results
        output_format: Output format (json, llm) - default: llm for stdout, json for download
        download_directory: Directory to download files to (None = stdout mode, str = download)
        clear_directory: Whether to clear directory before downloading (only with download_directory)
        scope: Search scope (notes, attachments, all) - default: all (searches both)
        time_window_start: Days back to start search (None = all time). Ignored if start_ts is set.
        time_window_end: Days back to end search (default: 0.0 = now). Ignored if end_ts is set.
        start_ts: Absolute start timestamp (Unix seconds). Overrides time_window_start.
        end_ts: Absolute end timestamp (Unix seconds). Overrides time_window_end.
        time_field: Which timestamp to filter on: 'created' or 'updated'.
                   Default: 'created' for absolute, 'updated' for relative.
        export_status: Filter by export status (all, unexported, exported)
        processed_status: Filter by processed status (all, unprocessed, processed)
        deleted_status: Filter by deleted status (active, deleted, all) - default: active
        max_content_length: Maximum content length (-1 = no limit)
        note_type: Filter by note type (user, system, all) - default: user
        reverse: If True with limit, get the N most recent notes instead of oldest N
        agent_filter: Filter by agent (shows notes owned by OR delegated to this agent)
        show_delegated: Include notes delegated to you (default: True)
    """
    try:
        # Determine default format
        if download_directory is not None:
            # Download mode (default to json format)
            if output_format is None:
                output_format = "json"
        else:
            # Stdout mode (default to llm format)
            if output_format is None:
                output_format = "llm"

        # FTS search returns minimal data - get unique_ids then fetch full notes
        fts_results = client.search_notes(
            query=query,
            content_type=content_type,
            limit=limit,
            scope=scope,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            start_ts=start_ts,
            end_ts=end_ts,
            time_field=time_field,
            export_status=export_status,
            processed_status=processed_status,
            deleted_status=deleted_status,
            max_content_length=max_content_length,
            note_type=note_type,
            reverse=reverse,
            agent_filter=agent_filter,
            show_delegated=show_delegated,
            with_attachments=True,
            strategy=strategy,
            mode=mode,
            similarity_threshold=similarity_threshold,
            order_by=order_by,
            order_dir=order_dir,
            offset=offset,
            file_type=file_type,
            mime_type=mime_type,
            tags=tags,
            exclude_tags=exclude_tags,
        )

        # Full format: dump raw API response with match metadata (scores, match_types, relevance)
        if output_format == "full":
            print(json.dumps(fts_results, indent=2))
            return

        # Extract unique_ids from FTS results and fetch full notes
        if fts_results:
            unique_ids = [r.get('unique_id') for r in fts_results if r.get('unique_id')]
            if unique_ids:
                result = client.get_notes_by_ids(unique_ids, with_attachments=True)
            else:
                result = []
        else:
            result = []

        # Check if download mode or stdout mode
        if download_directory is not None:
            # Download mode: save to files
            _save_notes_to_files(result, download_directory, clear_directory, client=client)
        else:
            # Stdout mode: output to console
            if output_format == "json":
                # Sanitize notes before outputting
                sanitized = [_sanitize_note_for_output(note) for note in result]
                print(json.dumps(sanitized, indent=2))
            elif output_format == "snippet":
                if not result:
                    print(f"No notes found matching '{query}'")
                    return
                # Ultra-concise one-liner per note
                for note in result:
                    print(_format_note_snippet(note))
            elif output_format == "summary":
                if not result:
                    print(f"No notes found matching '{query}'")
                    return
                # Summary only with content length
                for note in result:
                    print(_format_note_summary(note))
            elif output_format == "llm":
                if not result:
                    print(f"No notes found matching '{query}'")
                    return

                # Format all notes in LLM format
                for note in result:
                    print(_format_note_llm(note))
                    print()
            else:
                print(f"Unknown output format: {output_format}", file=sys.stderr)
                sys.exit(1)

    except Exception as e:
        print(f"Error searching notes: {e}", file=sys.stderr)
        sys.exit(1)


def recent_notes(client: AigonClient, limit: int = 10, output_format: Optional[str] = None,
                download_directory: Optional[str] = None, clear_directory: bool = False,
                max_bytes: int = 5000, max_bytes_llm: int = 5000,
                processed_status: str = 'unprocessed',
                note_type: str = 'user',
                time_window_start: Optional[float] = 3.0,
                time_window_end: float = 0.0,
                start_ts: Optional[int] = None,
                end_ts: Optional[int] = None,
                time_field: Optional[str] = None,
                reverse: bool = False,
                agent_filter: Optional[str] = None,
                show_delegated: bool = True,
                event: Optional[str] = None) -> None:
    """Get recent notes from Notetaker.

    Default filters: last 3 days, unprocessed notes only, all export statuses, user notes only.

    Args:
        client: Authenticated Aigon client
        limit: Maximum number of notes to return
        output_format: Output format (json, llm) - used only in stdout mode.
                      Default: llm for stdout, json for download
        download_directory: Directory to download files to (None = stdout mode, str = download)
        clear_directory: Whether to clear directory before downloading (only with download_directory)
        max_bytes: Maximum total response size in bytes (default: 5000, -1 = no limit)
                   Only applies to JSON format
        max_bytes_llm: Maximum total size for all notes in LLM format (default: 5000, -1 = no limit)
                      Only applies to LLM format
        processed_status: Filter by processed status (default: unprocessed)
        note_type: Filter by note type (user, system, all) - default: user
        time_window_start: Days back to start (3.0 = 3 days ago, None = all time). Ignored if start_ts is set.
        time_window_end: Days back to end (0.0 = now). Ignored if end_ts is set.
        start_ts: Absolute start timestamp (Unix seconds). Overrides time_window_start.
        end_ts: Absolute end timestamp (Unix seconds). Overrides time_window_end.
        time_field: Which timestamp to filter on: 'created' or 'updated'.
                   Default: 'created' for absolute, 'updated' for relative.
        reverse: If True with limit, get the N most recent notes instead of oldest N
        agent_filter: Filter by agent (shows notes owned by OR delegated to this agent)
        show_delegated: Include notes delegated to you (default: True)
        event: Event name to access participant notes (admin only). Empty results may indicate not authorized.
    """
    try:
        # Determine default format
        if download_directory is not None:
            # Download mode (default to json format)
            if output_format is None:
                output_format = "json"
        else:
            # Stdout mode (default to llm format)
            if output_format is None:
                output_format = "llm"

        # Download mode: never truncate
        # Stdout mode: LLM/snippet truncate client-side, JSON uses max_bytes server-side
        if download_directory is not None:
            api_max_bytes = -1  # Never truncate downloads
        elif output_format in ("llm", "snippet"):
            api_max_bytes = -1  # Truncate client-side
        else:
            api_max_bytes = max_bytes
        result = client.get_recent_notes(limit=limit, max_bytes=api_max_bytes,
                                        processed_status=processed_status,
                                        note_type=note_type,
                                        time_window_start=time_window_start,
                                        time_window_end=time_window_end,
                                        start_ts=start_ts,
                                        end_ts=end_ts,
                                        time_field=time_field,
                                        reverse=reverse,
                                        agent_filter=agent_filter,
                                        show_delegated=show_delegated,
                                        event=event)

        # Check if download mode or stdout mode
        if download_directory is not None:
            # Download mode: save to files
            _save_notes_to_files(result, download_directory, clear_directory, client=client)
        else:
            # Stdout mode: output to console
            if output_format == "json":
                # Sanitize notes before outputting
                sanitized = [_sanitize_note_for_output(note) for note in result]
                print(json.dumps(sanitized, indent=2))
            elif output_format == "snippet":
                if not result:
                    print("No recent notes found")
                    return
                # Ultra-concise one-liner per note
                for note in result:
                    print(_format_note_snippet(note))
            elif output_format == "summary":
                if not result:
                    print("No recent notes found")
                    return
                # Summary only with content length
                for note in result:
                    print(_format_note_summary(note))
            elif output_format == "llm":
                if not result:
                    print("No recent notes found")
                    return

                # Format all notes first (show user_id in event mode)
                show_user_id = event is not None
                formatted_notes = [_format_note_llm(note, show_user_id=show_user_id) for note in result]

                # Check total size and truncate ALL content if exceeded
                if max_bytes_llm > 0:
                    # Calculate total size
                    total_output = '\n\n'.join(formatted_notes)
                    total_size = len(total_output.encode('utf-8'))

                    if total_size > max_bytes_llm:
                        # Truncate ALL notes' content (signal to LLM to fetch in smaller chunks)
                        formatted_notes = []
                        for note in result:
                            note_copy = note.copy()
                            note_copy['content'] = "(truncated)"
                            formatted_notes.append(_format_note_llm(note_copy, show_user_id=show_user_id))

                # Print all formatted notes
                for formatted in formatted_notes:
                    print(formatted)
                    print()  # Empty line between notes
            else:
                print(f"Unknown output format: {output_format}", file=sys.stderr)
                sys.exit(1)

    except Exception as e:
        print(f"Error getting recent notes: {e}", file=sys.stderr)
        sys.exit(1)


def get_notes_by_id(client: AigonClient, unique_ids: List[str],
                    output_format: Optional[str] = None,
                    download_directory: Optional[str] = None,
                    clear_directory: bool = False,
                    context_before: int = 0,
                    context_after: int = 0,
                    with_signed_urls: bool = False,
                    agent_filter: Optional[str] = None) -> None:
    """Get notes by unique ID(s) with optional context.

    Args:
        client: Authenticated Aigon client
        unique_ids: List of unique IDs or prefixes (minimum 2 characters each)
        output_format: Output format (json, llm) - default: llm for stdout, json for download
        download_directory: Directory to download files to (None = stdout mode)
        clear_directory: Whether to clear directory before downloading
        context_before: Number of notes before each target to include
        context_after: Number of notes after each target to include
        with_signed_urls: Include share_signature for public URL generation
        agent_filter: Filter by agent (e.g. 'mailbox') to find notes owned by that agent
    """
    try:
        notes = client.get_notes_by_ids(unique_ids,
                                        context_before=context_before,
                                        context_after=context_after,
                                        with_attachments=True,
                                        with_share_signature=with_signed_urls,
                                        agent_filter=agent_filter)

        if not notes:
            print("No notes found")
            return

        # Determine default format
        if download_directory is not None:
            if output_format is None:
                output_format = "json"
        else:
            if output_format is None:
                output_format = "llm"

        # Check if download mode or stdout mode
        if download_directory is not None:
            _save_notes_to_files(notes, download_directory, clear_directory, client=client)
        else:
            if output_format == "json":
                # Sanitize notes before outputting
                sanitized = [_sanitize_note_for_output(note) for note in notes]
                print(json.dumps(sanitized, indent=2))
            elif output_format == "snippet":
                # Ultra-concise one-liner per note
                for note in notes:
                    print(_format_note_snippet(note))
            elif output_format == "summary":
                # Summary only with content length
                for note in notes:
                    print(_format_note_summary(note))
            else:
                # LLM format
                for note in notes:
                    print(_format_note_llm(note))
                    print()

    except Exception as e:
        print(f"Error getting notes by ID: {e}", file=sys.stderr)
        sys.exit(1)


def mailbox_reply(client: AigonClient, unique_id: str, text: str,
                  as_markdown: bool = False, delay: int = 5,
                  bcc: list = None) -> None:
    """Reply to a received email.

    Args:
        client: Authenticated Aigon client
        unique_id: Unique ID (or prefix) of the note to reply to
        text: Reply text
        as_markdown: If True, send text as markdown
        delay: Delay in minutes before sending (0 = immediate)
        bcc: Optional BCC recipients
    """
    try:
        kwargs = {'unique_id': unique_id, 'delay': delay}
        if as_markdown:
            kwargs['markdown'] = text
        else:
            kwargs['text'] = text
        if bcc:
            kwargs['bcc'] = bcc

        result = client.mailbox_reply(**kwargs)
        print(f"Reply sent to {result.get('to', '?')} (subject: {result.get('subject', '?')})")
        print(f"  message_id: {result.get('message_id', '?')}")
        print(f"  from: {result.get('from', '?')}")
        if result.get('send_at'):
            print(f"  scheduled: {result['send_at']}")
    except Exception as e:
        print(f"Error sending reply: {e}", file=sys.stderr)
        sys.exit(1)


def mailbox_send(client: AigonClient, to: str, subject: str, text: str,
                 as_markdown: bool = False, delay: int = 5,
                 bcc: list = None) -> None:
    """Send a new email.

    Args:
        client: Authenticated Aigon client
        to: Recipient email address
        subject: Email subject
        text: Email body
        as_markdown: If True, send text as markdown
        delay: Delay in minutes before sending (0 = immediate)
        bcc: Optional BCC recipients
    """
    try:
        kwargs = {'to': to, 'subject': subject, 'delay': delay}
        if as_markdown:
            kwargs['markdown'] = text
        else:
            kwargs['text'] = text
        if bcc:
            kwargs['bcc'] = bcc

        result = client.mailbox_send(**kwargs)
        print(f"Email sent to {to} (subject: {subject})")
        print(f"  message_id: {result.get('message_id', '?')}")
        print(f"  from: {result.get('from', '?')}")
        if result.get('send_at'):
            print(f"  scheduled: {result['send_at']}")
    except Exception as e:
        print(f"Error sending email: {e}", file=sys.stderr)
        sys.exit(1)


def mark_notes(client: AigonClient, unique_ids: list, processed: bool = None,
               exported: bool = None, deleted: bool = None, output_format: str = "llm") -> None:
    """Mark or unmark notes as processed, exported, and/or deleted.

    Args:
        client: Authenticated Aigon client
        unique_ids: List of unique IDs (or prefixes) to mark
        processed: True=mark as processed, False=unmark, None=no change
        exported: True=mark as exported, False=unmark, None=no change
        deleted: True=delete (soft), False=undelete, None=no change
        output_format: Output format (llm for concise, json for full details)

    Note: processed, exported, and deleted are independent flags.
    """
    try:
        result = client.mark_notes(unique_ids=unique_ids, processed=processed,
                                   exported=exported, deleted=deleted)

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            # LLM format: very concise output
            if result.get('success'):
                batch_size = result.get('batch_size', 0)
                actions = []
                if processed is True:
                    actions.append("processed")
                elif processed is False:
                    actions.append("unprocessed")
                if exported is True:
                    actions.append("exported")
                elif exported is False:
                    actions.append("unexported")
                if deleted is True:
                    actions.append("deleted")
                elif deleted is False:
                    actions.append("undeleted")
                action_str = " and ".join(actions) if actions else "updated"
                print(f"Marked {batch_size} note(s) as {action_str}")
            else:
                print(f"Failed: {result.get('message', 'Unknown error')}", file=sys.stderr)
                sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def update_notes(client: AigonClient, unique_ids: list,
                 tags_set: str = None, tags_add: str = None, tags_remove: str = None,
                 summary: str = None,
                 metadata_set: str = None, metadata_merge: str = None, metadata_remove_keys: str = None,
                 delegates_add: str = None, delegates_remove: str = None,
                 output_format: str = "llm") -> None:
    """Bulk update note metadata: tags, summary, metadata, delegates.

    Args:
        client: Authenticated Aigon client
        unique_ids: List of unique IDs (or prefixes) to update
        tags_set: Comma-separated tags to replace all (e.g., "a,b,c")
        tags_add: Comma-separated tags to add
        tags_remove: Comma-separated tags to remove
        summary: Set summary text (use "" to clear)
        metadata_set: JSON string to replace entire metadata
        metadata_merge: JSON string to merge into metadata
        metadata_remove_keys: Comma-separated keys to remove from metadata
        delegates_add: Comma-separated agents to add (e.g., "coach,wellness")
        delegates_remove: Comma-separated agents to remove
        output_format: Output format (llm for one-line, json for full record)
    """
    try:
        # Parse comma-separated lists
        tags_set_list = [t.strip() for t in tags_set.split(',')] if tags_set is not None else None
        tags_add_list = [t.strip() for t in tags_add.split(',')] if tags_add else None
        tags_remove_list = [t.strip() for t in tags_remove.split(',')] if tags_remove else None
        delegates_add_list = [a.strip() for a in delegates_add.split(',')] if delegates_add else None
        delegates_remove_list = [a.strip() for a in delegates_remove.split(',')] if delegates_remove else None
        meta_remove_keys_list = [k.strip() for k in metadata_remove_keys.split(',')] if metadata_remove_keys else None

        # Parse JSON strings for metadata
        meta_set_dict = json.loads(metadata_set) if metadata_set else None
        meta_merge_dict = json.loads(metadata_merge) if metadata_merge else None

        result = client.update_notes(
            unique_ids=unique_ids,
            tags_set=tags_set_list,
            tags_add=tags_add_list,
            tags_remove=tags_remove_list,
            summary=summary,
            metadata_set=meta_set_dict,
            metadata_merge=meta_merge_dict,
            metadata_remove_keys=meta_remove_keys_list,
            delegates_add=delegates_add_list,
            delegates_remove=delegates_remove_list,
        )

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            if result.get('success'):
                batch_size = result.get('batch_size', 0)
                operations = result.get('operations', [])
                ops_str = ", ".join(operations) if operations else "updated"
                print(f"Updated {batch_size} note(s): {ops_str}")
            else:
                print(f"Failed: {result.get('message', 'Unknown error')}", file=sys.stderr)
                sys.exit(1)

    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _attachment_download_filename(note_uid: str, index: int, attachment_uid: str,
                                  content_type: str, original_filename: str) -> str:
    """Build download filename for an attachment.

    Format: {note_id}_{number}_{att_id}_{type}--{original_filename}
    Example: rkmfip_1_sIVLRMR_voice--voice_9147.ogg
    """
    note_short = note_uid[:6] if note_uid else "unknown"
    att_short = attachment_uid[:7] if attachment_uid else "unknown"
    ctype = content_type or "file"
    return f"{note_short}_{index}_{att_short}_{ctype}--{original_filename}"


def get_attachment(client: AigonClient, note_id: str, filename: str = None,
                  download_directory: str = None) -> None:
    """Get attachment from note.

    Args:
        client: Authenticated Aigon client
        note_id: Note unique ID (or prefix, minimum 2 characters)
        filename: Attachment filename or index (1, 2, 3...). Default: 1 (first attachment)
        download_directory: Directory to download to. If None, output content to stdout
    """
    try:
        import sys

        # SINGLE ROUND-TRIP: Get note with attachment metadata
        notes = client.get_notes_by_ids(
            [note_id],
            context_before=0,
            context_after=0,
            with_attachments=True
        )

        if not notes:
            print(f"Note not found: {note_id}", file=sys.stderr)
            sys.exit(1)

        note = notes[0]
        note_uid = note.get('unique_id', '')
        attachments = note.get('attachments', [])

        if not attachments:
            print(f"Note {note_id} has no attachments", file=sys.stderr)
            sys.exit(1)

        # Select attachment by index or filename
        selected_att = None
        selected_index = 1  # 1-based

        if filename is not None and filename.isdigit():
            index = int(filename)
            if index < 1 or index > len(attachments):
                print(f"Note has {len(attachments)} attachment(s), cannot get #{index}", file=sys.stderr)
                sys.exit(1)
            selected_att = attachments[index - 1]
            selected_index = index
        elif filename is not None:
            # Match by filename
            for i, att in enumerate(attachments):
                att_filename = att.get('original_filename') or att.get('filename', '')
                if att_filename == filename:
                    selected_att = att
                    selected_index = i + 1
                    break
            if selected_att is None:
                print(f"Attachment '{filename}' not found in note {note_id}", file=sys.stderr)
                print(f"Available: {', '.join(a.get('original_filename') or a.get('filename', '?') for a in attachments)}", file=sys.stderr)
                sys.exit(1)
        else:
            selected_att = attachments[0]

        attachment_unique_id = selected_att.get('unique_id')
        if not attachment_unique_id:
            print("Attachment unique_id not found", file=sys.stderr)
            sys.exit(1)

        # Fetch attachment content
        attachment_data, mime_type, original_name = client.get_attachment_by_unique_id(attachment_unique_id)

        if not attachment_data:
            print("Failed to retrieve attachment content", file=sys.stderr)
            sys.exit(1)

        # Check if MIME type is displayable (text-based)
        is_displayable = mime_type and any(mime_type.startswith(prefix) for prefix in ['text/', 'application/json'])

        # Require --download for non-displayable content
        if not is_displayable and download_directory is None:
            print(f"Error: Attachment has MIME type '{mime_type}' which cannot be displayed to stdout.", file=sys.stderr)
            print("Use --download to save the file.", file=sys.stderr)
            sys.exit(1)

        # Output or download
        if download_directory is not None:
            att_type = selected_att.get('file_type') or selected_att.get('content_type') or 'file'
            out_filename = _attachment_download_filename(
                note_uid, selected_index, attachment_unique_id, att_type, original_name)
            output_path = os.path.join(download_directory, out_filename)
            with open(output_path, 'wb') as f:
                f.write(attachment_data)
            print(f"Downloaded: {output_path}")
        else:
            # Stdout mode (text only)
            sys.stdout.buffer.write(attachment_data)

    except Exception as e:
        print(f"Error getting attachment: {e}", file=sys.stderr)
        sys.exit(1)


def save_report(client: AigonClient, content: str, agent: Optional[str] = None,
                report_type: str = 'user', date: Optional[str] = None,
                event: Optional[str] = None, visible_to_participants: Optional[bool] = None,
                output_format: str = 'llm') -> None:
    """Save a user-provided report markdown file.

    Args:
        client: Authenticated Aigon client
        content: Markdown content to save
        agent: Agent name (optional, extracted from frontmatter if not provided)
        report_type: Report type (default: 'user')
        date: Report date ISO format (optional, extracted from frontmatter if not provided)
        event: Event name for visibility scoping (optional)
        visible_to_participants: If True, participants can see; if False, admin-only (optional)
        output_format: Output format (llm for concise, json for full details)
    """
    try:
        result = client.save_report(
            content=content,
            agent=agent,
            report_type=report_type,
            date=date,
            event=event,
            visible_to_participants=visible_to_participants
        )

        if output_format == "json":
            print(json.dumps(result, indent=2))
        else:
            # LLM format: concise output
            unique_id = result.get('unique_id', 'unknown')[:6]
            agent_out = result.get('agent', 'unknown')
            report_type_out = result.get('report_type', 'unknown')
            report_date = result.get('report_date', 'unknown')
            if 'T' in report_date:
                report_date = report_date.split('T')[0]
            filename = result.get('filename', 'unknown')
            print(f"Saved report [{unique_id}]: {filename} (agent={agent_out}, type={report_type_out}, date={report_date})")

    except Exception as e:
        print(f"Error saving report: {e}", file=sys.stderr)
        sys.exit(1)


def register_notetaker_commands(subparsers):
    """Register Notetaker commands with argument parser.

    Args:
        subparsers: argparse subparsers object
    """
    # Notetaker command group
    notetaker_parser = subparsers.add_parser('notetaker', help='Notetaker operations')
    notetaker_subparsers = notetaker_parser.add_subparsers(dest='notetaker_command', help='Notetaker commands')

    # Search command
    search_parser = notetaker_subparsers.add_parser('search', help='Search notes with advanced filtering')
    search_parser.add_argument('query', help='Search query string')
    search_parser.add_argument('--type', dest='content_type', choices=['text', 'audio', 'image'],
                            help='Filter by content type')
    search_parser.add_argument('--limit', type=int, default=None, help='Maximum results (default: 10 for llm/json, 100 for snippet/summary)')
    search_parser.add_argument('--format', choices=['json', 'llm', 'snippet', 'summary', 'full'], default=None,
                            help='Output format: llm (default), json, snippet, summary, full (raw API response with match scores)')
    search_parser.add_argument('--download', nargs='?', const='_notes', default=None,
                            help='Download notes (with attachments, excluding voice) to files. Optionally specify directory (default: _notes)')
    search_parser.add_argument('--clear', action='store_true',
                            help='Clear directory before downloading notes (requires --download)')

    # Time filtering options (relative - days back)
    search_parser.add_argument('--from', dest='from_days', type=float,
                            help='Days back to start search (e.g., --from 7)')
    search_parser.add_argument('--to', dest='to_days', type=float, default=0.0,
                            help='Days back to end search (default: 0.0 = now)')
    search_parser.add_argument('--days', dest='days_back', type=float,
                            help='Search last N days (shortcut for --from N --to 0)')
    search_parser.add_argument('--recent', action='store_true',
                            help='Search last day (shortcut for --from 1)')
    search_parser.add_argument('--week', action='store_true',
                            help='Search last week (shortcut for --from 7)')
    search_parser.add_argument('--forever', action='store_true',
                            help='All time (no time limit)')

    # Time filtering options (absolute - ISO dates)
    search_parser.add_argument('--start', dest='start_date',
                            help='Absolute start date (ISO format: 2025-12-01 or Unix timestamp)')
    search_parser.add_argument('--end', dest='end_date',
                            help='Absolute end date (ISO format: 2025-12-10 or Unix timestamp)')
    search_parser.add_argument('--time-field', dest='time_field', choices=['created', 'updated'],
                            help="Which timestamp to filter on. Default: 'created' for absolute, 'updated' for relative")

    # Result selection
    search_parser.add_argument('--newest', dest='last_n', type=int, nargs='?', const=1,
                            help='Get the N most recent notes (default: 1 if no value given)')

    # Status filtering options
    search_parser.add_argument('--exported', action='store_true',
                            help='Only exported notes')
    search_parser.add_argument('--unexported', action='store_true',
                            help='Only unexported notes')
    search_parser.add_argument('--processed', action='store_true',
                            help='Only processed notes')
    search_parser.add_argument('--unprocessed', action='store_true',
                            help='Only unprocessed notes')
    search_parser.add_argument('--new', action='store_true',
                            help='New notes (unexported and unprocessed)')

    # Content control options
    search_parser.add_argument('--preview', type=int, dest='preview_length',
                            help='Show only first N characters of content')
    search_parser.add_argument('--titles-only', action='store_true',
                            help='Show only metadata, no content')

    # Search filters: user/system notes and attachments
    search_parser.add_argument('--user', dest='search_user', action='store_true', default=True,
                            help='Include user notes (default: true)')
    search_parser.add_argument('--no-user', dest='search_user', action='store_false',
                            help='Exclude user notes')
    search_parser.add_argument('--system', dest='search_system', action='store_true', default=False,
                            help='Include system notes/reports (default: false)')
    search_parser.add_argument('--no-system', dest='search_system', action='store_false',
                            help='Exclude system notes/reports')
    search_parser.add_argument('--attachments', dest='search_attachments', action='store_true', default=True,
                            help='Search attachment content too (default: true)')
    search_parser.add_argument('--no-attachments', dest='search_attachments', action='store_false',
                            help='Search notes only, exclude attachments')
    # Convenience shortcuts
    search_parser.add_argument('-uo', '--user-only', dest='user_only', action='store_true',
                            help='User notes + attachments only (no system)')
    search_parser.add_argument('-un', '--user-notes-only', dest='user_notes_only', action='store_true',
                            help='User notes only (no attachments, no system)')
    search_parser.add_argument('-so', '--system-only', dest='system_only', action='store_true',
                            help='System notes + attachments only (no user)')

    # Deleted filter
    search_parser.add_argument('--deleted', choices=['active', 'deleted', 'all'], default='active',
                            help='Filter by deleted status: active (default), deleted, or all')

    # Agent filter
    search_parser.add_argument('--agent', dest='agent_filter',
                            help='Filter by agent (shows notes owned by OR delegated to this agent)')

    # Delegation visibility
    search_parser.add_argument('--show-delegated', dest='show_delegated', action='store_true', default=True,
                            help='Include notes delegated to you (default: true)')
    search_parser.add_argument('--no-show-delegated', dest='show_delegated', action='store_false',
                            help='Exclude notes delegated to you, show only notes you own')

    # Search strategy options
    search_parser.add_argument('--strategy', default='hybrid',
                            choices=['hybrid', 'fts', 'ilike', 'similarity', 'vector', 'all'],
                            help='Search strategy: hybrid (default), fts, ilike, similarity, vector, all')
    search_parser.add_argument('--mode', default='websearch',
                            choices=['websearch', 'plain', 'phrase', 'raw'],
                            help='FTS query parsing: websearch (default), plain, phrase, raw')
    search_parser.add_argument('--similarity-threshold', type=float, default=0.3,
                            help='Minimum pg_trgm similarity score 0.0-1.0 (default: 0.3)')

    # Sort options
    search_parser.add_argument('--order-by', choices=['relevance', 'created', 'updated'], default='relevance',
                            help='Sort order (default: relevance)')
    search_parser.add_argument('--order-dir', choices=['desc', 'asc'], default='desc',
                            help='Sort direction (default: desc)')
    search_parser.add_argument('--offset', type=int, default=0,
                            help='Skip first N results (for pagination)')

    # Attachment type filters
    search_parser.add_argument('--file-type', dest='file_type',
                            help='Comma-separated attachment file types: audio,voice,image,document,video,archive')
    search_parser.add_argument('--mime-type', dest='mime_type',
                            help='Comma-separated MIME types: text/markdown,application/pdf')

    # Tag filters
    search_parser.add_argument('--tags', dest='tags',
                            help='Comma-separated tags to require (AND logic, e.g., --tags twitter,important)')
    search_parser.add_argument('--exclude-tags', dest='exclude_tags',
                            help='Comma-separated tags to exclude (e.g., --exclude-tags spam,archive)')

    # Read notes command
    read_parser = notetaker_subparsers.add_parser('read', help='Read notes (recent or by ID)')
    read_parser.add_argument('unique_ids', nargs='*', help='Unique IDs to fetch (if provided, other flags are ignored)')
    read_parser.add_argument('--limit', type=int, default=None, help='Maximum notes (default: 10 for llm/json, 100 for snippet/summary)')
    read_parser.add_argument('--format', choices=['json', 'llm', 'snippet', 'summary'], default=None,
                            help='Output format: llm (default), json, snippet (one-liner), summary (summary+len only)')
    read_parser.add_argument('--download', nargs='?', const='_notes', default=None,
                            help='Download notes (with attachments, excluding voice) to files. Optionally specify directory (default: _notes)')
    read_parser.add_argument('--clear', action='store_true',
                            help='Clear directory before downloading notes (requires --download)')
    read_parser.add_argument('--max-bytes', type=int, default=5000,
                            help='Maximum total response size in bytes (default: 5000, -1 = no limit). If exceeded, content is replaced with "(truncated)"')
    read_parser.add_argument('--max-bytes-llm', type=int, default=5000,
                            help='Maximum total size for all notes in LLM format (default: 5000, -1 = no limit). Only applies to --format llm')
    read_parser.add_argument('--processed-status', choices=['unprocessed', 'all', 'processed'], default='unprocessed',
                            help='Which notes to retrieve (default: unprocessed)')
    read_parser.add_argument('--all', action='store_true',
                            help='Get all notes (shortcut for --processed-status all)')
    read_parser.add_argument('--note-type', choices=['user', 'system', 'all'], default='user',
                            help='Filter by note type (default: user)')

    # Agent filter
    read_parser.add_argument('--agent', dest='agent_filter',
                            help='Filter by agent (shows notes owned by OR delegated to this agent)')

    # Delegation visibility
    read_parser.add_argument('--show-delegated', dest='show_delegated', action='store_true', default=True,
                            help='Include notes delegated to you (default: true)')
    read_parser.add_argument('--no-show-delegated', dest='show_delegated', action='store_false',
                            help='Exclude notes delegated to you, show only notes you own')

    # Event admin access
    read_parser.add_argument('--event', dest='event',
                            help='Event name to access participant notes (admin only). Empty results may indicate not authorized.')

    # Time window options (relative - days back)
    read_parser.add_argument('--from', dest='from_days', type=float,
                            help='Days back to start (e.g., --from 7)')
    read_parser.add_argument('--to', dest='to_days', type=float, default=0.0,
                            help='Days back to end (default: 0.0 = now)')
    read_parser.add_argument('--days', dest='days_back', type=float,
                            help='Last N days (shortcut for --from N --to 0)')
    read_parser.add_argument('--recent', action='store_true',
                            help='Last day (shortcut for --from 1)')
    read_parser.add_argument('--week', action='store_true',
                            help='Last week (shortcut for --from 7)')
    read_parser.add_argument('--forever', action='store_true',
                            help='All time (no time limit)')

    # Time window options (absolute - ISO dates)
    read_parser.add_argument('--start', dest='start_date',
                            help='Absolute start date (ISO format: 2025-12-01 or Unix timestamp)')
    read_parser.add_argument('--end', dest='end_date',
                            help='Absolute end date (ISO format: 2025-12-10 or Unix timestamp)')
    read_parser.add_argument('--time-field', dest='time_field', choices=['created', 'updated'],
                            help="Which timestamp to filter on. Default: 'created' for absolute, 'updated' for relative")

    # Result selection
    read_parser.add_argument('--newest', dest='last_n', type=int, nargs='?', const=1,
                            help='Get the N most recent notes (default: 1 if no value given)')

    # Context for ID lookups
    read_parser.add_argument('--context', type=str, default='0',
                            help='Context for ID lookups: 0=note only (default), -N=N before, +N=N after, N=symmetric')

    # Public URL generation
    read_parser.add_argument('--with-signed-urls', action='store_true',
                            help='Include public shareable URLs for notes')

    # Mark notes command
    mark_parser = notetaker_subparsers.add_parser('mark', help='Mark or unmark notes as processed, exported, and/or deleted')
    mark_parser.add_argument('unique_ids', nargs='+', help='Unique IDs of notes to mark (minimum 2 characters each)')
    mark_parser.add_argument('--processed', nargs='?', const='true', choices=['true', 'false'],
                            help='Mark/unmark as processed (default: true if flag present, false to unmark)')
    mark_parser.add_argument('--exported', nargs='?', const='true', choices=['true', 'false'],
                            help='Mark/unmark as exported (default: true if flag present, false to unmark)')
    mark_parser.add_argument('--deleted', nargs='?', const='true', choices=['true', 'false'],
                            help='Delete/undelete (default: true if flag present, false to undelete)')
    mark_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                            help='Output format (default: llm for concise output)')

    # Delete notes command (shortcut for mark --deleted true)
    delete_parser = notetaker_subparsers.add_parser('delete', help='Delete notes (soft delete)')
    delete_parser.add_argument('unique_ids', nargs='+', help='Unique IDs of notes to delete (minimum 2 characters each)')
    delete_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                              help='Output format (default: llm for concise output)')

    # Undelete notes command (shortcut for mark --deleted false)
    undelete_parser = notetaker_subparsers.add_parser('undelete', help='Undelete notes (restore soft-deleted)')
    undelete_parser.add_argument('unique_ids', nargs='+', help='Unique IDs of notes to undelete (minimum 2 characters each)')
    undelete_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                                help='Output format (default: llm for concise output)')

    # Update notes command (bulk update: tags, summary, metadata, delegates)
    update_parser = notetaker_subparsers.add_parser('update', help='Bulk update notes (tags, summary, metadata, delegates)')
    update_parser.add_argument('unique_ids', nargs='+', help='Unique IDs of notes (minimum 2 characters each)')
    # Tags
    update_parser.add_argument('--tags-set', dest='tags_set', type=str,
                               help='Replace all tags (comma-separated: a,b,c)')
    update_parser.add_argument('--tags-add', dest='tags_add', type=str,
                               help='Add tags (comma-separated: new_tag1,new_tag2)')
    update_parser.add_argument('--tags-remove', dest='tags_remove', type=str,
                               help='Remove tags (comma-separated: old_tag)')
    # Summary
    update_parser.add_argument('--summary', dest='summary', type=str,
                               help='Set summary text (use "" to clear)')
    # Metadata
    update_parser.add_argument('--metadata-set', dest='metadata_set', type=str,
                               help='Replace entire metadata (JSON string)')
    update_parser.add_argument('--metadata-merge', dest='metadata_merge', type=str,
                               help='Merge keys into metadata (JSON string)')
    update_parser.add_argument('--metadata-remove-keys', dest='metadata_remove_keys', type=str,
                               help='Remove keys from metadata (comma-separated)')
    # Delegates
    update_parser.add_argument('--delegates-add', dest='delegates_add', type=str,
                               help='Add delegate agents (comma-separated: coach,wellness)')
    update_parser.add_argument('--delegates-remove', dest='delegates_remove', type=str,
                               help='Remove delegate agents (comma-separated)')
    update_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                               help='Output format (default: llm for concise output)')

    # Delegate command (convenience alias for update --delegates-add/--delegates-remove)
    delegate_parser = notetaker_subparsers.add_parser('delegate', help='Manage note delegation (alias for update --delegates-*)')
    delegate_parser.add_argument('unique_ids', nargs='+', help='Unique IDs of notes (minimum 2 characters each)')
    delegate_parser.add_argument('--add', dest='delegates_add', type=str,
                                help='Add agents to delegates (comma-separated: coach,wellness,flat)')
    delegate_parser.add_argument('--remove', dest='delegates_remove', type=str,
                                help='Remove agents from delegates (comma-separated)')
    delegate_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                                help='Output format (default: llm for one-line output)')

    # Attachment command
    attachment_parser = notetaker_subparsers.add_parser('attachment', help='Get attachment from note')
    attachment_parser.add_argument('note_id', help='Unique ID of note (minimum 2 characters)')
    attachment_parser.add_argument('filename', nargs='?', default=None, help='Attachment filename (optional - uses first/only attachment if not specified)')
    attachment_parser.add_argument('--download', nargs='?', const='.', default=None,
                                  help='Download attachment to directory (default: current directory)')

    # Save report command
    savereport_parser = notetaker_subparsers.add_parser('savereport', help='Save a report markdown file')
    savereport_parser.add_argument('filename', nargs='?', default=None,
                                   help='Markdown file to save (reads from stdin if not provided)')
    savereport_parser.add_argument('--agent', dest='agent',
                                   help='Agent name (extracted from frontmatter if not provided)')
    savereport_parser.add_argument('--report-type', dest='report_type', default='user',
                                   help='Report type (default: user)')
    savereport_parser.add_argument('--date', dest='date',
                                   help='Report date ISO format (extracted from frontmatter if not provided)')
    savereport_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                                   help='Output format (default: llm for concise output)')
    savereport_parser.add_argument('--visibility', dest='visibility',
                                   help='Event visibility as EVENT:ROLES (e.g., hackathon:a,f). Roles: p=participant, a=admin, f=faculty')

    # Clear local command
    clear_parser = notetaker_subparsers.add_parser('clear', help='Clear local notes directory')
    clear_parser.add_argument('--directory', default='_notes',
                            help='Directory to clear (default: _notes)')

    # Reply to email (mailbox only)
    reply_parser = notetaker_subparsers.add_parser('reply', help='Reply to a received email (mailbox only)')
    reply_parser.add_argument('unique_id', help='Unique ID of the note to reply to')
    reply_parser.add_argument('text', help='Reply text')
    reply_parser.add_argument('--markdown', action='store_true',
                              help='Treat text as markdown (auto-generates HTML)')
    reply_parser.add_argument('--delay', type=int, default=5,
                              help='Delay in minutes before sending (default: 5). Use 0 for immediate.')
    reply_parser.add_argument('--bcc', nargs='+', help='BCC recipients')

    # Send new email (mailbox only)
    send_parser = notetaker_subparsers.add_parser('send', help='Send a new email (mailbox only)')
    send_parser.add_argument('to', help='Recipient email address')
    send_parser.add_argument('text', help='Email body text')
    send_parser.add_argument('--subject', default='', help='Email subject')
    send_parser.add_argument('--markdown', action='store_true',
                             help='Treat text as markdown (auto-generates HTML)')
    send_parser.add_argument('--delay', type=int, default=5,
                              help='Delay in minutes before sending (default: 5). Use 0 for immediate.')
    send_parser.add_argument('--bcc', nargs='+', help='BCC recipients')

    # Help command
    help_parser = notetaker_subparsers.add_parser('help', help='Show Notetaker help information')
    help_parser.add_argument('subcommand', nargs='?', help='Show help for specific Notetaker subcommand')



def handle_notetaker_command(args, client: AigonClient):
    """Handle Notetaker commands.

    Args:
        args: Parsed command-line arguments
        client: Authenticated Aigon client
    """
    if args.notetaker_command == 'search':
        # Validate flag combinations
        if args.clear and args.download is None:
            print("Error: --clear requires --download flag", file=sys.stderr)
            sys.exit(1)

        # Map convenient CLI options to parameters
        time_window_start = None
        time_window_end = getattr(args, 'to_days', 0.0)
        start_ts = None
        end_ts = None
        time_field = getattr(args, 'time_field', None)
        export_status = "all"
        processed_status = "all"
        max_content_length = -1

        # Process absolute time options (--start/--end override relative)
        start_date = getattr(args, 'start_date', None)
        end_date = getattr(args, 'end_date', None)

        if start_date:
            try:
                start_ts = parse_date_to_timestamp(start_date)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

        if end_date:
            try:
                end_ts = parse_date_to_timestamp(end_date)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

        # Process relative time options (only if no absolute times)
        if start_ts is None:
            if getattr(args, 'forever', False):
                time_window_start = None  # All time (explicit)
            elif getattr(args, 'recent', False):
                time_window_start = 1.0
            elif getattr(args, 'week', False):
                time_window_start = 7.0
            elif getattr(args, 'days_back', None) is not None:
                time_window_start = args.days_back
                time_window_end = 0.0
            elif getattr(args, 'from_days', None) is not None:
                time_window_start = args.from_days

        # Handle --newest N (get most recent N notes)
        reverse = False
        last_n = getattr(args, 'last_n', None)
        if last_n is not None:
            limit = last_n
            reverse = True
        else:
            # Apply format-specific default limit if not explicitly set
            if args.limit is None:
                if args.format in ['snippet', 'summary']:
                    limit = 100
                else:
                    limit = 10
            else:
                limit = args.limit

        # Process status options
        if getattr(args, 'new', False):
            export_status = "unexported"
            processed_status = "unprocessed"
        else:
            if getattr(args, 'exported', False):
                export_status = "exported"
            elif getattr(args, 'unexported', False):
                export_status = "unexported"

            if getattr(args, 'processed', False):
                processed_status = "processed"
            elif getattr(args, 'unprocessed', False):
                processed_status = "unprocessed"

        # Process content options
        if getattr(args, 'titles_only', False):
            max_content_length = 0
        elif getattr(args, 'preview_length', None) is not None:
            max_content_length = args.preview_length

        # Handle convenience shortcuts
        search_user = getattr(args, 'search_user', True)
        search_system = getattr(args, 'search_system', False)
        search_attachments = getattr(args, 'search_attachments', True)

        if getattr(args, 'user_notes_only', False):
            # --user-notes-only: user notes only, no attachments, no system
            search_user = True
            search_system = False
            search_attachments = False
        elif getattr(args, 'user_only', False):
            # --user-only: user notes + attachments, no system
            search_user = True
            search_system = False
            search_attachments = True
        elif getattr(args, 'system_only', False):
            # --system-only: system notes + attachments, no user
            search_user = False
            search_system = True
            search_attachments = True

        # Derive note_type from flags
        if search_user and search_system:
            note_type = 'all'
        elif search_system:
            note_type = 'system'
        else:
            note_type = 'user'

        # Derive scope from attachments flag
        scope = 'all' if search_attachments else 'notes'

        search_notes(client,
                    query=args.query,
                    content_type=args.content_type,
                    limit=limit,
                    output_format=args.format,
                    download_directory=args.download,
                    clear_directory=args.clear,
                    scope=scope,
                    time_window_start=time_window_start,
                    time_window_end=time_window_end,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    time_field=time_field,
                    export_status=export_status,
                    processed_status=processed_status,
                    deleted_status=getattr(args, 'deleted', 'active'),
                    max_content_length=max_content_length,
                    note_type=note_type,
                    reverse=reverse,
                    agent_filter=getattr(args, 'agent_filter', None),
                    show_delegated=getattr(args, 'show_delegated', True),
                    strategy=getattr(args, 'strategy', 'hybrid'),
                    mode=getattr(args, 'mode', 'websearch'),
                    similarity_threshold=getattr(args, 'similarity_threshold', 0.3),
                    order_by=getattr(args, 'order_by', 'relevance'),
                    order_dir=getattr(args, 'order_dir', 'desc'),
                    offset=getattr(args, 'offset', 0),
                    file_type=getattr(args, 'file_type', None),
                    mime_type=getattr(args, 'mime_type', None),
                    tags=getattr(args, 'tags', None),
                    exclude_tags=getattr(args, 'exclude_tags', None))
    elif args.notetaker_command == 'read':
        unique_ids = getattr(args, 'unique_ids', [])

        if unique_ids:
            # Get notes by ID - warn if filter flags provided (format/download/clear still work)
            has_filter_flags = (args.limit is not None or
                        getattr(args, 'max_bytes', 5000) != 5000 or
                        getattr(args, 'max_bytes_llm', 5000) != 5000 or
                        args.processed_status != 'unprocessed' or args.all)
            if has_filter_flags:
                print("Warning: filter flags ignored when fetching by ID", file=sys.stderr)

            # Parse context flag
            context_before, context_after = parse_context(getattr(args, 'context', '0'))

            get_notes_by_id(client, unique_ids=unique_ids, output_format=args.format,
                           download_directory=args.download, clear_directory=args.clear,
                           context_before=context_before, context_after=context_after,
                           with_signed_urls=getattr(args, 'with_signed_urls', False),
                           agent_filter=getattr(args, 'agent_filter', None))
        else:
            # Validate flag combinations
            if args.clear and args.download is None:
                print("Error: --clear requires --download flag", file=sys.stderr)
                sys.exit(1)

            # Handle --all flag as shortcut for --processed-status all
            processed_status = args.processed_status
            if args.all:
                processed_status = 'all'

            # Process time window options
            time_window_start = 1.0  # Default: last 1 day
            time_window_end = getattr(args, 'to_days', 0.0)
            start_ts = None
            end_ts = None
            time_field = getattr(args, 'time_field', None)

            # Process absolute time options (--start/--end override relative)
            start_date = getattr(args, 'start_date', None)
            end_date = getattr(args, 'end_date', None)

            if start_date:
                try:
                    start_ts = parse_date_to_timestamp(start_date)
                except ValueError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            if end_date:
                try:
                    end_ts = parse_date_to_timestamp(end_date)
                except ValueError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            # Process relative time options (only if no absolute times)
            if start_ts is None:
                if getattr(args, 'forever', False):
                    time_window_start = None  # All time
                elif getattr(args, 'recent', False):
                    time_window_start = 1.0
                elif getattr(args, 'week', False):
                    time_window_start = 7.0
                elif getattr(args, 'days_back', None) is not None:
                    time_window_start = args.days_back
                    time_window_end = 0.0
                elif getattr(args, 'from_days', None) is not None:
                    time_window_start = args.from_days

            # Handle --newest N (get most recent N notes)
            reverse = False
            last_n = getattr(args, 'last_n', None)
            if last_n is not None:
                limit = last_n
                reverse = True
            else:
                # Apply format-specific default limit if not explicitly set
                if args.limit is None:
                    if args.format in ['snippet', 'summary']:
                        limit = 100
                    else:
                        limit = 10
                else:
                    limit = args.limit

            recent_notes(client, limit=limit, output_format=args.format,
                        download_directory=args.download, clear_directory=args.clear,
                        max_bytes=getattr(args, 'max_bytes', 5000),
                        max_bytes_llm=getattr(args, 'max_bytes_llm', 5000),
                        processed_status=processed_status,
                        note_type=getattr(args, 'note_type', 'user'),
                        time_window_start=time_window_start,
                        time_window_end=time_window_end,
                        start_ts=start_ts,
                        end_ts=end_ts,
                        time_field=time_field,
                        reverse=reverse,
                        agent_filter=getattr(args, 'agent_filter', None),
                        show_delegated=getattr(args, 'show_delegated', True),
                        event=getattr(args, 'event', None))
    elif args.notetaker_command == 'mark':
        # Convert string args to bool or None
        processed = None
        exported = None
        deleted = None
        if hasattr(args, 'processed') and args.processed:
            processed = args.processed == 'true'
        if hasattr(args, 'exported') and args.exported:
            exported = args.exported == 'true'
        if hasattr(args, 'deleted') and args.deleted:
            deleted = args.deleted == 'true'

        # Validate at least one flag is specified
        if processed is None and exported is None and deleted is None:
            print("Error: At least one of --processed, --exported, or --deleted must be specified", file=sys.stderr)
            sys.exit(1)

        mark_notes(client, unique_ids=args.unique_ids, processed=processed,
                   exported=exported, deleted=deleted, output_format=args.format)
    elif args.notetaker_command == 'delete':
        # Shortcut for mark --deleted true
        mark_notes(client, unique_ids=args.unique_ids, deleted=True, output_format=args.format)
    elif args.notetaker_command == 'undelete':
        # Shortcut for mark --deleted false
        mark_notes(client, unique_ids=args.unique_ids, deleted=False, output_format=args.format)
    elif args.notetaker_command == 'update':
        # Handle update command (full bulk update)
        update_notes(client, unique_ids=args.unique_ids,
                    tags_set=getattr(args, 'tags_set', None),
                    tags_add=getattr(args, 'tags_add', None),
                    tags_remove=getattr(args, 'tags_remove', None),
                    summary=getattr(args, 'summary', None),
                    metadata_set=getattr(args, 'metadata_set', None),
                    metadata_merge=getattr(args, 'metadata_merge', None),
                    metadata_remove_keys=getattr(args, 'metadata_remove_keys', None),
                    delegates_add=getattr(args, 'delegates_add', None),
                    delegates_remove=getattr(args, 'delegates_remove', None),
                    output_format=args.format)
    elif args.notetaker_command == 'delegate':
        # Delegate is a convenience alias for update with delegates only
        delegates_add = getattr(args, 'delegates_add', None)
        delegates_remove = getattr(args, 'delegates_remove', None)
        if delegates_add is None and delegates_remove is None:
            # READ mode - just show delegates
            notes = client.get_notes_by_ids(args.unique_ids, context_before=0, context_after=0, with_attachments=True)
            if not notes:
                print("No notes found")
            elif args.format == "json":
                sanitized = [_sanitize_note_for_output(note) for note in notes]
                print(json.dumps(sanitized, indent=2))
            else:
                for note in notes:
                    uid = note.get('unique_id_short', note.get('unique_id', 'unknown'))
                    delegates = note.get('delegates', [])
                    print(f"unique_id: {uid}  delegates: {json.dumps(delegates)}")
        else:
            update_notes(client, unique_ids=args.unique_ids,
                        delegates_add=delegates_add,
                        delegates_remove=delegates_remove,
                        output_format=args.format)
    elif args.notetaker_command == 'attachment':
        # Handle attachment command
        get_attachment(client, note_id=args.note_id, filename=args.filename,
                      download_directory=args.download)
    elif args.notetaker_command == 'savereport':
        # Handle savereport command - read from file or stdin
        filename = getattr(args, 'filename', None)
        if filename:
            # Read from file
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
            except FileNotFoundError:
                print(f"Error: File not found: {filename}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Read from stdin
            if sys.stdin.isatty():
                print("Error: No filename provided and stdin is a terminal.", file=sys.stderr)
                print("Provide a filename or pipe content: cat report.md | aigon notetaker savereport", file=sys.stderr)
                sys.exit(1)
            content = sys.stdin.read()

        if not content.strip():
            print("Error: Empty content", file=sys.stderr)
            sys.exit(1)

        # Get visibility settings
        event = getattr(args, 'event', None)
        visible_to_participants = getattr(args, 'participants', None)

        save_report(client, content=content,
                   agent=getattr(args, 'agent', None),
                   report_type=getattr(args, 'report_type', 'user'),
                   date=getattr(args, 'date', None),
                   event=event,
                   visible_to_participants=visible_to_participants,
                   output_format=args.format)
    elif args.notetaker_command == 'reply':
        mailbox_reply(client, unique_id=args.unique_id, text=args.text,
                      as_markdown=getattr(args, 'markdown', False),
                      delay=getattr(args, 'delay', 5),
                      bcc=getattr(args, 'bcc', None))
    elif args.notetaker_command == 'send':
        mailbox_send(client, to=args.to, subject=getattr(args, 'subject', ''),
                     text=args.text, as_markdown=getattr(args, 'markdown', False),
                     delay=getattr(args, 'delay', 5),
                     bcc=getattr(args, 'bcc', None))
    elif args.notetaker_command == 'clear':
        clear_local(args.directory)
    elif args.notetaker_command == 'help':
        if hasattr(args, 'subcommand') and args.subcommand:
            # Show help for specific notetaker subcommand
            if args.subcommand == 'search':
                print("Search Command Help - Search through notetaker notes with advanced filtering\n")
                print("Usage: aigon notetaker search <query> [OPTIONS]")
                print("\nDefault filters (without flags):")
                print("  • All time (no time limit)")
                print("  • All notes (processed and unprocessed)")
                print("  • All notes (exported and unexported)")
                print("\nBasic Options:")
                print("  query                  Search query string")
                print("  --type {text,audio,image}  Filter by content type")
                print("  --limit INTEGER        Maximum results (default: 10)")
                print("  --format {llm,json,snippet,summary}  Output format (default: llm). summary = summary+len only")
                print("  --download [DIRECTORY]    Download notes to files. Optional directory (default: _notes)")
                print("  --clear                   Clear directory before downloading (requires --download)")
                print("\nTime Filtering:")
                print("  --from DAYS           Days back to start search (e.g., --from 7)")
                print("  --to DAYS             Days back to end search (default: 0.0 = now)")
                print("  --days DAYS           Search last N days (shortcut for --from N --to 0)")
                print("  --recent              Search last day (shortcut for --from 1)")
                print("  --week                Search last week (shortcut for --from 7)")
                print("\nResult Selection:")
                print("  --newest [N]          Get the N most recent notes (default: 1)")
                print("\nStatus Filtering:")
                print("  --exported            Only exported notes")
                print("  --unexported          Only unexported notes")
                print("  --processed           Only processed notes")
                print("  --unprocessed         Only unprocessed notes")
                print("  --new                 New notes (unexported and unprocessed)")
                print("\nContent Control:")
                print("  --preview N           Show only first N characters of content")
                print("  --titles-only         Show only metadata, no content")
                print("\nExamples:")
                print("  # Search (default LLM format)")
                print("  aigon notetaker search 'meeting'")
                print("  # Search with JSON output")
                print("  aigon notetaker search 'meeting' --format json")
                print("  # Search last 3 days for unexported notes")
                print("  aigon notetaker search 'meeting' --days 3 --unexported")
                print("  # Get the 5 most recent notes")
                print("  aigon notetaker search '' --newest 5")
                print("  # Get the most recent note (--newest defaults to 1)")
                print("  aigon notetaker search '' --newest")
                print("  # Search and download to files")
                print("  aigon notetaker search 'todo' --new --download")
                print("  # Search and download to custom directory")
                print("  aigon notetaker search '' --recent --download my_notes --clear")
            elif args.subcommand == 'read':
                print("Read Notes Command Help - Get recent unprocessed notes from the last day\n")
                print("Usage: aigon notetaker read [OPTIONS]")
                print("\nDefault filters:")
                print("  • Last 1 day only")
                print("  • Unprocessed notes only")
                print("  • All export statuses")
                print("\nOptions:")
                print("  --limit INTEGER        Maximum notes (default: 10)")
                print("  --newest [N]           Get the N most recent notes (default: 1)")
                print("  --format {llm,json,snippet,summary}  Output format (default: llm). summary = summary+len only")
                print("  --download [DIRECTORY] Download notes to files (default: _notes)")
                print("  --clear                Clear directory before downloading")
                print("\nTime Filtering:")
                print("  --days DAYS            Last N days (shortcut for --from N)")
                print("  --recent               Last day (shortcut for --from 1)")
                print("  --week                 Last week (shortcut for --from 7)")
                print("  --forever              All time (no time limit)")
                print("\nExamples:")
                print("  aigon notetaker read --limit 20              # Get oldest 20 notes")
                print("  aigon notetaker read --newest                # Get the most recent note")
                print("  aigon notetaker read --newest 5              # Get the 5 most recent notes")
                print("  aigon notetaker read --download              # Download to _notes/")
                print("  aigon notetaker read --download exports      # Download to exports/")
            else:
                print(f"Unknown Notetaker subcommand: {args.subcommand}")
                print("Available subcommands: search, read, clear")
        else:
            # Show general notetaker help
            print("Notetaker Help - Search and retrieve notes\n")
            print("Available Notetaker commands:")
            print("  search     - Search through notes with advanced filtering")
            print("  read       - Get recent notes or specific notes by ID")
            print("  update     - Bulk update notes (tags, summary, metadata, delegates)")
            print("  mark       - Mark notes as processed/exported")
            print("  delegate   - Manage note delegation (alias for update --delegates-*)")
            print("  delete     - Delete notes (soft delete)")
            print("  undelete   - Undelete notes (restore soft-deleted)")
            print("  attachment - Get attachment content from note")
            print("  savereport - Save a report markdown file")
            print("  clear      - Clear local notes directory")
            print("  help       - Show Notetaker help information")
            print("\nFor command-specific help:")
            print("  aigon notetaker help search    - Show search command help")
            print("  aigon notetaker help read      - Show read command help")
            print("  aigon notetaker <command> --help  - Show detailed help for command")
            print("\nFor LLM-friendly comprehensive help:")
            print("  aigon llm help                 - Show full command reference")
    else:
        print(f"Unknown Notetaker command: {args.notetaker_command}", file=sys.stderr)
        sys.exit(1)
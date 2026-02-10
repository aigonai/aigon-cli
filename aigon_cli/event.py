"""Event commands for Aigon CLI.

This module provides command-line interface functions for event admin operations
including reading participant notes and viewing submission timelines.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import json
import os
import shutil
import sys
import time
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import re

from .client import AigonClient
from .config import get_config_value, set_config_value, load_config, save_config, get_config_path
from .tz import parse_time, parse_time_range


# ===== Configuration Helpers =====

def get_event_name() -> Optional[str]:
    """Get event name from config."""
    return get_config_value('event', 'name')


def get_event_token() -> Optional[str]:
    """Get event API token from config.

    Priority:
    1. [event] token - event-specific token
    2. [api] token - fallback to general token

    Warns if both are present in local config (confusing setup).

    Returns:
        API token string or None
    """
    event_token = get_config_value('event', 'token')
    api_token = get_config_value('api', 'token')

    if event_token and api_token:
        print("Warning: Local config has both [event] token and [api] token", file=sys.stderr)
        print("         Using [event] token. Consider removing [api] token from local config.", file=sys.stderr)

    return event_token or api_token


def get_test_users() -> List[int]:
    """Get test user IDs from config."""
    value = get_config_value('event', 'test_users')
    if not value:
        return []
    return [int(u.strip()) for u in value.split(',') if u.strip()]


def get_admin_users() -> List[int]:
    """Get admin user IDs from config."""
    value = get_config_value('event', 'admin_users')
    if not value:
        return []
    return [int(u.strip()) for u in value.split(',') if u.strip()]


def parse_user_list(value: Optional[str]) -> List[int]:
    """Parse comma-separated user IDs string to list of ints."""
    if not value:
        return []
    return [int(u.strip()) for u in value.split(',') if u.strip()]


def get_periods() -> Dict[str, tuple]:
    """Get configured time periods from config.

    Returns:
        Dict mapping period name to (start_time, end_time) tuples
        Times are in HH:MM format
    """
    config = load_config()
    periods = {}
    if not config.has_section('event'):
        return periods

    for option in config.options('event'):
        if option.startswith('period.'):
            period_name = option[7:]  # Remove 'period.' prefix
            value = config.get('event', option)
            # Parse "HH:MM-HH:MM" format
            if '-' in value:
                start_time, end_time = value.split('-', 1)
                periods[period_name] = (start_time.strip(), end_time.strip())

    return periods




# ===== Note Formatting =====

def _format_note_llm(note: dict) -> str:
    """Format a single note in LLM-friendly format for event mode.

    Always shows user_id_pk_int since this is event admin view.
    """
    unique_id = note.get('unique_id', 'unknown')
    short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
    content_type = note.get('content_type', 'text')
    content = note.get('content', '')
    user_id_pk_int = note.get('user_id_pk_int', 'unknown')

    # Format created_at
    created_at_ts = note.get('created_at')
    if created_at_ts:
        try:
            dt = datetime.fromtimestamp(int(created_at_ts), tz=timezone.utc)
            created_at = dt.strftime('%a %Y-%m-%d %H:%M:%S UTC')
        except (ValueError, TypeError):
            created_at = 'unknown'
    else:
        created_at = 'unknown'

    lines = [
        "--- BEGIN NOTE ---",
        f"unique_id: {short_id} [{unique_id}]",
        f"user_id_pk_int: {user_id_pk_int}",
        f"created_at: {created_at}",
        f"content_type: {content_type}",
        "content: ---",
        content,
        "---",
        "--- END NOTE ---"
    ]

    return '\n'.join(lines)


def _format_note_snippet(note: dict, max_content_chars: int = 80) -> str:
    """Format a single note as ultra-concise one-liner.

    Format: user_id | short_id | time | content_preview
    """
    unique_id = note.get('unique_id', 'unknown')
    short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
    user_id_pk_int = note.get('user_id_pk_int', '?')

    # Time (compact format)
    created_at = note.get('created_at')
    if created_at:
        try:
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
            time_str = dt.strftime('%H:%M')
        except (ValueError, TypeError):
            time_str = '??:??'
    else:
        time_str = '??:??'

    # Content preview
    content = note.get('content', '')
    content_preview = content.replace('\n', ' ').replace('\r', '')[:max_content_chars]
    if len(content) > max_content_chars:
        content_preview += '...'

    return f"u{user_id_pk_int} | {short_id} | {time_str} | {content_preview}"


def _sanitize_note_for_output(note: dict) -> dict:
    """Remove internal fields from note before outputting.

    Note: user_id_pk_int is kept for event mode since admins need to identify note owners.
    """
    internal_fields = {'id', 'agent', 'att_id', 'att_unique_id', 'att_filename',
                       'att_original_filename', 'att_file_type', 'att_mime_type',
                       'att_content_size'}
    return {k: v for k, v in note.items() if k not in internal_fields}


def _clear_directory(directory: str) -> None:
    """Clear all files in a directory.

    Args:
        directory: Directory path to clear
    """
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        print(f"Cleared {directory}/")


def _save_event_notes_to_files(notes: List[dict], directory: str,
                                clear_directory: bool = False,
                                with_attachments: bool = True,
                                client: Optional[AigonClient] = None) -> List[str]:
    """Save event notes as individual markdown files with optional attachments.

    Args:
        notes: List of note dictionaries
        directory: Directory to save files to
        clear_directory: Whether to clear directory before saving
        with_attachments: Whether to download attachments (default: True)
        client: Aigon client (required for attachment downloads)

    Returns:
        List of saved file paths
    """
    # Clear directory before saving notes if requested
    if clear_directory:
        _clear_directory(directory)

    # Create directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)

    if not notes:
        print("No notes found to save")
        return []

    saved_files = []
    attachment_count = 0

    for note in notes:
        # Generate filename from created_at timestamp
        unique_id = note.get('unique_id', note.get('id', 'unknown'))
        short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
        content_type = note.get('content_type', 'text')
        created_at = note.get('created_at')
        user_id = note.get('user_id_pk_int', 'unknown')

        # Convert created_at to proper datetime format for filename
        try:
            if created_at:
                dt_utc = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
                date_prefix = dt_utc.strftime("%Y%m%d_%H%MZ")
            else:
                date_prefix = "unknown"
        except (ValueError, TypeError):
            date_prefix = "unknown"

        # Create filename: date_user_shortid_type.md
        filename = f"{date_prefix}_u{user_id}_{short_id}_{content_type}.md"
        filepath = os.path.join(directory, filename)

        # Prepare content
        content = note.get('content', note.get('processed_content', note.get('original_content', '')))

        # Create metadata header with YAML frontmatter
        metadata = "---\n"
        metadata += f"unique_id: {unique_id}\n"
        metadata += f"user_id: {user_id}\n"
        metadata += f"type: {content_type}\n"

        # Add time information
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
            metadata += f"created_at: unknown\n"

        # Add processed timestamp
        processed_at = note.get('processed_at')
        if processed_at:
            try:
                processed_ts = int(processed_at)
                processed_dt = datetime.fromtimestamp(processed_ts, tz=timezone.utc)
                metadata += f"processed_at: \"{processed_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}\"\n"
            except (ValueError, TypeError):
                metadata += f"processed_at: {processed_at}\n"

        # Add attachment info if present
        attachments = note.get('attachments', [])
        if attachments:
            att_names = [att.get('filename', 'unknown') for att in attachments]
            metadata += f"attachments: {att_names}\n"

        metadata += "---\n\n"
        metadata += f"# Note {short_id}\n\n"

        full_content = metadata + content

        # Write note file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        saved_files.append(filepath)

        # Download attachments if requested (skip voice recordings)
        if with_attachments and attachments and client and content_type != 'voice':
            for att in attachments:
                att_unique_id = att.get('unique_id')
                att_filename = att.get('filename')
                if not att_unique_id or not att_filename:
                    continue
                try:
                    # Get attachment content by unique_id
                    att_content, mime_type, _ = client.get_attachment_by_unique_id(att_unique_id)

                    # Name attachment with note prefix so it sorts with the note
                    # Format: date_user_shortid_attachmentfilename
                    att_save_name = f"{date_prefix}_u{user_id}_{short_id}_{att_filename}"
                    att_filepath = os.path.join(directory, att_save_name)

                    with open(att_filepath, 'wb') as f:
                        f.write(att_content)
                    saved_files.append(att_filepath)
                    attachment_count += 1
                except Exception as e:
                    print(f"Warning: Failed to download attachment {att_filename} for {short_id}: {e}", file=sys.stderr)

    # Print summary
    note_count = len(notes)
    if attachment_count > 0:
        print(f"Saved {note_count} notes and {attachment_count} attachments to {directory}/:")
    else:
        print(f"Saved {note_count} notes to {directory}/:")

    for filepath in saved_files:
        print(f"  - {os.path.basename(filepath)}")

    return saved_files


# ===== Commands =====

def event_read(client: AigonClient, event_name: str,
               limit: int = 50,
               output_format: str = 'llm',
               time_range: Optional[str] = None,
               start_time: Optional[str] = None,
               end_time: Optional[str] = None,
               period: Optional[str] = None,
               date: Optional[str] = None,
               test_users: Optional[List[int]] = None,
               newest: bool = False,
               processed_status: str = 'unprocessed',
               test_only: bool = False,
               filter_users: Optional[List[int]] = None,
               download_directory: Optional[str] = None,
               clear_directory: bool = False,
               with_attachments: bool = True) -> None:
    """Read event participant notes.

    Args:
        client: Authenticated Aigon client
        event_name: Event name for filtering
        limit: Maximum number of notes
        output_format: Output format (llm, json, snippet)
        time_range: Time range filter (HH:MM-HH:MM)
        start_time: Start time filter (HH:MM)
        end_time: End time filter (HH:MM)
        period: Period name from config
        date: Date filter (ISO format, default: today)
        test_users: User IDs to filter out (or include if test_only=True)
        newest: If True, get most recent (reversed order)
        processed_status: Filter by processed status (unprocessed, processed, all)
        test_only: If True, only show test user data instead of filtering them out
        filter_users: If provided, only include these user IDs (client-side filter)
        download_directory: Directory to download notes to (None = stdout mode)
        clear_directory: Whether to clear directory before downloading
        with_attachments: Whether to download attachments (default: True)
    """
    try:
        # Determine base date
        if date:
            base_date = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        else:
            base_date = datetime.now(timezone.utc)

        # Calculate time range
        start_ts = None
        end_ts = None

        if period:
            periods = get_periods()
            if period not in periods:
                print(f"Error: Period '{period}' not found in config", file=sys.stderr)
                print(f"Available periods: {', '.join(periods.keys()) or '(none)'}", file=sys.stderr)
                sys.exit(1)
            start_time, end_time = periods[period]

        if time_range:
            start_ts, end_ts = parse_time_range(time_range, base_date)
        elif start_time or end_time:
            if start_time:
                start_dt = parse_time(start_time, base_date)
                start_ts = int(start_dt.timestamp())
            if end_time:
                end_dt = parse_time(end_time, base_date)
                end_ts = int(end_dt.timestamp())

        # Get test users from config if not provided
        if test_users is None:
            test_users = get_test_users()

        # Call API with event parameter
        result = client.get_recent_notes(
            limit=limit,
            max_bytes=-1,  # Never truncate
            processed_status=processed_status,
            note_type='user',
            time_window_start=None,  # Use absolute timestamps
            start_ts=start_ts,
            end_ts=end_ts,
            reverse=newest,
            event=event_name
        )

        # Filter test users
        if test_users:
            if test_only:
                result = [n for n in result if n.get('user_id_pk_int') in test_users]
            else:
                result = [n for n in result if n.get('user_id_pk_int') not in test_users]

        # Filter to specific users if requested
        if filter_users:
            result = [n for n in result if n.get('user_id_pk_int') in filter_users]

        # Output - download mode or stdout mode
        if download_directory is not None:
            # Download mode: save to files
            _save_event_notes_to_files(result, download_directory, clear_directory,
                                        with_attachments=with_attachments, client=client)
        elif output_format == 'json':
            sanitized = [_sanitize_note_for_output(note) for note in result]
            print(json.dumps(sanitized, indent=2))
        elif output_format == 'snippet':
            if not result:
                print("No notes found")
                return
            for note in result:
                print(_format_note_snippet(note))
        else:  # llm format
            if not result:
                print("No notes found")
                return
            for note in result:
                print(_format_note_llm(note))
                print()

    except Exception as e:
        print(f"Error reading event notes: {e}", file=sys.stderr)
        sys.exit(1)


def event_timeline(client: AigonClient, event_name: str,
                   date: Optional[str] = None,
                   from_time: Optional[str] = None,
                   to_time: Optional[str] = None,
                   test_users: Optional[List[int]] = None,
                   format_style: int = 1,
                   bucket_minutes: int = 5,
                   processed_status: str = 'all',
                   test_only: bool = False,
                   filter_users: Optional[List[int]] = None) -> None:
    """Show submission timeline for event.

    Displays when participants submitted notes, useful for determining cutoffs.

    Args:
        format_style: 1 = detailed with user IDs, 2 = bar chart, 3 = note IDs
        bucket_minutes: Minutes per bucket for format 2
        from_time: Start time filter HH:MM
        to_time: End time filter HH:MM
        processed_status: Filter by processed status (all, processed, unprocessed)
    """
    try:
        # Determine date range
        if date:
            base_date = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        else:
            base_date = datetime.now(timezone.utc)

        # Start of day to end of day (or filtered by from/to)
        start_of_day = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = base_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Apply from_time filter
        if from_time:
            from_dt = parse_time(from_time, base_date)
            start_of_day = from_dt

        # Apply to_time filter
        if to_time:
            to_dt = parse_time(to_time, base_date)
            end_of_day = to_dt

        start_ts = int(start_of_day.timestamp())
        end_ts = int(end_of_day.timestamp())

        # Get test users from config if not provided
        if test_users is None:
            test_users = get_test_users()

        # Get all notes for the time range
        result = client.get_recent_notes(
            limit=1000,  # High limit for timeline
            max_bytes=-1,
            processed_status=processed_status,
            note_type='user',
            time_window_start=None,
            start_ts=start_ts,
            end_ts=end_ts,
            reverse=False,  # Chronological order
            event=event_name
        )

        # Filter test users
        if test_users:
            if test_only:
                result = [n for n in result if n.get('user_id_pk_int') in test_users]
            else:
                result = [n for n in result if n.get('user_id_pk_int') not in test_users]

        # Filter to specific users if requested
        if filter_users:
            result = [n for n in result if n.get('user_id_pk_int') in filter_users]

        if not result:
            print("No submissions found for this date")
            return

        if format_style == 2:
            # Bar chart format with equal-width buckets
            _timeline_format_bar(result, base_date, event_name, bucket_minutes)
        elif format_style == 3:
            # Note IDs format
            _timeline_format_note_ids(result, base_date, event_name)
        else:
            # Original detailed format with user IDs
            _timeline_format_detailed(result, base_date, event_name)

    except Exception as e:
        print(f"Error getting timeline: {e}", file=sys.stderr)
        sys.exit(1)


def _timeline_format_detailed(result: List[dict], base_date: datetime, event_name: str) -> None:
    """Format 1: Detailed timeline with user IDs."""
    print()
    # Group by time (minute buckets)
    buckets = {}
    min_time = None
    max_time = None

    for note in result:
        created_at = note.get('created_at')
        if created_at:
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
            bucket_key = dt.strftime('%H:%M')
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(note.get('user_id_pk_int'))

            if min_time is None or bucket_key < min_time:
                min_time = bucket_key
            if max_time is None or bucket_key > max_time:
                max_time = bucket_key

    if not buckets:
        print("No submissions found")
        return

    # Generate all minute buckets between min and max
    all_buckets = []
    current = min_time
    while current <= max_time:
        all_buckets.append(current)
        # Increment by 1 minute
        h, m = int(current[:2]), int(current[3:])
        m += 1
        if m >= 60:
            m = 0
            h += 1
        current = f"{h:02d}:{m:02d}"

    # Find max user ID length for padding
    all_user_ids = set()
    for users in buckets.values():
        all_user_ids.update(users)
    max_uid_len = max(len(str(u)) for u in all_user_ids) if all_user_ids else 1

    # Find max count for column width
    max_count = max(len(v) for v in buckets.values()) if buckets else 0
    count_width = max(len(str(max_count)), 2)

    # Display timeline
    print(f"Timeline for {base_date.strftime('%Y-%m-%d')}")
    print(f"Event: {event_name}")
    print("-" * 60)

    for time_key in all_buckets:
        users = buckets.get(time_key, [])
        count = len(users)
        # Pad user IDs to same length
        user_strs = [f"u{u:<{max_uid_len}}" for u in sorted(set(users))]
        user_str = '[' + ','.join(user_strs) + ']' if user_strs else '[]'
        print(f"{time_key} | {count:>{count_width}} | {user_str}")

    print("-" * 60)
    print(f"Total: {len(result)} notes from {len(all_user_ids)} users")
    print()


def _timeline_format_note_ids(result: List[dict], base_date: datetime, event_name: str) -> None:
    """Format 3: Timeline with note IDs."""
    print()
    # Group by time (minute buckets)
    buckets = {}
    min_time = None
    max_time = None

    for note in result:
        created_at = note.get('created_at')
        if created_at:
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc)
            bucket_key = dt.strftime('%H:%M')
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            unique_id = note.get('unique_id', 'unknown')
            short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
            buckets[bucket_key].append(short_id)

            if min_time is None or bucket_key < min_time:
                min_time = bucket_key
            if max_time is None or bucket_key > max_time:
                max_time = bucket_key

    if not buckets:
        print("No submissions found")
        return

    # Generate all minute buckets between min and max
    all_buckets = []
    current = min_time
    while current <= max_time:
        all_buckets.append(current)
        # Increment by 1 minute
        h, m = int(current[:2]), int(current[3:])
        m += 1
        if m >= 60:
            m = 0
            h += 1
        current = f"{h:02d}:{m:02d}"

    # Find max count for column width
    max_count = max(len(v) for v in buckets.values()) if buckets else 0
    count_width = max(len(str(max_count)), 2)

    # Display timeline
    print(f"Timeline for {base_date.strftime('%Y-%m-%d')}")
    print(f"Event: {event_name}")
    print("-" * 60)

    for time_key in all_buckets:
        note_ids = buckets.get(time_key, [])
        count = len(note_ids)
        ids_str = '[' + ','.join(note_ids) + ']' if note_ids else '[]'
        print(f"{time_key} | {count:>{count_width}} | {ids_str}")

    print("-" * 60)
    print(f"Total: {len(result)} notes")
    print()


def _timeline_format_bar(result: List[dict], base_date: datetime, event_name: str,
                         bucket_minutes: Optional[int] = None) -> None:
    """Format 2: Bar chart with equal-width time buckets.

    Auto-selects bucket size to have 10-30 buckets if not specified.
    Valid bucket sizes: 1, 2, 5, 10, 15, 20, 30, 60 minutes.
    """
    print()
    # Get timestamps and find range
    timestamps = []
    for note in result:
        created_at = note.get('created_at')
        if created_at:
            timestamps.append(int(created_at))

    if not timestamps:
        print("No submissions found")
        return

    min_ts = min(timestamps)
    max_ts = max(timestamps)
    range_minutes = (max_ts - min_ts) / 60

    # Auto-select bucket size if not specified
    valid_buckets = [1, 2, 5, 10, 15, 20, 30, 60]
    if bucket_minutes is None:
        # Find bucket size that gives 10-30 buckets
        for size in valid_buckets:
            num_buckets = range_minutes / size
            if 10 <= num_buckets <= 30:
                bucket_minutes = size
                break
        # If range is too small, use smallest bucket
        if bucket_minutes is None and range_minutes < 10:
            bucket_minutes = 1
        # If range is too large, use largest bucket
        if bucket_minutes is None:
            bucket_minutes = 60

    # Round to bucket boundaries
    bucket_seconds = bucket_minutes * 60
    min_bucket = (min_ts // bucket_seconds) * bucket_seconds
    max_bucket = ((max_ts // bucket_seconds) + 1) * bucket_seconds

    # Count notes per bucket
    buckets = {}
    for ts in range(min_bucket, max_bucket + 1, bucket_seconds):
        buckets[ts] = 0

    for ts in timestamps:
        bucket_ts = (ts // bucket_seconds) * bucket_seconds
        buckets[bucket_ts] = buckets.get(bucket_ts, 0) + 1

    # Trim empty buckets from start and end
    sorted_keys = sorted(buckets.keys())
    while sorted_keys and buckets[sorted_keys[0]] == 0:
        del buckets[sorted_keys[0]]
        sorted_keys = sorted_keys[1:]
    while sorted_keys and buckets[sorted_keys[-1]] == 0:
        del buckets[sorted_keys[-1]]
        sorted_keys = sorted_keys[:-1]

    if not buckets:
        print("No submissions found")
        return

    # Find max count for normalization
    max_count = max(buckets.values()) if buckets.values() else 1
    bar_width = 60

    # Display header
    print(f"Timeline for {base_date.strftime('%Y-%m-%d')} ({bucket_minutes}min buckets)")
    print(f"Event: {event_name}")
    print("-" * (8 + 6 + bar_width + 4))

    # Display bars
    for bucket_ts in sorted(buckets.keys()):
        count = buckets[bucket_ts]
        dt = datetime.fromtimestamp(bucket_ts, tz=timezone.utc)
        time_str = dt.strftime('%H:%M')

        # Calculate bar length (normalized to bar_width)
        if max_count > 0:
            bar_len = int((count / max_count) * bar_width)
        else:
            bar_len = 0

        bar = '█' * bar_len

        # Fixed-width formatting: time (5) + space + count (4) + space + bar
        print(f"{time_str} | {count:4d} | {bar}")

    print("-" * (8 + 6 + bar_width + 4))
    print(f"Total: {len(result)} notes | Max: {max_count} per {bucket_minutes}min")
    print()


def event_stats(client: AigonClient, event_name: str,
                date: Optional[str] = None,
                test_users: Optional[List[int]] = None,
                format_style: int = 1,
                test_only: bool = False,
                filter_users: Optional[List[int]] = None) -> None:
    """Show user statistics for event.

    Args:
        format_style: 1 = with content types, 2 = with note IDs
        test_only: If True, only show test user data instead of filtering them out
        filter_users: If provided, only include these user IDs (client-side filter)
    """
    try:
        # Determine date range (full day or all time if no date)
        start_ts = None
        end_ts = None

        if date:
            base_date = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
            start_of_day = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = base_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            start_ts = int(start_of_day.timestamp())
            end_ts = int(end_of_day.timestamp())

        # Get test users from config if not provided
        if test_users is None:
            test_users = get_test_users()

        # Get all notes
        result = client.get_recent_notes(
            limit=10000,  # High limit for stats
            max_bytes=-1,
            processed_status='all',
            note_type='user',
            time_window_start=None,
            start_ts=start_ts,
            end_ts=end_ts,
            reverse=False,
            event=event_name
        )

        # Filter test users
        if test_users:
            if test_only:
                result = [n for n in result if n.get('user_id_pk_int') in test_users]
            else:
                result = [n for n in result if n.get('user_id_pk_int') not in test_users]

        # Filter to specific users if requested
        if filter_users:
            result = [n for n in result if n.get('user_id_pk_int') in filter_users]

        if not result:
            print("No notes found")
            return

        # Calculate statistics per user
        user_stats = {}
        for note in result:
            user_id = note.get('user_id_pk_int')
            if user_id not in user_stats:
                user_stats[user_id] = {
                    'count': 0,
                    'first': None,
                    'last': None,
                    'content_types': {},
                    'note_ids': []
                }

            user_stats[user_id]['count'] += 1

            created_at = note.get('created_at')
            if created_at:
                ts = int(created_at)
                if user_stats[user_id]['first'] is None or ts < user_stats[user_id]['first']:
                    user_stats[user_id]['first'] = ts
                if user_stats[user_id]['last'] is None or ts > user_stats[user_id]['last']:
                    user_stats[user_id]['last'] = ts

            content_type = note.get('content_type', 'text')
            user_stats[user_id]['content_types'][content_type] = \
                user_stats[user_id]['content_types'].get(content_type, 0) + 1

            unique_id = note.get('unique_id', '')
            short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
            user_stats[user_id]['note_ids'].append(short_id)

        # Display statistics
        date_str = date if date else "all time"
        print(f"User Statistics for {event_name} ({date_str})")
        print("=" * 60)

        if format_style == 2:
            print(f"{'User':<8} | {'Notes':<6} | {'First':<8} | {'Last':<8} | Note IDs")
        else:
            print(f"{'User':<8} | {'Notes':<6} | {'First':<8} | {'Last':<8} | Types")
        print("-" * 60)

        total_notes = 0
        for user_id in sorted(user_stats.keys()):
            stats = user_stats[user_id]
            total_notes += stats['count']

            first_time = datetime.fromtimestamp(stats['first'], tz=timezone.utc).strftime('%H:%M') if stats['first'] else '?'
            last_time = datetime.fromtimestamp(stats['last'], tz=timezone.utc).strftime('%H:%M') if stats['last'] else '?'

            if format_style == 2:
                last_col = '[' + ','.join(stats['note_ids']) + ']'
            else:
                last_col = ', '.join(f"{k}:{v}" for k, v in sorted(stats['content_types'].items()))

            print(f"u{user_id:<7} | {stats['count']:<6} | {first_time:<8} | {last_time:<8} | {last_col}")

        print("-" * 60)
        print(f"Total: {total_notes} notes from {len(user_stats)} users")

    except Exception as e:
        print(f"Error getting stats: {e}", file=sys.stderr)
        sys.exit(1)


def event_status(client: AigonClient, event_name: str,
                 date: Optional[str] = None,
                 test_users: Optional[List[int]] = None,
                 test_only: bool = False,
                 filter_users: Optional[List[int]] = None) -> None:
    """Show event status overview - where am I now?

    Shows counts of processed/unprocessed notes and general stats.

    Args:
        test_only: If True, only show test user data instead of filtering them out
        filter_users: If provided, only include these user IDs (client-side filter)
    """
    try:
        # Determine date range
        start_ts = None
        end_ts = None

        if date:
            base_date = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
            start_of_day = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = base_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            start_ts = int(start_of_day.timestamp())
            end_ts = int(end_of_day.timestamp())
            date_str = date
        else:
            date_str = "all time"

        # Get test users from config if not provided
        if test_users is None:
            test_users = get_test_users()

        # Get all notes
        result = client.get_recent_notes(
            limit=10000,
            max_bytes=-1,
            processed_status='all',
            note_type='user',
            time_window_start=None,
            start_ts=start_ts,
            end_ts=end_ts,
            reverse=False,
            event=event_name
        )

        # Filter test users
        if test_users:
            if test_only:
                result = [n for n in result if n.get('user_id_pk_int') in test_users]
            else:
                result = [n for n in result if n.get('user_id_pk_int') not in test_users]

        # Filter to specific users if requested
        if filter_users:
            result = [n for n in result if n.get('user_id_pk_int') in filter_users]

        # Calculate stats
        total = len(result)
        processed = sum(1 for n in result if n.get('processed_at'))
        unprocessed = total - processed

        users = set(n.get('user_id_pk_int') for n in result)
        user_count = len(users)

        # Time range
        timestamps = [int(n.get('created_at', 0)) for n in result if n.get('created_at')]
        if timestamps:
            first_ts = min(timestamps)
            last_ts = max(timestamps)
            first_time = datetime.fromtimestamp(first_ts, tz=timezone.utc).strftime('%H:%M')
            last_time = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime('%H:%M')
            time_range = f"{first_time} - {last_time}"
        else:
            time_range = "-"

        # Per user stats
        total_per_user = total / user_count if user_count > 0 else 0
        unprocessed_per_user = unprocessed / user_count if user_count > 0 else 0
        processed_per_user = processed / user_count if user_count > 0 else 0

        # Display
        print()
        print("=" * 40)
        print(f"\033[1m{'Event Status'.center(40)}\033[0m")
        print(event_name.center(40))
        print("=" * 40)
        print(f"Date:  {date_str}")
        print(f"Users: {user_count}")
        print("=" * 40)
        print()
        print(f"{'':14} {'Count':>6}  {'/User':>6}")
        print("-" * 40)
        print(f"{'Total':<14} {total:>6}  {total_per_user:>6.1f}")
        print(f"{'Processed':<14} {processed:>6}  {processed_per_user:>6.1f}")
        print("-" * 40)

        # Bold unprocessed if > 0
        if unprocessed > 0:
            print(f"\033[1m{'Unprocessed':<14} {unprocessed:>6}  {unprocessed_per_user:>6.1f}\033[0m")
        else:
            print(f"{'Unprocessed':<14} {unprocessed:>6}  {unprocessed_per_user:>6.1f}")
        print("-" * 40)
        print()

    except Exception as e:
        print(f"Error getting status: {e}", file=sys.stderr)
        sys.exit(1)


def event_watch(client: AigonClient, event_name: str,
                interval: float = 1.0,
                start_time: Optional[str] = None,
                clear_screen: bool = False,
                simulate_rate: Optional[float] = None,
                test_users: Optional[List[int]] = None,
                test_only: bool = False,
                filter_users: Optional[List[int]] = None) -> None:
    """Watch mode: continuously monitor for new submissions.

    Displays a single updating status line with progress indicator.
    When new notes arrive, prints timeline to terminal flow.
    Refreshes every `interval` minutes. Exit with Ctrl+C.

    Args:
        interval: Minutes between checks (supports fractions like 0.5)
        start_time: Optional start time for timeline HH:MM (default: now)
        clear_screen: If True, clear screen and show full status each refresh
        simulate_rate: If set, simulate messages at this rate per minute (Poisson arrivals)
        test_only: If True, only show test user data instead of filtering them out
        filter_users: If provided, only include these user IDs (client-side filter)
    """
    import time
    import random

    # Determine timeline start time
    now = datetime.now(timezone.utc)
    if start_time:
        watch_start = parse_time(start_time, now)
    else:
        watch_start = now
    watch_start_ts = int(watch_start.timestamp())

    # Get test users from config if not provided
    if test_users is None:
        test_users = get_test_users()

    # Track previous state to detect changes
    prev_unprocessed = None
    prev_total = None

    # Simulation: pre-generate all arrivals for 30 minutes, starting 5 seconds from now
    simulated_notes = []
    sim_start_ts = watch_start_ts + 5  # First message arrives 5 seconds after start
    if simulate_rate:
        mean_interval = 60.0 / simulate_rate
        current_ts = float(sim_start_ts)
        end_ts = watch_start_ts + 30 * 60  # 30 minutes ahead

        while current_ts < end_ts:
            simulated_notes.append({
                'created_at': int(current_ts),
                'user_id_pk_int': random.randint(1, 10),
                'processed_at': None,
                'unique_id': f'sim_{len(simulated_notes):04d}'
            })
            wait = random.expovariate(1.0 / mean_interval)
            current_ts += wait

    def fetch_notes():
        """Fetch and filter notes (or return simulated notes up to now).

        Only returns notes created at or after watch_start_ts.
        """
        if simulate_rate:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            return [n for n in simulated_notes if n['created_at'] <= now_ts and n['created_at'] >= watch_start_ts]

        result = client.get_recent_notes(
            limit=10000,
            max_bytes=-1,
            processed_status='all',
            note_type='user',
            time_window_start=None,
            start_ts=watch_start_ts,  # Only notes after watch start time
            end_ts=None,
            reverse=False,
            event=event_name
        )

        # Filter test users
        if test_users:
            if test_only:
                result = [n for n in result if n.get('user_id_pk_int') in test_users]
            else:
                result = [n for n in result if n.get('user_id_pk_int') not in test_users]

        # Filter to specific users if requested
        if filter_users:
            result = [n for n in result if n.get('user_id_pk_int') in filter_users]

        return result

    def print_timeline(notes):
        """Print timeline bar chart for notes.

        Shows bins with at least 1 second granularity.
        Only shows bins that have messages.
        """
        # Get all notes with timestamps
        recent_notes = [n for n in notes if n.get('created_at')]

        if not recent_notes:
            return

        timestamps = [int(n.get('created_at')) for n in recent_notes]
        first_ts = min(timestamps)
        now_ts = int(datetime.now(timezone.utc).timestamp())

        # Minimum 1 second bins, max 20 bins
        time_span = max(now_ts - first_ts, 1)
        num_bins = min(20, time_span)  # At most 1 bin per second
        bin_seconds = max(1, (time_span + num_bins - 1) // num_bins)  # Ceiling division

        print()
        first_dt = datetime.fromtimestamp(first_ts, tz=timezone.utc)
        print(f"Timeline (since {first_dt.strftime('%H:%M:%S')}):")

        # Build buckets
        buckets = {}
        for ts in timestamps:
            bucket_ts = (ts // bin_seconds) * bin_seconds
            buckets[bucket_ts] = buckets.get(bucket_ts, 0) + 1

        if not buckets:
            return

        max_count = max(buckets.values())
        bar_width = 30

        # Only show non-empty buckets
        for bucket_ts in sorted(buckets.keys()):
            count = buckets[bucket_ts]
            dt = datetime.fromtimestamp(bucket_ts, tz=timezone.utc)
            time_str = dt.strftime('%H:%M:%S')

            bar_len = int((count / max_count) * bar_width) if max_count > 0 else 0
            bar = '█' * bar_len
            print(f"  {time_str} | {count:3d} | {bar}")

        print()

    def format_status_line(unprocessed, check_time, progress_pct=None):
        """Format the single-line status display."""
        # Bold unprocessed if > 0
        if unprocessed > 0:
            status = f"[{check_time}] \033[1m{unprocessed} unprocessed\033[0m"
        else:
            status = f"[{check_time}] 0 unprocessed"

        if progress_pct is not None:
            # Progress bar: 10 chars with 8 fractional states each = 80 visual states
            fractional_blocks = ' ▏▎▍▌▋▊▉█'  # 9 states: 0/8 to 8/8
            # Convert percentage to 0-80 scale
            total_eighths = int(progress_pct * 80 / 100)
            full_chars = total_eighths // 8
            frac_idx = total_eighths % 8

            bar = '█' * full_chars
            if full_chars < 10:
                bar += fractional_blocks[frac_idx]
                bar += ' ' * (9 - full_chars)

            status += f" ▕{bar}▏"

        return status

    # Setup for non-blocking key detection
    import select
    import termios
    import tty

    old_settings = None
    try:
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
    except (termios.error, AttributeError):
        pass  # Not a TTY, skip key detection

    def check_for_exit_key():
        """Check if ESC or q was pressed (non-blocking)."""
        if old_settings is None:
            return False
        try:
            if select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch == '\x1b' or ch == 'q':  # ESC or q
                    return True
        except (select.error, IOError):
            pass
        return False

    def print_header():
        """Print the watch mode header."""
        if simulate_rate:
            print(f"Watching {event_name} [SIMULATE {simulate_rate}/min] (interval: {interval}min, since: {watch_start.strftime('%H:%M')})")
        else:
            print(f"Watching {event_name} (interval: {interval}min, since: {watch_start.strftime('%H:%M')})")
        print("Press ESC or Ctrl+C to exit")
        print()

    # Print initial header (non-clear mode only - clear mode prints each cycle)
    if not clear_screen:
        print_header()

    # Hide cursor
    print("\033[?25l", end="", flush=True)

    # Assert simulation starts with 0 unprocessed
    if simulate_rate:
        initial_notes = fetch_notes()
        initial_unprocessed = sum(1 for n in initial_notes if not n.get('processed_at'))
        assert initial_unprocessed == 0, f"Simulation should start with 0 unprocessed, got {initial_unprocessed}"
        print(f"✓ Assertion passed: started with {initial_unprocessed} unprocessed")

    try:
        while True:
            # Check for exit key
            if check_for_exit_key():
                break

            # Fetch first (keep old display visible during API call)
            result = fetch_notes()

            # Clear screen and show header AFTER fetch (when ready to redraw)
            if clear_screen:
                print("\033[2J\033[H", end="", flush=True)
                print_header()

            # Calculate stats
            check_time = datetime.now(timezone.utc).strftime('%H:%M:%S')

            total = len(result)
            processed = sum(1 for n in result if n.get('processed_at'))
            unprocessed = total - processed

            prev_unprocessed = unprocessed
            prev_total = total

            if unprocessed > 0:
                # TIMELINE MODE: show timeline and wait for interval
                if not clear_screen:
                    print("\r" + " " * 120 + "\r", end="")  # Clear line in non-clear mode
                print_timeline(result)
                print(f"[{check_time}] \033[1m{unprocessed} unprocessed\033[0m - waiting {interval}min...")

                # Wait for interval, checking for exit key
                interval_seconds = interval * 60
                steps = 20
                step_seconds = interval_seconds / steps
                for i in range(steps):
                    if check_for_exit_key():
                        raise KeyboardInterrupt
                    time.sleep(step_seconds)
            else:
                # PROGRESS BAR MODE: single line status with progress bar
                interval_seconds = interval * 60
                steps = 80
                step_seconds = interval_seconds / steps

                for i in range(steps):
                    if check_for_exit_key():
                        raise KeyboardInterrupt
                    progress_pct = (i / steps) * 100
                    status_line = format_status_line(unprocessed, check_time, progress_pct)
                    print(f"\r{status_line}", end="", flush=True)
                    time.sleep(step_seconds)

                # Final 100% before next fetch
                status_line = format_status_line(unprocessed, check_time, 100)
                print(f"\r{status_line}", end="", flush=True)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("\033[?25h", end="")  # Show cursor
        print(f"\nError in watch mode: {e}", file=sys.stderr)
        if old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        sys.exit(1)
    finally:
        print("\033[?25h", end="")  # Show cursor
        if old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        print("\n\nWatch mode stopped.")


def _prompt(prompt_text: str, default: str = '') -> str:
    """Prompt user for input with default value.

    Args:
        prompt_text: Text to display
        default: Default value (shown in brackets)

    Returns:
        User input or default if empty
    """
    if default:
        result = input(f"{prompt_text} [{default}]: ").strip()
        return result if result else default
    else:
        return input(f"{prompt_text}: ").strip()


def _mask_token(token: str) -> str:
    """Mask a token for display."""
    if not token:
        return ''
    if len(token) <= 8:
        return '*' * len(token)
    return token[:4] + '*' * (len(token) - 8) + token[-4:]


def event_mark(client: AigonClient, unique_ids: List[str],
               processed: bool,
               output_format: str = 'llm') -> None:
    """Mark event participant notes as processed.

    Args:
        client: Authenticated Aigon client
        unique_ids: List of unique IDs (or prefixes) to mark
        processed: True=mark as processed, False=unmark
        output_format: Output format (llm for concise, json for full details)
    """
    try:
        result = client.mark_notes(unique_ids=unique_ids, processed=processed,
                                   exported=None, deleted=None)

        if output_format == 'json':
            print(json.dumps(result, indent=2))
        else:
            # LLM format: concise output
            if result.get('success'):
                batch_size = result.get('batch_size', 0)
                action_str = "processed" if processed else "unprocessed"
                print(f"Marked {batch_size} note(s) as {action_str}")
            else:
                print(f"Failed: {result.get('message', 'Unknown error')}", file=sys.stderr)
                sys.exit(1)

    except Exception as e:
        print(f"Error marking notes: {e}", file=sys.stderr)
        sys.exit(1)


def event_config_interactive() -> None:
    """Interactive configuration for event settings."""
    print("Event Configuration")
    print("=" * 40)
    print("Press Enter to keep current value, or type new value.\n")

    # Get current values as defaults
    current_token = get_config_value('event', 'token') or ''
    current_name = get_event_name() or ''
    current_test = get_config_value('event', 'test_users') or ''
    current_admin = get_config_value('event', 'admin_users') or ''

    # Prompt for values - token first (most important)
    token_display = _mask_token(current_token) if current_token else ''
    event_token = _prompt("Event API token", token_display)
    # If user entered something different from masked version, use it
    if event_token and event_token != token_display:
        set_config_value('event', 'token', event_token)
        print(f"  Set event.token = {_mask_token(event_token)}")

    event_name = _prompt("Event name", current_name)
    test_users = _prompt("Test user IDs (comma-separated, to ignore)", current_test)
    admin_users = _prompt("Admin user IDs (comma-separated)", current_admin)

    # Periods
    print("\nTime periods (leave blank to skip):")
    periods = get_periods()

    # Show existing periods and allow editing
    period_num = 1
    while True:
        period_key = str(period_num)
        current_period = ''
        if period_key in periods:
            start, end = periods[period_key]
            current_period = f"{start}-{end}"

        period_value = _prompt(f"  Period {period_num} (HH:MM-HH:MM)", current_period)

        if not period_value and not current_period:
            # No value entered and no existing value - stop asking
            break

        if period_value:
            set_config_value('event', f'period.{period_key}', period_value)
            print(f"    Set period.{period_key} = {period_value}")
        elif current_period:
            # Keep existing
            pass

        period_num += 1
        if period_num > 10:  # Safety limit
            break

    # Save non-empty values
    print()
    if event_name:
        set_config_value('event', 'name', event_name)
        print(f"Set event.name = {event_name}")

    if test_users:
        set_config_value('event', 'test_users', test_users)
        print(f"Set event.test_users = {test_users}")

    if admin_users:
        set_config_value('event', 'admin_users', admin_users)
        print(f"Set event.admin_users = {admin_users}")

    print("\nConfiguration saved.")


def event_config_cmd(event_token: Optional[str] = None,
                     event_name: Optional[str] = None,
                     test_users: Optional[str] = None,
                     admin_users: Optional[str] = None,
                     period_name: Optional[str] = None,
                     period_value: Optional[str] = None,
                     show: bool = False,
                     init_local: bool = False,
                     interactive: bool = False) -> None:
    """Configure event settings.

    Args:
        event_token: Event API token to set
        event_name: Event name to set
        test_users: Comma-separated test user IDs
        admin_users: Comma-separated admin user IDs
        period_name: Period name to set (e.g., "1" for period.1)
        period_value: Period time range (e.g., "10:00-10:30")
        show: Show current config
        init_local: Initialize local .aigon file
        interactive: Run interactive configuration
    """
    if init_local:
        local_path = os.path.join(os.getcwd(), '.aigon')
        if not os.path.exists(local_path):
            with open(local_path, 'w') as f:
                f.write('')
            print(f"Created local config file: {local_path}")
        else:
            print(f"Local config file already exists: {local_path}")

    if interactive:
        event_config_interactive()
        return

    # Show config if --show or no options provided
    no_options = (event_token is None and event_name is None and test_users is None
                  and admin_users is None and period_name is None and period_value is None
                  and not init_local)
    if show or no_options:
        config = load_config()
        config_path = get_config_path()
        print(f"Config file: {config_path}")

        if config.has_section('event'):
            print("\n[event]")
            for option in config.options('event'):
                value = config.get('event', option)
                # Mask token for display
                if option == 'token':
                    value = _mask_token(value)
                print(f"  {option} = {value}")
        else:
            print("\nNo event configuration found")

        # Show configured periods
        periods = get_periods()
        if periods:
            print("\nConfigured periods:")
            for name, (start, end) in sorted(periods.items()):
                print(f"  {name}: {start} - {end}")
        return

    # Set values
    if event_token:
        set_config_value('event', 'token', event_token)
        print(f"Set event.token = {_mask_token(event_token)}")

    if event_name:
        set_config_value('event', 'name', event_name)
        print(f"Set event.name = {event_name}")

    if test_users is not None:
        set_config_value('event', 'test_users', test_users)
        print(f"Set event.test_users = {test_users}")

    if admin_users is not None:
        set_config_value('event', 'admin_users', admin_users)
        print(f"Set event.admin_users = {admin_users}")

    if period_name and period_value:
        set_config_value('event', f'period.{period_name}', period_value)
        print(f"Set event.period.{period_name} = {period_value}")


# ===== CLI Registration =====

def register_event_commands(subparsers):
    """Register event commands with argument parser."""
    event_parser = subparsers.add_parser('event', help='Event admin operations')
    event_subparsers = event_parser.add_subparsers(dest='event_command', help='Event commands')

    # Config command
    config_parser = event_subparsers.add_parser('config', help='Configure event settings')
    config_parser.add_argument('-i', '--interactive', action='store_true',
                               help='Interactive configuration mode')
    config_parser.add_argument('--token', dest='event_token',
                               help='Set event API token')
    config_parser.add_argument('--name', dest='event_name', help='Set event name')
    config_parser.add_argument('--test-users', dest='test_users',
                               help='Comma-separated test user IDs to filter out')
    config_parser.add_argument('--admin-users', dest='admin_users',
                               help='Comma-separated admin user IDs')
    config_parser.add_argument('--period', dest='period_name',
                               help='Period name to configure (e.g., "1" for period.1)')
    config_parser.add_argument('--period-value', dest='period_value',
                               help='Period time range (e.g., "10:00-10:30")')
    config_parser.add_argument('--show', action='store_true',
                               help='Show current event configuration')
    config_parser.add_argument('--init', action='store_true', dest='init_local',
                               help='Initialize local .aigon config file')

    # Read command
    read_parser = event_subparsers.add_parser('read', help='Read event participant notes')
    read_parser.add_argument('--event', dest='event_name',
                             help='Event name (default: from config)')
    read_parser.add_argument('--limit', type=int, default=50,
                             help='Maximum notes (default: 50)')
    read_parser.add_argument('--format', choices=['json', 'llm', 'snippet'], default='llm',
                             help='Output format (default: llm)')
    read_parser.add_argument('--time', dest='time_range',
                             help='Time range HH:MM-HH:MM [TZ] (e.g., 10:35-10:50 CET)')
    read_parser.add_argument('--start-time', dest='start_time',
                             help='Start time HH:MM [TZ]')
    read_parser.add_argument('--end-time', dest='end_time',
                             help='End time HH:MM [TZ]')
    read_parser.add_argument('--period', dest='period',
                             help='Use configured period (e.g., "1" for period.1)')
    read_parser.add_argument('--date', dest='date',
                             help='Date filter (ISO format, default: today)')
    read_parser.add_argument('--newest', action='store_true',
                             help='Get most recent notes (reversed order)')
    # Processed status filtering
    read_parser.add_argument('--processed', action='store_true',
                             help='Only processed notes')
    read_parser.add_argument('--unprocessed', action='store_true',
                             help='Only unprocessed notes (default)')
    read_parser.add_argument('--all', action='store_true',
                             help='All notes (processed and unprocessed)')
    read_parser.add_argument('--test-only', action='store_true', dest='test_only',
                             help='Only show test user data (instead of filtering them out)')
    read_parser.add_argument('--users', dest='filter_users',
                             help='Comma-separated user IDs to include (client-side filter)')
    # Download options
    read_parser.add_argument('--download', nargs='?', const='_event_notes', default=None,
                             help='Download notes to files. Optionally specify directory (default: _event_notes)')
    read_parser.add_argument('--clear', action='store_true',
                             help='Clear directory before downloading notes (requires --download)')
    read_parser.add_argument('--with-attachments', dest='with_attachments',
                             choices=['true', 'false'], default='true',
                             help='Download attachments with notes (default: true)')

    # Mark command
    mark_parser = event_subparsers.add_parser('mark', help='Mark participant notes as processed')
    mark_parser.add_argument('unique_ids', nargs='+', help='Unique IDs of notes to mark (minimum 2 characters each)')
    mark_parser.add_argument('--processed', nargs='?', const='true', choices=['true', 'false'],
                             help='Mark/unmark as processed (default: true if flag present)')
    mark_parser.add_argument('--format', choices=['json', 'llm'], default='llm',
                             help='Output format (default: llm)')

    # Timeline command
    timeline_parser = event_subparsers.add_parser('timeline', help='Show submission timeline')
    timeline_parser.add_argument('--event', dest='event_name',
                                 help='Event name (default: from config)')
    timeline_parser.add_argument('--date', dest='date',
                                 help='Date filter (ISO format, default: today)')
    timeline_parser.add_argument('--from', dest='from_time',
                                 help='Start time HH:MM [TZ] (only notes after this)')
    timeline_parser.add_argument('--to', dest='to_time',
                                 help='End time HH:MM [TZ] (only notes before this)')
    timeline_parser.add_argument('--format', dest='format_style', type=int, choices=[1, 2, 3], default=2,
                                 help='Format: 1=user IDs, 2=bar chart (default), 3=note IDs')
    timeline_parser.add_argument('--bucket', dest='bucket_minutes', type=int, default=None,
                                 help='Minutes per bucket. Auto-selects for 10-30 buckets if not specified.')
    # Processed status filtering
    timeline_parser.add_argument('--processed', action='store_true',
                                 help='Only processed notes')
    timeline_parser.add_argument('--unprocessed', action='store_true',
                                 help='Only unprocessed notes')
    timeline_parser.add_argument('--all', action='store_true',
                                 help='All notes (default)')
    timeline_parser.add_argument('--test-only', action='store_true', dest='test_only',
                                 help='Only show test user data (instead of filtering them out)')
    timeline_parser.add_argument('--users', dest='filter_users',
                                 help='Comma-separated user IDs to include (client-side filter)')

    # Status command
    status_parser = event_subparsers.add_parser('status', help='Show event status overview')
    status_parser.add_argument('--event', dest='event_name',
                               help='Event name (default: from config)')
    status_parser.add_argument('--date', dest='date',
                               help='Date filter (ISO format, default: all time)')
    status_parser.add_argument('--test-only', action='store_true', dest='test_only',
                               help='Only show test user data (instead of filtering them out)')
    status_parser.add_argument('--users', dest='filter_users',
                               help='Comma-separated user IDs to include (client-side filter)')

    # Watch command
    watch_parser = event_subparsers.add_parser('watch', help='Watch mode: continuously monitor for new submissions')
    watch_parser.add_argument('--event', dest='event_name',
                              help='Event name (default: from config)')
    watch_parser.add_argument('--interval', type=float, default=1.0,
                              help='Minutes between checks (default: 1, supports fractions like 0.5)')
    watch_parser.add_argument('--start', dest='start_time',
                              help='Start time for timeline HH:MM (default: now)')
    watch_parser.add_argument('--clear', action='store_true',
                              help='Clear screen mode: full status display with screen refresh')
    watch_parser.add_argument('--simulate', type=float, nargs='?', const=5.0, default=None,
                              help='Simulate messages (default: 5/min Poisson arrivals) for testing')
    watch_parser.add_argument('--test-only', action='store_true', dest='test_only',
                              help='Only show test user data (instead of filtering them out)')
    watch_parser.add_argument('--users', dest='filter_users',
                              help='Comma-separated user IDs to include (client-side filter)')

    # Stats command
    stats_parser = event_subparsers.add_parser('stats', help='Show user statistics')
    stats_parser.add_argument('--event', dest='event_name',
                              help='Event name (default: from config)')
    stats_parser.add_argument('--date', dest='date',
                              help='Date filter (ISO format, default: all time)')
    stats_parser.add_argument('--format', dest='format_style', type=int, choices=[1, 2], default=2,
                              help='Format: 1=content types, 2=note IDs (default)')
    stats_parser.add_argument('--test-only', action='store_true', dest='test_only',
                              help='Only show test user data (instead of filtering them out)')
    stats_parser.add_argument('--users', dest='filter_users',
                              help='Comma-separated user IDs to include (client-side filter)')

    # Help command
    event_subparsers.add_parser('help', help='Show event help')


def handle_event_command(args, client: AigonClient = None):
    """Handle event commands.

    Args:
        args: Parsed command-line arguments
        client: Authenticated Aigon client (None for config command)
    """
    if args.event_command == 'config':
        event_config_cmd(
            event_token=getattr(args, 'event_token', None),
            event_name=getattr(args, 'event_name', None),
            test_users=getattr(args, 'test_users', None),
            admin_users=getattr(args, 'admin_users', None),
            period_name=getattr(args, 'period_name', None),
            period_value=getattr(args, 'period_value', None),
            show=getattr(args, 'show', False),
            init_local=getattr(args, 'init_local', False),
            interactive=getattr(args, 'interactive', False)
        )
    elif args.event_command == 'read':
        # Get event name from args or config
        event_name = getattr(args, 'event_name', None) or get_event_name()
        if not event_name:
            print("Error: No event name specified. Use --event or configure with 'aigon event config --name <event>'", file=sys.stderr)
            sys.exit(1)

        # Validate --clear requires --download
        if getattr(args, 'clear', False) and getattr(args, 'download', None) is None:
            print("Error: --clear requires --download flag", file=sys.stderr)
            sys.exit(1)

        # Determine processed_status from flags
        if getattr(args, 'all', False):
            processed_status = 'all'
        elif getattr(args, 'processed', False):
            processed_status = 'processed'
        else:
            # Default: unprocessed only
            processed_status = 'unprocessed'

        # Parse --with-attachments (string to bool)
        with_attachments_str = getattr(args, 'with_attachments', 'true')
        with_attachments = with_attachments_str == 'true'

        event_read(client, event_name=event_name,
                   limit=args.limit,
                   output_format=args.format,
                   time_range=getattr(args, 'time_range', None),
                   start_time=getattr(args, 'start_time', None),
                   end_time=getattr(args, 'end_time', None),
                   period=getattr(args, 'period', None),
                   date=getattr(args, 'date', None),
                   newest=getattr(args, 'newest', False),
                   processed_status=processed_status,
                   test_only=getattr(args, 'test_only', False),
                   filter_users=parse_user_list(getattr(args, 'filter_users', None)),
                   download_directory=getattr(args, 'download', None),
                   clear_directory=getattr(args, 'clear', False),
                   with_attachments=with_attachments)
    elif args.event_command == 'mark':
        # Convert string arg to bool or None
        processed = None
        if hasattr(args, 'processed') and args.processed:
            processed = args.processed == 'true'

        # Validate flag is specified
        if processed is None:
            print("Error: --processed flag must be specified", file=sys.stderr)
            sys.exit(1)

        event_mark(client, unique_ids=args.unique_ids, processed=processed,
                   output_format=args.format)
    elif args.event_command == 'timeline':
        event_name = getattr(args, 'event_name', None) or get_event_name()
        if not event_name:
            print("Error: No event name specified", file=sys.stderr)
            sys.exit(1)

        # Determine processed_status from flags (default: all)
        if getattr(args, 'processed', False):
            processed_status = 'processed'
        elif getattr(args, 'unprocessed', False):
            processed_status = 'unprocessed'
        else:
            processed_status = 'all'

        event_timeline(client, event_name=event_name,
                       date=getattr(args, 'date', None),
                       from_time=getattr(args, 'from_time', None),
                       to_time=getattr(args, 'to_time', None),
                       format_style=getattr(args, 'format_style', 2),
                       bucket_minutes=getattr(args, 'bucket_minutes', None),
                       processed_status=processed_status,
                       test_only=getattr(args, 'test_only', False),
                       filter_users=parse_user_list(getattr(args, 'filter_users', None)))
    elif args.event_command == 'status':
        event_name = getattr(args, 'event_name', None) or get_event_name()
        if not event_name:
            print("Error: No event name specified", file=sys.stderr)
            sys.exit(1)

        event_status(client, event_name=event_name,
                     date=getattr(args, 'date', None),
                     test_only=getattr(args, 'test_only', False),
                     filter_users=parse_user_list(getattr(args, 'filter_users', None)))
    elif args.event_command == 'watch':
        event_name = getattr(args, 'event_name', None) or get_event_name()
        if not event_name:
            print("Error: No event name specified", file=sys.stderr)
            sys.exit(1)

        event_watch(client, event_name=event_name,
                    interval=getattr(args, 'interval', 1.0),
                    start_time=getattr(args, 'start_time', None),
                    clear_screen=getattr(args, 'clear', False),
                    simulate_rate=getattr(args, 'simulate', None),
                    test_only=getattr(args, 'test_only', False),
                    filter_users=parse_user_list(getattr(args, 'filter_users', None)))
    elif args.event_command == 'stats':
        event_name = getattr(args, 'event_name', None) or get_event_name()
        if not event_name:
            print("Error: No event name specified", file=sys.stderr)
            sys.exit(1)

        event_stats(client, event_name=event_name,
                    date=getattr(args, 'date', None),
                    format_style=getattr(args, 'format_style', 2),
                    test_only=getattr(args, 'test_only', False),
                    filter_users=parse_user_list(getattr(args, 'filter_users', None)))
    elif args.event_command == 'help':
        print("Event Commands - Admin operations for event participant notes")
        print("")
        print("Setup:")
        print("  aigon event config --init              Initialize local .aigon config")
        print("  aigon event config --name <event>      Set event name")
        print("  aigon event config --test-users 1,2,3  Set test user IDs to filter out")
        print("  aigon event config --period 1 --period-value 10:00-10:30")
        print("  aigon event config --show              Show current configuration")
        print("")
        print("Read Notes:")
        print("  aigon event read                       Read participant notes")
        print("  aigon event read --time 10:35-10:50    Filter by time range")
        print("  aigon event read --period 1            Use configured period")
        print("  aigon event read --date 2026-01-15     Specific date")
        print("  aigon event read --newest              Most recent first")
        print("  aigon event read --format snippet      Compact output")
        print("")
        print("Analysis:")
        print("  aigon event timeline                   Show submission timeline")
        print("  aigon event stats                      Show user statistics")
        print("  aigon event stats --date 2026-01-15    Stats for specific date")
        print("  aigon event status                     Show event status overview")
        print("")
        print("Watch Mode:")
        print("  aigon event watch                      Monitor for new submissions")
        print("  aigon event watch --interval 0.5       Check every 30 seconds")
        print("  aigon event watch --start 10:30        Timeline from specific time")
        print("")
        print("Note: Uses local .aigon config file (expected for event mode)")
    else:
        print(f"Unknown event command: {args.event_command}", file=sys.stderr)
        print("Use 'aigon event help' for available commands", file=sys.stderr)
        sys.exit(1)

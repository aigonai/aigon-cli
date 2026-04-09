"""Global search commands for Aigon CLI.

This module provides command-line interface functions for global search
operations across notes, attachments, and files.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Optional

from .client import AigonClient


def _format_result_merged(result: dict, output_format: str) -> None:
    """Format and print merged search results."""
    if output_format == "json":
        # Exclude content from JSON output by default
        print(json.dumps(result, indent=2, default=str))
        return

    # LLM-friendly format
    results = result.get("results", [])
    total = result.get("total_count", 0)
    returned = result.get("returned_count", 0)
    query = result.get("query", "")

    print(f"Global Search: '{query}'")
    print(f"Found {total} results, showing {returned}")
    print("-" * 60)

    for i, item in enumerate(results, 1):
        resource_type = item.get("resource_type", "unknown")
        unique_id = item.get("unique_id", "unknown")
        short_id = unique_id[:6] if len(unique_id) >= 6 else unique_id
        relevance = item.get("relevance", 0)

        if resource_type == "note":
            created_at = item.get("created_at")
            note_type = item.get("note_type", "user")
            agent = item.get("agent", "notetaker")
            snippet = ""
            matches = item.get("matches", [])
            if matches:
                snippet = matches[0].get("snippet", "")
            # Show snippet or truncated content
            content = snippet or (item.get("content", "")[:100] + "..." if item.get("content") else "")

            date_str = _format_timestamp(created_at)
            print(f"{i}. [NOTE] {short_id} | {date_str} | {note_type}/{agent} | rel:{relevance:.3f}")
            if content:
                print(f"   {content}")

        elif resource_type == "attachment":
            note_id = item.get("note_unique_id", "")[:6]
            filename = item.get("original_filename", item.get("filename", "unknown"))
            mime_type = item.get("mime_type", "")
            snippet = item.get("snippet", "")

            print(f"{i}. [ATTACHMENT] {short_id} (note: {note_id}) | {filename} | {mime_type} | rel:{relevance:.3f}")
            if snippet:
                print(f"   {snippet}")

        elif resource_type == "file":
            namespace = item.get("namespace", "")
            basename = item.get("basename", "")
            version = item.get("version", 1)
            snippet = item.get("snippet", "")

            print(f"{i}. [FILE] {short_id} | {namespace}{basename} (v{version}) | rel:{relevance:.3f}")
            if snippet:
                print(f"   {snippet}")

        print()


def _format_result_grouped(result: dict, output_format: str) -> None:
    """Format and print grouped search results."""
    if output_format == "json":
        print(json.dumps(result, indent=2, default=str))
        return

    # LLM-friendly format
    notes = result.get("notes", [])
    attachments = result.get("attachments", [])
    files = result.get("files", [])
    total = result.get("total_count", 0)
    query = result.get("query", "")

    print(f"Global Search: '{query}'")
    print(f"Found {total} total results")
    print("=" * 60)

    if notes:
        print(f"\nNOTES ({len(notes)} results)")
        print("-" * 40)
        for note in notes:
            unique_id = note.get("unique_id", "")[:6]
            created_at = note.get("created_at")
            note_type = note.get("note_type", "user")
            relevance = note.get("relevance", 0)
            date_str = _format_timestamp(created_at)

            snippet = ""
            matches = note.get("matches", [])
            if matches:
                snippet = matches[0].get("snippet", "")

            print(f"  {unique_id} | {date_str} | {note_type} | rel:{relevance:.3f}")
            if snippet:
                print(f"    {snippet}")

    if attachments:
        print(f"\nATTACHMENTS ({len(attachments)} results)")
        print("-" * 40)
        for att in attachments:
            unique_id = att.get("unique_id", "")[:6]
            filename = att.get("original_filename", "")
            relevance = att.get("relevance", 0)
            snippet = att.get("snippet", "")

            print(f"  {unique_id} | {filename} | rel:{relevance:.3f}")
            if snippet:
                print(f"    {snippet}")

    if files:
        print(f"\nFILES ({len(files)} results)")
        print("-" * 40)
        for f in files:
            unique_id = f.get("unique_id", "")[:6]
            basename = f.get("basename", "")
            namespace = f.get("namespace", "")
            version = f.get("version", 1)
            relevance = f.get("relevance", 0)
            snippet = f.get("snippet", "")

            print(f"  {unique_id} | {namespace}{basename} (v{version}) | rel:{relevance:.3f}")
            if snippet:
                print(f"    {snippet}")


def _format_timestamp(ts) -> str:
    """Format Unix timestamp to readable string."""
    if not ts:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "unknown"


def do_global_search(
    client: AigonClient,
    query: str,
    scope: str = "all",
    grouping: str = "merged",
    note_type: str = "all",
    file_versions: str = "latest",
    time_window_start: Optional[float] = None,
    time_window_end: float = 0.0,
    export_status: str = "all",
    processed_status: str = "all",
    deleted_status: str = "active",
    agent: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "relevance",
    order_dir: str = "desc",
    output_format: str = "llm",
) -> None:
    """Execute global search and display results.

    Args:
        client: Authenticated Aigon client
        query: Search query string
        scope: Comma-separated scopes (notes,system,attachments,files,all)
        grouping: Result grouping (merged, grouped)
        note_type: Note type filter (user, system, ephemeral, all)
        file_versions: File versions (latest, all)
        time_window_start: Days back from now (None = all time)
        time_window_end: Days back to end (0 = now)
        export_status: Export status filter
        processed_status: Processed status filter
        deleted_status: Deleted status filter
        agent: Agent filter
        limit: Max results
        offset: Skip first N results
        order_by: Sort order (relevance, created, updated)
        order_dir: Sort direction (desc, asc)
        output_format: Output format (json, llm)
    """
    try:
        result = client.global_search(
            query=query,
            scope=scope,
            grouping=grouping,
            note_type=note_type,
            file_versions=file_versions,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            export_status=export_status,
            processed_status=processed_status,
            deleted_status=deleted_status,
            agent=agent,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir,
        )

        # Determine response grouping
        response_grouping = result.get("grouping", "merged")

        if response_grouping == "grouped":
            _format_result_grouped(result, output_format)
        else:
            _format_result_merged(result, output_format)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def register_search_commands(subparsers) -> None:
    """Register search commands with argparse.

    Args:
        subparsers: Argparse subparsers to register commands with
    """
    search_parser = subparsers.add_parser("search", help="Global search across notes, attachments, and files")

    # Required argument
    search_parser.add_argument("query", help='Search query (supports "phrase", OR, -exclude)')

    # Scope options
    search_parser.add_argument(
        "--scope", "-s", default="all", help="Comma-separated: notes,system,attachments,files,all (default: all)"
    )

    # Grouping and format options
    search_parser.add_argument(
        "--grouping",
        "-g",
        choices=["merged", "grouped"],
        default="merged",
        help="Result grouping: merged (single list) or grouped (by type)",
    )
    search_parser.add_argument(
        "--format", "-f", choices=["json", "llm"], default="llm", help="Output format: json or llm (default: llm)"
    )

    # Note filters
    search_parser.add_argument(
        "--note-type",
        choices=["user", "system", "ephemeral", "all"],
        default="all",
        help="Note type filter (default: all)",
    )

    # File filters
    search_parser.add_argument(
        "--file-versions",
        choices=["latest", "all"],
        default="latest",
        help="File versions: latest or all (default: latest)",
    )

    # Time filters
    search_parser.add_argument("--days", type=float, default=None, help="Search last N days (shortcut for --from N)")
    search_parser.add_argument("--from", dest="time_from", type=float, default=None, help="Days back to start search")
    search_parser.add_argument(
        "--to", dest="time_to", type=float, default=0.0, help="Days back to end search (default: 0 = now)"
    )
    search_parser.add_argument("--recent", action="store_true", help="Last 24 hours (shortcut for --days 1)")
    search_parser.add_argument("--week", action="store_true", help="Last 7 days (shortcut for --days 7)")

    # Status filters
    search_parser.add_argument(
        "--export-status", choices=["all", "exported", "unexported"], default="all", help="Export status filter"
    )
    search_parser.add_argument(
        "--processed-status", choices=["all", "processed", "unprocessed"], default="all", help="Processed status filter"
    )
    search_parser.add_argument(
        "--deleted-status",
        choices=["active", "deleted", "all"],
        default="active",
        help="Deleted status filter (default: active)",
    )

    # Agent filter
    search_parser.add_argument("--agent", default=None, help="Filter notes by agent (notetaker, wellness, coach, etc.)")

    # Result options
    search_parser.add_argument("--limit", "-l", type=int, default=50, help="Maximum results (default: 50)")
    search_parser.add_argument("--offset", type=int, default=0, help="Skip first N results")
    search_parser.add_argument(
        "--order-by",
        choices=["relevance", "created", "updated"],
        default="relevance",
        help="Sort order (default: relevance)",
    )
    search_parser.add_argument(
        "--order-dir", choices=["desc", "asc"], default="desc", help="Sort direction (default: desc)"
    )


def handle_search_command(args, client: AigonClient) -> None:
    """Handle search command.

    Args:
        args: Parsed command line arguments
        client: Authenticated Aigon client
    """
    # Process time shortcuts
    time_from = args.time_from
    if args.days is not None:
        time_from = args.days
    elif args.recent:
        time_from = 1.0
    elif args.week:
        time_from = 7.0

    do_global_search(
        client=client,
        query=args.query,
        scope=args.scope,
        grouping=args.grouping,
        note_type=args.note_type,
        file_versions=args.file_versions,
        time_window_start=time_from,
        time_window_end=args.time_to,
        export_status=args.export_status,
        processed_status=args.processed_status,
        deleted_status=args.deleted_status,
        agent=args.agent,
        limit=args.limit,
        offset=args.offset,
        order_by=args.order_by,
        order_dir=args.order_dir,
        output_format=args.format,
    )

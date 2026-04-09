"""LLM-specific commands for Aigon CLI.

This module provides LLM-friendly help and command documentation.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import sys


def register_llm_commands(subparsers):
    """Register LLM help commands with argument parser.

    Registers ``llmhelp`` as the primary subcommand for LLM-friendly
    command reference and help.

    Args:
        subparsers: Argument parser subparsers object
    """
    llmhelp_parser = subparsers.add_parser("llmhelp", help="LLM-friendly command reference")
    llmhelp_parser.add_argument(
        "topic",
        nargs="*",
        default=[],
        help="Topic: notes/notetaker, files/filedb, event, or a command path",
    )


def handle_llm_command(args):
    """Handle LLM commands with 3-level progressive disclosure.

    Level 0: aigon llmhelp (no args) → overview
    Level 1: aigon llmhelp notes (1 arg, domain) → domain help
    Level 2: aigon llmhelp notetaker read (2+ args) → per-command help

    Args:
        args: Parsed command-line arguments
    """
    topics = getattr(args, "topic", []) or []
    # Filter out 'help' - it's just noise
    topics = [t for t in topics if t != "help"]

    if not topics:
        # Level 0: overview
        show_llm_help()
    elif len(topics) == 1:
        # Level 1: domain-level help
        topic = topics[0]
        if topic in ("notes", "notetaker"):
            show_llm_help_notes()
        elif topic in ("files", "filedb"):
            show_llm_help_files()
        elif topic in ("event", "events"):
            show_llm_help_event()
        else:
            print(f"Unknown topic: {topic}", file=sys.stderr)
            print("Available: notes, files, event", file=sys.stderr)
            sys.exit(1)
    else:
        # Level 2: per-command help
        command_path = " ".join(topics)
        show_level_2_help(command_path)


def get_help_for_command(command_path):
    """Get help content for a command path (any level).

    Tries to match:
    1. Exact Level 2 match (e.g., "notetaker read")
    2. Domain/Level 1 match (e.g., "notetaker" → notes help, "filedb" → files help)
    3. Returns None if no match found

    Args:
        command_path: Space-separated command path (e.g., "notetaker read" or "notes")

    Returns:
        Help content string, or None if not found
    """
    # Try exact Level 2 match first
    if command_path in LEVEL_2_HELP:
        return LEVEL_2_HELP[command_path]

    # Try domain-level match (first word)
    parts = command_path.split()
    if parts:
        domain = parts[0].lower()

        # Map domain aliases to help getters
        domain_map = {
            "notetaker": get_llm_help_content_notes,
            "notes": get_llm_help_content_notes,
            "filedb": get_llm_help_content_files,
            "files": get_llm_help_content_files,
            "event": get_llm_help_content_event,
            "events": get_llm_help_content_event,
        }

        if domain in domain_map:
            return domain_map[domain]()

    return None


def show_level_2_help(command_path):
    """Display per-command help for LLMs (Level 2).

    Args:
        command_path: Space-separated command path (e.g., "notetaker read")
    """
    if command_path in LEVEL_2_HELP:
        print(LEVEL_2_HELP[command_path])
    else:
        print(f"No detailed help for: {command_path}", file=sys.stderr)
        print("Available: see 'aigon llmhelp <domain>'", file=sys.stderr)
        sys.exit(1)


# Level 2: Per-command help pages
LEVEL_2_HELP = {
    "notetaker read": """
# aigon notetaker read

Read notes. Default: oldest 10 unprocessed (for processing backlogs in order).

## Usage

  aigon notetaker read                        # Oldest 10 unprocessed
  aigon notetaker read --newest 5             # Newest 5 notes (any status)
  aigon notetaker read abc123 def456          # Specific notes by ID

## Flags

  --limit N             Max notes (default: 10)
  --newest [N]          Most recent first (default: 1 when present)
  --all                 Include processed notes (default: unprocessed only)
  --format FMT          Output format: llm (default), json, snippet, summary
  --note-type TYPE      Filter by type: user (default), system, all
  --agent AGENT         Filter by agent: coach, wellness, flat
  --days N              Last N days only
  --recent              Last 24 hours
  --week                Last 7 days
  --forever             All time (no time filter)
  --context N           For ID lookups: show N notes before/after
  --save [DIR]          Save to files (default dir: _notes/)

## Notes

Default ordering is oldest-first (for processing backlogs in order).
Use --newest to switch to most-recent-first.
Truncation: default max-bytes is 5000. Use --max-bytes -1 for full content.

## Full reference

  aigon notetaker read --help-argparse
""",
    "notetaker mark": """
# aigon notetaker mark

Mark notes as processed, exported, or deleted.

## Usage

  aigon notetaker mark --processed abc123 def456    # Mark as processed
  aigon notetaker mark --processed=false abc123      # Unmark
  aigon notetaker mark --exported abc123             # Mark as exported
  aigon notetaker mark --deleted abc123              # Soft delete

## Flags

  --processed [BOOL]    Mark/unmark as processed (default: true when present)
  --exported [BOOL]     Mark/unmark as exported (default: true when present)
  --deleted [BOOL]      Soft delete/undelete (default: true when present)

## Notes

You can combine flags: --processed --exported marks both.
Boolean flags default to true when present. Use =false to unmark.
Example: aigon notetaker mark --processed=false abc123 unmarks a note.

## Full reference

  aigon notetaker mark --help-argparse
""",
    "notetaker search": """
# aigon notetaker search

Full-text search for notes.

## Usage

  aigon notetaker search "query"              # Search all notes
  aigon notetaker search "query" --days 7     # Last 7 days
  aigon notetaker search "query" --limit 5    # Top 5 results

## Flags

  --limit N             Max results (default: 10 for llm, 100 for snippet)
  --format FMT          Output format: llm (default), json, snippet, summary
  --days N              Last N days only
  --recent              Last 24 hours
  --week                Last 7 days
  --all                 Include processed notes

## Notes

Search is full-text. Returns notes matching the query, sorted by relevance.

## Full reference

  aigon notetaker search --help-argparse
""",
    "notetaker attachment": """
# aigon notetaker attachment

Get an attachment from a note.

## Usage

  aigon notetaker attachment abc123                   # Output first attachment
  aigon notetaker attachment abc123 --save            # Save to file
  aigon notetaker attachment abc123 photo.jpg         # Specific attachment by filename

## Flags

  --save [DIR]          Save to directory instead of stdout (default: current dir)

## Notes

Without --save, content goes to stdout (text/binary).
If a note has multiple attachments, specify filename as second argument.
If omitted, returns the first (or only) attachment.

## Full reference

  aigon notetaker attachment --help-argparse
""",
    "notetaker delegate": """
# aigon notetaker delegate

Delegate notes to an agent.

## Usage

  aigon notetaker delegate abc123 --add coach         # Assign to coach
  aigon notetaker delegate abc123 --remove wellness   # Remove from wellness
  aigon notetaker delegate abc123 def456 --add flat   # Multiple notes

## Flags

  --add AGENT           Assign to agent: coach, wellness, flat
  --remove AGENT        Remove from agent

## Notes

A note can be delegated to multiple agents.

## Full reference

  aigon notetaker delegate --help-argparse
""",
    "notetaker reply": """
# aigon notetaker reply

Send a reply to a note.

## Usage

  aigon notetaker reply abc123 "Your reply text"     # Send reply
  aigon notetaker reply abc123 --from file.txt       # Reply from file

## Flags

  --from FILE           Read reply from file
  --format FMT          Output format: json (default), text

## Notes

Replies appear as attachments/comments on the note.

## Full reference

  aigon notetaker reply --help-argparse
""",
    "notetaker send": """
# aigon notetaker send

Send a new note to the system.

## Usage

  aigon notetaker send "Note text"                    # Send text note
  aigon notetaker send --from file.txt                # Send from file
  aigon notetaker send --from photo.jpg --type image  # Send attachment

## Flags

  --from FILE           Read content from file
  --type TYPE           Content type: text (default), image, audio
  --agent AGENT         Assign to agent: coach, wellness, flat

## Notes

Automatically timestamps and assigns a unique ID.

## Full reference

  aigon notetaker send --help-argparse
""",
    "filedb list": """
# aigon filedb list

List files in FileDB namespace.

## Usage

  aigon filedb list                          # List all files
  aigon filedb list --format json            # JSON output

## Flags

  --format FMT          Output format: text (default), json

## Notes

Shows file name, size, last modified, version count.

## Full reference

  aigon filedb list --help-argparse
""",
    "filedb read": """
# aigon filedb read

Read a file from FileDB to stdout.

## Usage

  aigon filedb read myfile                    # Output file content
  aigon filedb read myfile --version 3        # Specific version

## Flags

  --version N           Read specific version (default: latest)

## Notes

Works for any file type (markdown, text, binary). Outputs to stdout.
Use --download to save to local file instead.

## Full reference

  aigon filedb read --help-argparse
""",
    "filedb upload": """
# aigon filedb upload

Upload a file to FileDB.

## Usage

  aigon filedb upload myfile                  # Upload single file
  aigon filedb upload --all                   # Upload all local .md files that exist in FileDB

## Flags

  --all                 Upload all local files that exist in FileDB namespace

## Notes

Creates or updates the file in FileDB. Keeps version history.

## Full reference

  aigon filedb upload --help-argparse
""",
    "filedb download": """
# aigon filedb download

Download a file from FileDB to local.

## Usage

  aigon filedb download myfile                # Download single file
  aigon filedb download --all                 # Download all files that exist locally

## Flags

  --all                 Download all files that exist as local .md files

## Notes

Saves to current directory (or --dir DIR).
Overwrites local file if it exists.

## Full reference

  aigon filedb download --help-argparse
""",
    "filedb check": """
# aigon filedb check

Check sync status between local and FileDB.

## Usage

  aigon filedb check                          # Check all local .md files
  aigon filedb check myfile                   # Check specific file
  aigon filedb checkall                       # Check all including remote-only files

## Flags

  (none for basic usage)

## Notes

Shows which files are:
  - In sync (local and remote have same content)
  - Out of sync (different versions)
  - Local-only (not in FileDB yet)
  - Remote-only (only in FileDB, not local)

## Full reference

  aigon filedb check --help-argparse
""",
    "event read": """
# aigon event read

Read notes from a live event.

## Usage

  aigon event read                            # Unprocessed notes (default)
  aigon event read --all                      # All notes
  aigon event read --newest 10                # Latest 10 notes

## Flags

  --all                 Include processed notes
  --newest [N]          Most recent first (default: 1)
  --format FMT          Output format: llm (default), json, snippet
  --time HH:MM-HH:MM    Time range filter
  --date YYYY-MM-DD     Specific date
  --users 1,2,3         Filter by user IDs
  --download [DIR]      Save to directory (default: _event_notes/)

## Notes

Event config comes from .aigon file in current directory (not ~/.aigon).

## Full reference

  aigon event read --help-argparse
""",
    "event mark": """
# aigon event mark

Mark event notes as processed.

## Usage

  aigon event mark abc123 def456 --processed   # Mark as processed
  aigon event mark abc123 --processed=false    # Unmark

## Flags

  --processed [BOOL]    Mark/unmark as processed (default: true)

## Notes

Same as notetaker mark, but for event-local notes.

## Full reference

  aigon event mark --help-argparse
""",
    "event watch": """
# aigon event watch

Monitor for new notes in real time.

## Usage

  aigon event watch                           # Check every minute (default)
  aigon event watch --interval 0.5            # Check every 30 seconds
  aigon event watch --clear                   # Full-screen mode
  aigon event watch --start 10:30             # Start time for timeline

## Flags

  --interval N          Check interval in minutes (default: 1)
  --clear               Clear screen for full-screen display
  --start HH:MM         Timeline start time
  --simulate N          Test mode: N fake msgs/min

## Notes

Shows a live bar chart of note submissions over time.
Press ESC or Ctrl+C to exit.

## Full reference

  aigon event watch --help-argparse
""",
    "event timeline": """
# aigon event timeline

Show timeline of note submissions.

## Usage

  aigon event timeline                        # Bar chart (default)
  aigon event timeline --format 1             # With user IDs
  aigon event timeline --format 3             # With note IDs
  aigon event timeline --from 10:30 --to 11:00  # Time range

## Flags

  --format N            Display format: 0=bar (default), 1=users, 3=note IDs
  --bucket N            Bucket size in minutes (default: 5)
  --from HH:MM          Start time
  --to HH:MM            End time

## Notes

Useful for understanding submission patterns during the event.

## Full reference

  aigon event timeline --help-argparse
""",
}


def get_llm_help_content_notes():
    """Get concise notetaker help content (Level 1)."""
    return """
# Notetaker Commands (aigon llmhelp notes)

## Note References - IMPORTANT

Every note has a unique ID (e.g., abc123). When discussing notes, ALWAYS cite them:
  "The user mentioned a meeting [abc123] and follow-up tasks [def456]."

Format: [xxxxxx] - 6 character ID in square brackets.

## Note Ordering: --limit vs --newest

Default: oldest N unprocessed (for processing backlogs in order)
Use --newest N: for recent recordings/notes

## Commands

### Read notes
  aigon notetaker read                      # Oldest 10 unprocessed (default)
  aigon notetaker read --newest 5           # Newest 5 notes
  aigon notetaker read abc123 def456        # Specific notes by ID
  aigon notetaker read abc123 --context 3   # Note + 3 before + 3 after

### Search notes
  aigon notetaker search "query"            # Full-text search
  aigon notetaker search "query" --days 7   # Last 7 days

### Mark as processed
  aigon notetaker mark --processed abc123 def456

### Delegate notes
  aigon notetaker delegate abc123 --add coach
  aigon notetaker delegate abc123 --remove wellness

### Get attachments
  aigon notetaker attachment abc123         # Output first attachment
  aigon notetaker attachment abc123 --save

### Agent shortcuts
  aigon coach                               # Same as: notetaker read --agent coach
  aigon wellness                            # Same as: notetaker read --agent wellness

## Common flags

  --format {llm,json,snippet,summary}       # Output format (default: llm)
  --agent {coach,wellness,flat}             # Filter by agent
  --all                                     # Include processed notes
  --note-type {user,system,all}             # Filter by type (default: user)

## Per-Command Help

For detailed help on a specific notetaker command:

  aigon llmhelp notetaker read              # Detailed help for read
  aigon llmhelp notetaker mark              # Detailed help for mark
  aigon llmhelp notetaker search            # Detailed help for search
  aigon llmhelp notetaker attachment        # Detailed help for attachment
  aigon llmhelp notetaker delegate          # Detailed help for delegate
  aigon llmhelp notetaker reply             # Detailed help for reply
  aigon llmhelp notetaker send              # Detailed help for send

Works for any notetaker subcommand.
"""


def show_llm_help_notes():
    """Display concise notetaker help for LLMs."""
    print(get_llm_help_content_notes())


def get_llm_help_content_files():
    """Get concise filedb help content (Level 1)."""
    return """
# FileDB Commands (aigon llmhelp files)

FileDB stores versioned markdown files in the cloud.

## Commands

### List files
  aigon filedb list                       # List all files in namespace

### Read file (to stdout)
  aigon filedb read myfile                # Output file content

### Download/Upload
  aigon filedb download myfile            # Download single file
  aigon filedb download --all             # Download all existing local files
  aigon filedb upload myfile              # Upload single file
  aigon filedb upload --all               # Upload all existing FileDB files

### Check sync status
  aigon filedb check                      # Check all local .md files
  aigon filedb check myfile               # Check specific file
  aigon filedb checkall                   # Check all files against FileDB

## Per-Command Help

For detailed help on a specific filedb command:

  aigon llmhelp filedb list                # Detailed help for list
  aigon llmhelp filedb read                # Detailed help for read
  aigon llmhelp filedb upload              # Detailed help for upload
  aigon llmhelp filedb download            # Detailed help for download
  aigon llmhelp filedb check               # Detailed help for check

Works for any filedb subcommand.
"""


def show_llm_help_files():
    """Display concise filedb help for LLMs."""
    print(get_llm_help_content_files())


def get_llm_help_content_event():
    """Get concise event help content (Level 1)."""
    return """
# Event Commands (aigon llmhelp event)

Event mode is for administering live events where participants submit notes.
Uses local .aigon config file in current directory (not ~/.aigon).

## Setup

### Initialize local config
  aigon event config --init               # Create .aigon in current directory
  aigon event config -i                   # Interactive setup (recommended)

### Configure event
  aigon event config --token <token>      # Set API token
  aigon event config --name <event>       # Set event name
  aigon event config --test-users 1,2,3   # Test user IDs to filter out
  aigon event config --show               # Show current config

### Configure time periods
  aigon event config --period 1 --period-value 10:00-10:30
  aigon event config --period 2 --period-value 10:45-11:15

## Reading Notes

### Basic reading
  aigon event read                        # Unprocessed notes (default)
  aigon event read --all                  # All notes
  aigon event read --processed            # Only processed notes
  aigon event read --newest               # Most recent first

### Time filtering
  aigon event read --time 10:35-10:50     # Time range (HH:MM-HH:MM)
  aigon event read --period 1             # Use configured period
  aigon event read --start-time 10:30     # Notes after this time
  aigon event read --end-time 11:00       # Notes before this time
  aigon event read --date 2026-01-15      # Specific date

### Output formats
  --format llm                            # Detailed (default)
  --format snippet                        # One-liner per note
  --format json                           # JSON output

### User filtering
  aigon event read --test-only            # Only test users (for testing)
  aigon event read --users 5,10,15        # Only these user IDs

### Download notes to files
  aigon event read --download             # Download to _event_notes/
  aigon event read --download my_dir      # Download to my_dir/
  aigon event read --download --clear     # Clear dir before downloading
  aigon event read --download --with-attachments false  # Skip attachments

Files are named: YYYYMMDD_HHMMZ_u<user_id>_<note_id>_<type>.md
Attachments are named: YYYYMMDD_HHMMZ_u<user_id>_<note_id>_<filename>
(This naming ensures notes and their attachments sort together)

## Analysis Commands

### Timeline - when notes were submitted
  aigon event timeline                    # Bar chart (default)
  aigon event timeline --format 1         # Detailed with user IDs
  aigon event timeline --format 3         # With note IDs
  aigon event timeline --bucket 5         # 5-minute buckets
  aigon event timeline --from 10:30 --to 11:00

### Stats - per-user statistics
  aigon event stats                       # All time
  aigon event stats --date 2026-01-15     # Specific date
  aigon event stats --format 1            # Content types
  aigon event stats --format 2            # Note IDs (default)

### Status - quick overview
  aigon event status                      # Processed/unprocessed counts

## Watch Mode

Live monitoring for new submissions:
  aigon event watch                       # Check every minute
  aigon event watch --interval 0.5        # Check every 30 seconds
  aigon event watch --start 10:30         # Timeline starts at 10:30
  aigon event watch --clear               # Full-screen mode
  aigon event watch --simulate 5          # Test with 5 fake msgs/min

Press ESC or Ctrl+C to exit watch mode.

## Mark Notes as Processed

  aigon event mark abc123 def456 --processed
  aigon event mark abc123 --processed=false  # Unmark

## Typical Workflow

1. Setup: aigon event config -i
2. Monitor: aigon event watch --start 10:00
3. Review: aigon event read --period 1
4. Analyze: aigon event timeline --from 10:00 --to 10:30
5. Process: aigon event mark <ids> --processed

## Per-Command Help

For detailed help on a specific event command:

  aigon llmhelp event read                 # Detailed help for read
  aigon llmhelp event mark                 # Detailed help for mark
  aigon llmhelp event watch                # Detailed help for watch
  aigon llmhelp event timeline             # Detailed help for timeline

Works for any event subcommand.
"""


def show_llm_help_event():
    """Display concise event help for LLMs."""
    print(get_llm_help_content_event())


def get_llm_help_content():
    """Get brief LLM-friendly intro content (Level 0)."""
    return """
# Aigon CLI — Quick Reference

## Note References - IMPORTANT

Every note has a unique ID (e.g., abc123). When discussing notes, ALWAYS cite them:
  "The user mentioned a meeting [abc123] and follow-up tasks [def456]."

Format: [xxxxxx] - 6 character ID in square brackets.

## Core Workflow: Read → Process → Mark

  aigon notetaker read                    # Get unprocessed notes (oldest first)
  (... process each note ...)
  aigon notetaker mark --processed abc123 # Mark as done
  (repeat until no unprocessed notes remain)

## Quick Peek (most recent, not for processing)

  aigon notetaker read --newest 3         # Latest 3 notes (any status)

## Domains

  aigon llmhelp notes                     # All notetaker commands (read, mark, search, etc.)
  aigon llmhelp files                     # All filedb commands (list, read, upload, etc.)
  aigon llmhelp event                     # All event commands (read, watch, timeline, etc.)

## Per-Command Help

For detailed help on a specific command, drill down:

  aigon llmhelp notetaker read            # Detailed help for notetaker read
  aigon llmhelp filedb upload             # Detailed help for filedb upload
  aigon llmhelp event watch               # Detailed help for event watch

Works for any command: aigon llmhelp <domain> <command>

## Full Reference

  aigon <command> --help-argparse         # Full argparse help (all flags)
"""


def show_llm_help():
    """Display brief LLM-friendly intro (Level 0)."""
    print(get_llm_help_content())

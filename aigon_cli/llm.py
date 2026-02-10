"""LLM-specific commands for Aigon CLI.

This module provides LLM-friendly help and command documentation.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import sys


def register_llm_commands(subparsers):
    """Register LLM commands with argument parser.

    Args:
        subparsers: Argument parser subparsers object
    """
    llm_parser = subparsers.add_parser('llm', help='LLM-friendly command reference')
    llm_parser.add_argument('topic', nargs='*', default=[],
                            help='Topic: notes/notetaker, files/filedb, or omit for full reference')


def handle_llm_command(args):
    """Handle LLM commands.

    Args:
        args: Parsed command-line arguments
    """
    topics = getattr(args, 'topic', []) or []
    # Filter out 'help' - it's just noise
    topics = [t for t in topics if t != 'help']

    if not topics:
        show_llm_help()
    elif any(t in ('notes', 'notetaker') for t in topics):
        show_llm_help_notes()
    elif any(t in ('files', 'filedb') for t in topics):
        show_llm_help_files()
    elif any(t in ('event', 'events') for t in topics):
        show_llm_help_event()
    else:
        print(f"Unknown topic: {' '.join(topics)}", file=sys.stderr)
        print("Available: notes, notetaker, files, filedb, event", file=sys.stderr)
        sys.exit(1)


def show_llm_help_notes():
    """Display concise notetaker help for LLMs."""
    help_text = """
# Notetaker Commands (aigon llm notes)

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
  aigon notetaker search "query" --last 7   # Last 7 days

### Mark as processed
  aigon notetaker mark --processed abc123 def456

### Delegate notes
  aigon notetaker delegate abc123 --add coach
  aigon notetaker delegate abc123 --remove wellness

### Get attachments
  aigon notetaker attachment abc123         # Output first attachment
  aigon notetaker attachment abc123 --download

### Agent shortcuts
  aigon coach                               # Same as: notetaker read --agent coach
  aigon wellness                            # Same as: notetaker read --agent wellness

## Common flags
  --format {llm,json,snippet,summary}       # Output format (default: llm)
  --agent {coach,wellness,flat}             # Filter by agent
  --all                                     # Include processed notes
  --note-type {user,system,all}             # Filter by type (default: user)
"""
    print(help_text)


def show_llm_help_files():
    """Display concise filedb help for LLMs."""
    help_text = """
# FileDB Commands (aigon llm files)

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
"""
    print(help_text)


def show_llm_help_event():
    """Display concise event help for LLMs."""
    help_text = """
# Event Commands (aigon llm event)

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
"""
    print(help_text)


def show_llm_help():
    """Display brief LLM-friendly intro."""
    help_text = """
# Aigon CLI

## Note References - IMPORTANT

Every note has a unique ID (e.g., abc123). When discussing notes, ALWAYS cite them:
  "The user mentioned a meeting [abc123] and follow-up tasks [def456]."

Format: [xxxxxx] - 6 character ID in square brackets.

## Commands

  aigon llm notes                         # Notetaker command reference
  aigon llm files                         # FileDB command reference
  aigon llm event                         # Event admin command reference

  aigon notetaker read                    # Read notes (oldest 10 unprocessed)
  aigon notetaker read abc123             # Read specific note by ID
  aigon notetaker search "query"          # Full-text search
  aigon notetaker mark --processed abc123 # Mark note as processed

  aigon filedb list                       # List files
  aigon filedb read myfile                # Read file content

  aigon event read                        # Read event participant notes
  aigon event watch                       # Monitor for new submissions

  aigon <command> --help                  # Detailed help for any command
"""
    print(help_text)

#!/usr/bin/env python3
"""Aigon CLI - Main command-line interface.

This is the main entry point for the Aigon CLI tool that provides command-line
access to the Agent01 REST API.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import argparse
import os
import sys

from .version import __version__, __date__
from .client import AigonClient
from .config import get_api_token, get_api_url, register_config_commands, handle_config_command, set_config_path
from .filedb import register_filedb_commands, handle_filedb_command
from .notetaker import register_notetaker_commands, handle_notetaker_command
from .fileserver import register_fileserver_commands, handle_fileserver_command
from .llm import register_llm_commands, handle_llm_command
from .crypto import register_crypto_commands, handle_crypto_command
from .vtt2md import register_vtt2md_commands, handle_vtt2md_command
from .report import register_report_commands, handle_report_command
from .event import register_event_commands, handle_event_command, get_event_token
from .download import register_download_commands, handle_download_command
from .search import register_search_commands, handle_search_command


def create_client(base_url: str, token: str) -> AigonClient:
    """Create and validate API client.

    Args:
        base_url: Base URL for the REST API
        token: Authentication token

    Returns:
        Configured AigonClient

    Raises:
        SystemExit: If client creation or validation fails
    """
    try:
        client = AigonClient(base_url=base_url, api_token=token)
        # Test connection
        client.get_health()
        return client
    except Exception as e:
        print(f"Failed to connect to API at {base_url}: {e}", file=sys.stderr)
        print("Make sure the REST API server is running and your token is valid.", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    # Handle shortcuts by transforming sys.argv before parsing
    # aigon coach read -> aigon notetaker read --agent coach
    # aigon wellness search -> aigon notetaker search --agent wellness
    # aigon coach -> aigon notetaker read --agent coach (default to read)

    # Valid notetaker subcommands
    NOTETAKER_SUBCOMMANDS = {'read', 'search', 'mark', 'delegate'}

    if len(sys.argv) > 1:
        if sys.argv[1] in ('coach', 'wellness'):
            agent_name = sys.argv[1]
            sys.argv[1] = 'notetaker'

            # Check if there's a notetaker subcommand
            if len(sys.argv) > 2 and sys.argv[2] in NOTETAKER_SUBCOMMANDS:
                # Has valid subcommand: aigon coach read ... -> aigon notetaker read ... --agent coach
                # Append --agent at the end
                sys.argv.extend(['--agent', agent_name])
            elif len(sys.argv) > 2 and not sys.argv[2].startswith('-'):
                # Has something that's not a valid notetaker subcommand and not a flag
                # This is invalid usage - let argparse handle the error
                pass
            else:
                # No subcommand or starts with flag: aigon coach ... -> aigon notetaker read ... --agent coach
                sys.argv.insert(2, 'read')  # Default to read
                sys.argv.extend(['--agent', agent_name])

    parser = argparse.ArgumentParser(
        prog='aigon',
        description='Aigon CLI - Command-line interface for Agent01 REST API',
        epilog=f'Version {__version__} ({__date__})'
    )

    parser.add_argument('--version', action='version',
                       version=f'aigon {__version__} ({__date__})')

    parser.add_argument('--config-file',
                       help='Config file path (default: ~/.aigon or AIGON_CLI_CONFIG_FILE env var)')

    parser.add_argument('--url', default=None,
                       help='REST API base URL (default: https://api.aigon.ai or from config)')

    parser.add_argument('--token',
                       help='API authentication token (default: from AIGON_API_TOKEN env var)')

    parser.add_argument('--format', choices=['json', 'table'], default='table',
                       help='Default output format (default: table)')

    # Add subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Add help command
    help_parser = subparsers.add_parser('help', help='Show help information')
    help_parser.add_argument('subcommand', nargs='?', help='Show help for specific subcommand')

    # Register module commands
    register_config_commands(subparsers)
    register_filedb_commands(subparsers)
    register_notetaker_commands(subparsers)
    register_fileserver_commands(subparsers)
    register_llm_commands(subparsers)
    register_crypto_commands(subparsers)
    register_vtt2md_commands(subparsers)
    register_report_commands(subparsers)
    register_event_commands(subparsers)
    register_download_commands(subparsers)
    register_search_commands(subparsers)

    # Register coach and wellness in help (they're handled by sys.argv transformation)
    # These won't actually be used since sys.argv is transformed, but shows in --help
    subparsers.add_parser('coach', help='Coach agent commands (accepts: read, search, mark)', add_help=False)
    subparsers.add_parser('wellness', help='Wellness agent commands (accepts: read, search, mark)', add_help=False)

    # Parse arguments
    args = parser.parse_args()

    # Set config file path if specified (before any config access)
    if args.config_file:
        set_config_path(args.config_file)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle commands that don't require authentication
    if args.command == 'viewer':
        handle_fileserver_command(args)
        sys.exit(0)

    if args.command == 'llm':
        handle_llm_command(args)
        sys.exit(0)

    if args.command == 'crypto':
        handle_crypto_command(args)
        sys.exit(0)

    if args.command == 'vtt2md':
        handle_vtt2md_command(args)
        sys.exit(0)

    if args.command == 'report':
        exit_code = handle_report_command(args)
        sys.exit(exit_code)

    if args.command == 'config':
        handle_config_command(args)
        sys.exit(0)

    # Event commands use local .aigon by default (no warning)
    if args.command == 'event':
        # Set config to local .aigon in current directory (expected for event mode)
        if not args.config_file:  # Only if not explicitly overridden
            set_config_path(os.path.join(os.getcwd(), '.aigon'))

        # Config and help don't require authentication
        if getattr(args, 'event_command', None) in ['config', 'help', None]:
            handle_event_command(args, client=None)
            sys.exit(0)

    # Handle help command and notetaker help before requiring authentication
    if args.command == 'help':
        if hasattr(args, 'subcommand') and args.subcommand:
            # Show help for specific subcommand
            if args.subcommand == 'filedb':
                print("FileDB Help - File management with versioning\n")
                print("Available FileDB commands:")
                print("  list      - List files in namespace")
                print("  read      - Read file and save locally")
                print("  write     - Write file to FileDB")
                print("  create    - Create a new empty file")
                print("  delete    - Delete a file")
                print("  readall   - Read all files from namespace")
                print("  writeall  - Write all local .md files to FileDB")
                print("  check     - Check if local file matches FileDB")
                print("  checkall  - Check all local files against FileDB")
                print("  hash      - Calculate MD5 hash of local file")
                print("  init      - Initialize workspace with .claude structure and system commands")
                print("  help      - Show FileDB help information")
                print(f"\nFor detailed command help: aigon filedb <command> --help")
                print("For FileDB command overview: aigon filedb help")
            elif args.subcommand == 'notetaker':
                os.system(f"{sys.executable} -m app.infrastructure.restapi_cli.cli notetaker --help")
            else:
                print(f"Unknown subcommand: {args.subcommand}")
                print("Available subcommands: filedb, notetaker")
        else:
            # Show general help
            parser.print_help()
            print("\nFor module-specific help:")
            print("  aigon help filedb    - Show FileDB commands and usage")
            print("  aigon help notetaker - Show Notetaker commands and usage")
        sys.exit(0)
    elif args.command == 'notetaker' and hasattr(args, 'notetaker_command') and args.notetaker_command == 'help':
            # Handle notetaker help without requiring authentication
            if hasattr(args, 'subcommand') and args.subcommand:
                # Show help for specific notetaker subcommand
                if args.subcommand == 'search':
                    print("Search Command Help - Search through notetaker notes with advanced filtering\n")
                    print("Usage: aigon notetaker search <query> [OPTIONS]")
                    print("  query                  Search query string")
                    print("  --type {text,audio,image}  Filter by content type")
                    print("  --limit INTEGER        Maximum results (default: 10)")
                    print("  --last [N]             Get the N most recent notes (default: 1)")
                    print("  --format {json,llm}    Output format (default: llm)")
                    print("  --download [DIRECTORY] Download notes to files (default: _notes)")
                    print("  --clear                Clear directory before downloading")
                    print("\nTime Filtering:")
                    print("  --from DAYS           Days back to start search (e.g., --from 7)")
                    print("  --to DAYS             Days back to end search (default: 0.0 = now)")
                    print("  --days DAYS           Search last N days (shortcut for --from N --to 0)")
                    print("  --recent              Search last day (shortcut for --from 1)")
                    print("  --week                Search last week (shortcut for --from 7)")
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
                    print("  aigon notetaker search 'meeting' --days 3 --unexported")
                    print("  aigon notetaker search '' --last 5   # Get 5 most recent notes")
                    print("  aigon notetaker search 'todo' --new --titles-only")
                elif args.subcommand == 'read':
                    print("Read Notes Command Help - Get recent notes from notetaker\n")
                    print("Usage: aigon notetaker read [OPTIONS]")
                    print("  --limit INTEGER        Maximum notes (default: 10)")
                    print("  --last [N]             Get the N most recent notes (default: 1)")
                    print("  --format {json,llm}    Output format (default: llm)")
                    print("  --download [DIRECTORY] Download notes to files (default: _notes)")
                    print("  --clear                Clear directory before downloading")
                    print("\nExamples:")
                    print("  aigon notetaker read --limit 20     # Get oldest 20 notes")
                    print("  aigon notetaker read --last         # Get the most recent note")
                    print("  aigon notetaker read --last 5       # Get the 5 most recent notes")
                elif args.subcommand == 'clear':
                    print("Clear Command Help - Clear local notes directory\n")
                    print("Usage: aigon notetaker clear [OPTIONS]")
                    print("  --directory DIRECTORY  Directory to clear (default: _notes)")
                    print("\nExample: aigon notetaker clear --directory my_notes")
                else:
                    print(f"Unknown Notetaker subcommand: {args.subcommand}")
                    print("Available subcommands: search, read, clear")
            else:
                # Show general notetaker help
                print("Notetaker Help - Search and retrieve notes\n")
                print("Available Notetaker commands:")
                print("  search     - Search through notes with advanced filtering")
                print("  read       - Get recent notes")
                print("  clear      - Clear local notes directory")
                print("  help       - Show Notetaker help information")
                print("\nFor command-specific help:")
                print("  aigon notetaker help search    - Show search command help")
                print("  aigon notetaker help read      - Show read command help")
                print("  aigon notetaker <command> --help  - Show detailed help for command")
            sys.exit(0)

    # Get API token (from --token arg, env var, or config file)
    # For event commands, use event token with fallback to api token
    if args.command == 'event':
        token = args.token or get_event_token()
    else:
        token = args.token or get_api_token()

    if not token:
        print("\n❌ ERROR: No API token found!", file=sys.stderr)
        if args.command == 'event':
            print("\nFor event commands, set token with:", file=sys.stderr)
            print("   aigon event config --token <your-token>", file=sys.stderr)
            print("   (or use aigon event config -i for interactive setup)", file=sys.stderr)
        else:
            print("\nTo get an API token:", file=sys.stderr)
            print("1. Open Telegram and message @aigon_auth_bot (https://t.me/aigon_auth_bot)", file=sys.stderr)
            print("2. Send the command: /get", file=sys.stderr)
            print("3. Copy the token and either:", file=sys.stderr)
            print("   - Save to config: aigon config set api.token <your-token>", file=sys.stderr)
            print("   - Set environment variable: export AIGON_API_TOKEN=<your-token>", file=sys.stderr)
            print("   - Use --token option: aigon --token <your-token> <command>", file=sys.stderr)
        sys.exit(1)

    # Get API URL (from --url arg, env var, or config file)
    api_url = args.url or get_api_url()

    # Create API client
    client = create_client(api_url, token)

    # Handle commands
    # Note: coach/wellness are already transformed to notetaker by sys.argv manipulation
    try:
        if args.command == 'filedb':
            handle_filedb_command(args, client)
        elif args.command == 'notetaker':
            handle_notetaker_command(args, client)
        elif args.command == 'event':
            handle_event_command(args, client)
        elif args.command == 'download':
            handle_download_command(args, client)
        elif args.command == 'search':
            handle_search_command(args, client)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
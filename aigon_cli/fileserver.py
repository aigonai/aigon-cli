#!/usr/bin/env python3
"""Viewer command proxy - delegates to aigonviewer CLI.

This module acts as a thin proxy between the 'aigon viewer' command
and the 'aigonviewer' CLI. The actual viewer server and process management
logic now lives in the aigon-viewer package.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import subprocess
import sys
from importlib.metadata import version as pkg_version

try:
    expected_viewer_version = pkg_version("aigon-viewer")
except Exception:
    expected_viewer_version = None


def register_fileserver_commands(subparsers):
    """Register viewer command (proxies to aigonviewer).

    Args:
        subparsers: ArgumentParser subparsers object
    """
    import argparse

    viewer_parser = subparsers.add_parser(
        "viewer",
        help="Markdown file viewer (delegates to aigonviewer)",
        add_help=False,  # Let aigonviewer handle --help
        prefix_chars="\x00",  # Disable option parsing for this subcommand
    )
    # Accept any remaining arguments without parsing them
    viewer_parser.add_argument("viewer_args", nargs="*", help=argparse.SUPPRESS)


def handle_fileserver_command(args):
    """Proxy to aigonviewer command.

    This function extracts viewer arguments from sys.argv and passes them
    directly to the aigonviewer CLI, which handles all the actual work.

    Args:
        args: Parsed command line arguments (mostly ignored, we use sys.argv)
    """
    # Extract viewer arguments from sys.argv
    # Find where 'viewer' appears in the arguments
    try:
        viewer_index = sys.argv.index("viewer")
        # Get all arguments after 'viewer'
        viewer_args = sys.argv[viewer_index + 1 :]
    except (ValueError, IndexError):
        # No viewer command or no arguments after it
        viewer_args = []

    # Run aigonviewer command with version assertion and --remote flag
    try:
        cmd = ["aigonviewer"]
        if expected_viewer_version:
            cmd.extend(["--assert-version", expected_viewer_version])

        # Determine if first arg is an explicit subcommand
        has_explicit_subcommand = viewer_args and viewer_args[0] in ["launch", "status", "kill"]
        is_status_or_kill = viewer_args and viewer_args[0] in ["status", "kill"]

        if is_status_or_kill:
            # status or kill - pass through as-is
            cmd.extend(viewer_args)
        else:
            # It's a launch command (no args, 'launch' subcommand, path, or flags)
            should_add_remote = "--local" not in viewer_args and "-l" not in viewer_args

            if has_explicit_subcommand and viewer_args[0] == "launch":
                # Explicit 'launch' subcommand
                cmd.append("launch")
                if should_add_remote:
                    cmd.append("--remote")
                cmd.extend(viewer_args[1:])  # Rest of args after 'launch'
            else:
                # Implicit launch (no args, path, or flags) - insert 'launch' subcommand
                cmd.append("launch")
                if should_add_remote:
                    cmd.append("--remote")
                cmd.extend(viewer_args)  # All args

        result = subprocess.run(cmd, check=False, capture_output=True, text=True)

        # Check for version mismatch (exit code 3 is reserved for version mismatch)
        if result.returncode == 3:
            print(result.stderr, end="", file=sys.stderr)
            print("\n❌ You must update aigonviewer to continue.\n", file=sys.stderr)
            print("  uv tool install --upgrade aigon-viewer\n", file=sys.stderr)
            sys.exit(1)

        # Forward stdout/stderr for all other cases
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        sys.exit(result.returncode)

    except FileNotFoundError:
        print("\n❌ Error: 'aigonviewer' command not found\n", file=sys.stderr)
        print("The Aigon Viewer must be installed separately.\n", file=sys.stderr)
        print("Install uv (if not installed):", file=sys.stderr)
        print("  curl -LsSf https://astral.sh/uv/install.sh | sh\n", file=sys.stderr)
        print("Then install aigon-viewer:", file=sys.stderr)
        print("  uv tool install aigon-viewer\n", file=sys.stderr)
        sys.exit(1)

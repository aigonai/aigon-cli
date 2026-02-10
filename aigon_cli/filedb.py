"""FileDB commands for Argon CLI.

This module provides command-line interface functions for FileDB operations
including list, read, and write operations.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import os
import re
import json
import sys
import shutil
import hashlib
import yaml
from typing import Optional, List
from pathlib import Path
from datetime import datetime

from .client import AigonClient


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from content.

    Returns:
        Tuple of (frontmatter_dict, body_content)
    """
    pattern = r'^---\n(.*?)\n---\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    if match:
        frontmatter = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)
        return frontmatter, body
    return {}, content


def list_files(client: AigonClient, namespace: str = "user/", output_format: str = "llm", include_hidden: bool = False) -> None:
    """List files in FileDB namespace, filtering hidden files by default.

    By default, files starting with '_' are hidden and not displayed.
    Use include_hidden=True to show all files including those starting with '_'.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to list files from (user/ or system/)
        output_format: Output format (llm, json, table)
        include_hidden: If True, include files starting with '_' (default: False)
    """
    try:
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.list_files(system=system)

        # Get all files and filter out hidden files if not including them
        all_files = result.get('files', [])
        hidden_files = [f for f in all_files if f.get('basename', '').startswith('_')]

        if include_hidden:
            files = all_files
        else:
            files = [f for f in all_files if not f.get('basename', '').startswith('_')]

        if output_format == "llm":
            # LLM format: concise list of files
            if not files:
                print("No files found")
                return
            print(f"{len(files)} file(s):")
            for f in files:
                name = f.get('basename', 'unknown')
                version = f.get('version', '?')
                unique_id = f.get('unique_id', '')[:6]
                # Show * indicator for files that are shared
                shared_with = f.get('shared_with', [])
                shared_marker = ' *' if shared_with else ''
                print(f"  {name} (v{version}, {unique_id}){shared_marker}")
            if not include_hidden and hidden_files:
                print(f"  ({len(hidden_files)} hidden)")
        elif output_format == "json":
            # For JSON output, show filtered files but include metadata about hidden files
            output_result = result.copy()
            output_result['files'] = files
            if not include_hidden and hidden_files:
                output_result['hidden_files_count'] = len(hidden_files)
                output_result['hidden_files_note'] = f"{len(hidden_files)} files starting with '_' were hidden. Use --include-hidden to show all files."
            print(json.dumps(output_result, indent=2))
        elif output_format == "table":
            if not files and not hidden_files:
                print(f"No files found in namespace '{namespace}'")
                return
            elif not files and hidden_files:
                print(f"No visible files found in namespace '{namespace}'")
                print(f"Note: {len(hidden_files)} files starting with '_' are hidden. Use --include-hidden to show all files.")
                return

            # Calculate dynamic column width for filename
            max_filename_length = max(len(file_info.get('basename', 'unknown')) for file_info in files)
            filename_width = max(max_filename_length, len('FILENAME'))  # At least as wide as header

            # Calculate total table width
            version_width = 8
            hash_width = 32
            timestamp_width = 10
            date_width = 17  # "YYYY-MM-DD HH:MM UTC"
            total_width = filename_width + version_width + hash_width + timestamp_width + date_width + 4  # 4 spaces between columns

            # Show header with file count
            visible_count = len(files)
            total_count = len(all_files)
            if include_hidden or visible_count == total_count:
                print(f"Files in '{namespace}' ({total_count} total):")
            else:
                print(f"Files in '{namespace}' ({visible_count} visible, {total_count} total):")

            print(f"{'FILENAME':<{filename_width}} {'VERSION':<{version_width}} {'HASH_MD5':<{hash_width}} {'TIMESTAMP':>{timestamp_width}} {'UPDATED (UTC)'}")
            print("-" * total_width)

            for file_info in files:
                name = file_info.get('basename', 'unknown')
                version = file_info.get('version', 'unknown')
                hash_md5 = file_info.get('hash_MD5', 'unknown')
                created_raw = file_info.get('created_at', 'unknown')

                # Convert timestamp to UTC format if it's a number
                if isinstance(created_raw, (int, float)) and created_raw != 'unknown':
                    created_utc = datetime.fromtimestamp(created_raw).strftime('%Y-%m-%d %H:%M UTC')
                    timestamp_str = str(int(created_raw))
                else:
                    created_utc = str(created_raw)
                    timestamp_str = str(created_raw)

                print(f"{name:<{filename_width}} v{version:<{version_width-1}} {hash_md5:<{hash_width}} {timestamp_str:>{timestamp_width}} {created_utc}")

            # Show message about hidden files if any were filtered
            if not include_hidden and hidden_files:
                print()
                print(f"Note: {len(hidden_files)} files starting with '_' are hidden. Use --include-hidden to show all files.")
        else:
            print(f"Unknown output format: {output_format}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error listing files: {e}", file=sys.stderr)
        sys.exit(1)


def read_file(client: AigonClient, basename: str, namespace: str = "user/",
              version: Optional[int] = None) -> None:
    """Read a file from FileDB and output to stdout.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
        version: Optional version number
    """
    try:
        # Read from FileDB
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.read_file(basename=basename, system=system, version=version)

        if not result.get('success'):
            print(f"Error reading file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        # Extract content and print to stdout
        file_info = result.get('file_info', {})
        content = file_info.get('content', '')

        # Print content to stdout
        print(content)

    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)


def download_file(client: AigonClient, basename: str, namespace: str = "user/",
                 version: Optional[int] = None, overwrite: bool = True) -> None:
    """Download a file from FileDB and save locally as .md file.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
        version: Optional version number
        overwrite: Whether to overwrite existing local file
    """
    try:
        # Read from FileDB
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.read_file(basename=basename, system=system, version=version)

        if not result.get('success'):
            print(f"Error reading file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        # Extract file info from the API response
        file_info = result.get('file_info', {})
        content = file_info.get('content', '')
        file_version = file_info.get('version', 'unknown')
        hash_md5 = file_info.get('hash_MD5', 'unknown')
        filedb_timestamp = file_info.get('created_at', None)

        local_filename = f"{basename}.md"
        local_path = Path(local_filename)

        # Check if file exists and overwrite setting
        if local_path.exists() and not overwrite:
            print(f"File '{local_filename}' already exists. Use --overwrite to replace it.", file=sys.stderr)
            sys.exit(1)

        # Create backup if file exists
        backup_created = False
        if local_path.exists():
            backup_dir = Path(".backup")
            backup_dir.mkdir(exist_ok=True)

            # Create timestamped backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"{basename}_{timestamp}.md"
            backup_path = backup_dir / backup_filename

            # Copy existing file to backup
            shutil.copy2(local_path, backup_path)
            backup_created = True
            print(f"Existing file backed up to: .backup/{backup_filename}")

        # Write to local file (content already has frontmatter from server)
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Set file timestamp to match FileDB timestamp
        if filedb_timestamp:
            os.utime(local_path, (filedb_timestamp, filedb_timestamp))

        # Parse frontmatter to show version info
        frontmatter, _ = parse_frontmatter(content)
        fm_version = frontmatter.get('filedb_version', file_version)

        print(f"File '{basename}' (v{fm_version}) saved as '{local_filename}'")
        print(f"Content length: {len(content)} characters")
        print(f"MD5 Hash: {hash_md5}")
        if backup_created:
            print(f"Previous version backed up to .backup/ folder")

    except Exception as e:
        print(f"Error downloading file: {e}", file=sys.stderr)
        sys.exit(1)


def write_file(client: AigonClient, basename: str, file_path: Optional[str] = None,
               namespace: str = "user/", share_with: Optional[List[int]] = None,
               reshare: bool = False, no_overwrite: bool = False) -> None:
    """Write a file to FileDB.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        file_path: Path to local file to upload (default: basename.md)
        namespace: Namespace of the file
        share_with: List of user IDs to share with after upload
        reshare: If True, re-share with same users as previous version
        no_overwrite: If True, refuse upload if remote version is newer than local
    """
    try:
        # Determine source file path
        if file_path is None:
            file_path = f"{basename}.md"

        source_path = Path(file_path)
        if not source_path.exists():
            print(f"Source file '{file_path}' not found.", file=sys.stderr)
            sys.exit(1)

        # Read local file content
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Version conflict check if --no-overwrite is set
        if no_overwrite:
            # Parse local frontmatter to get version
            frontmatter, _ = parse_frontmatter(content)
            local_version = frontmatter.get('filedb_version')

            if local_version is not None:
                # Check remote version
                system = (namespace == "system/")
                try:
                    remote_result = client.read_file(basename=basename, system=system)
                    if remote_result.get('success'):
                        remote_version = remote_result.get('file_info', {}).get('version', 0)
                        if remote_version > local_version:
                            print(f"Error: Remote version ({remote_version}) is newer than local ({local_version}).",
                                  file=sys.stderr)
                            print("Download the latest version first, or remove --no-overwrite to force.",
                                  file=sys.stderr)
                            sys.exit(1)
                except Exception:
                    pass  # File might not exist yet, OK to proceed

        # Write to FileDB
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.write_file(
            basename=basename,
            content=content,
            system=system,
            reshare=reshare,
            share_with=share_with
        )

        if not result.get('success'):
            print(f"Error writing file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        # The version is in file_info, not at the top level
        file_info = result.get('file_info', {})
        new_version = file_info.get('version', 'unknown')
        hash_md5 = file_info.get('hash_MD5', 'unknown')
        unique_id = file_info.get('unique_id', '?')
        shared_with_result = file_info.get('shared_with', [])

        print(f"File '{basename}' written to FileDB as version {new_version}")
        print(f"Source: {source_path} ({len(content)} characters)")
        print(f"MD5 Hash: {hash_md5}")

        # Show sharing info if applicable
        if shared_with_result:
            print(f"Shared {basename} [{unique_id}] v{new_version} with users: {', '.join(map(str, shared_with_result))}")

    except Exception as e:
        print(f"Error writing file: {e}", file=sys.stderr)
        sys.exit(1)


def upload_file(client: AigonClient, basename: str, file_path: Optional[str] = None,
               namespace: str = "user/", share_with: Optional[List[int]] = None,
               reshare: bool = False, no_overwrite: bool = False) -> None:
    """Upload a file to FileDB (alias for write_file).

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        file_path: Path to local file to upload (default: basename.md)
        namespace: Namespace of the file
        share_with: List of user IDs to share with after upload
        reshare: If True, re-share with same users as previous version
        no_overwrite: If True, refuse upload if remote version is newer than local
    """
    # Just call write_file
    write_file(client, basename, file_path, namespace, share_with, reshare, no_overwrite)


def download_all_present(client: AigonClient, namespace: str = "user/", overwrite: bool = True) -> None:
    """Download all files that exist locally from FileDB.

    Only updates existing local .md files, does not create new files.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to download from
        overwrite: Whether to overwrite existing local files
    """
    try:
        # Find all local .md files
        local_files = list(Path(".").glob("*.md"))
        if not local_files:
            print("No .md files found in current directory")
            return

        local_basenames = {f.stem for f in local_files}

        # Get remote files
        system = (namespace == "system/")
        result = client.list_files(system=system)
        remote_files = {f['basename'] for f in result.get('files', [])}

        # Find intersection (files that exist both locally and remotely)
        to_download = local_basenames & remote_files

        if not to_download:
            print("No matching files found in FileDB")
            return

        print(f"Downloading {len(to_download)} files from FileDB...")

        success_count = 0
        error_count = 0

        for basename in sorted(to_download):
            try:
                result = client.read_file(basename=basename, system=system)
                if result.get('success'):
                    file_info = result.get('file_info', {})
                    content = file_info.get('content', '')
                    filedb_timestamp = file_info.get('created_at', None)

                    local_path = Path(f"{basename}.md")
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    if filedb_timestamp:
                        os.utime(local_path, (filedb_timestamp, filedb_timestamp))

                    print(f"✅ {basename}")
                    success_count += 1
                else:
                    print(f"❌ {basename}: {result.get('error', 'Unknown error')}")
                    error_count += 1
            except Exception as e:
                print(f"❌ {basename}: {e}")
                error_count += 1

        print(f"\nDownloaded: {success_count}, Errors: {error_count}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def upload_all_present(client: AigonClient, namespace: str = "user/") -> None:
    """Upload all local .md files that exist in FileDB.

    Only updates existing files in FileDB, does not create new files.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to upload to
    """
    try:
        # Find all local .md files
        local_files = list(Path(".").glob("*.md"))
        if not local_files:
            print("No .md files found in current directory")
            return

        local_basenames = {f.stem for f in local_files}

        # Get remote files
        system = (namespace == "system/")
        result = client.list_files(system=system)
        remote_files = {f['basename'] for f in result.get('files', [])}

        # Find intersection (files that exist both locally and remotely)
        to_upload = local_basenames & remote_files

        if not to_upload:
            print("No matching files found in FileDB")
            return

        print(f"Uploading {len(to_upload)} files to FileDB...")

        success_count = 0
        error_count = 0

        for basename in sorted(to_upload):
            try:
                local_path = Path(f"{basename}.md")
                with open(local_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                result = client.write_file(basename=basename, content=content, system=system)
                if result.get('success'):
                    print(f"✅ {basename}")
                    success_count += 1
                else:
                    print(f"❌ {basename}: {result.get('error', 'Unknown error')}")
                    error_count += 1
            except Exception as e:
                print(f"❌ {basename}: {e}")
                error_count += 1

        print(f"\nUploaded: {success_count}, Errors: {error_count}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def create_file(client: AigonClient, basename: str, namespace: str = "user/") -> None:
    """Create a new empty file in FileDB.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
    """
    # Block creation of "claude" files (reserved name)
    if basename.lower() == 'claude':
        print("Error: Cannot create file named 'claude' (reserved name)", file=sys.stderr)
        sys.exit(1)

    try:
        # Create the file
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.create_file(basename=basename, system=system)

        if not result.get('success'):
            print(f"Error creating file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        file_info = result.get('file_info', {})
        file_version = file_info.get('version', 'unknown')

        print(f"File '{basename}' created successfully as version {file_version}")

    except Exception as e:
        print(f"Error creating file: {e}", file=sys.stderr)
        sys.exit(1)


def delete_file(client: AigonClient, basename: str, namespace: str = "user/",
                sync_local: bool = False) -> None:
    """Delete a file from FileDB (soft delete).

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
        sync_local: If True, also delete local file
    """
    try:
        # Delete the file
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.delete_file(basename=basename, system=system)

        if not result.get('success'):
            print(f"Error deleting file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        print(f"File '{basename}' deleted successfully")
        message = result.get('message', '')
        if message:
            print(f"Details: {message}")

        # Handle local file sync
        if sync_local:
            local_file = f"{basename}.md"
            if os.path.exists(local_file):
                os.remove(local_file)
                print(f"Local file '{local_file}' deleted")
            else:
                print(f"Local file '{local_file}' not found (skipped)")

    except Exception as e:
        print(f"Error deleting file: {e}", file=sys.stderr)
        sys.exit(1)


def archive_file(client: AigonClient, basename: str, namespace: str = "user/",
                 sync_local: bool = False) -> None:
    """Archive a file in FileDB (set status to 'archived').

    Archived files are hidden from normal listings but preserved and can be restored.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
        sync_local: If True, move local file to .archived/ folder
    """
    try:
        # Archive the file
        system = (namespace == "system/")
        result = client.archive_file(basename=basename, system=system)

        if not result.get('success'):
            print(f"Error archiving file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        print(f"File '{basename}' archived successfully")
        message = result.get('message', '')
        if message:
            print(f"Details: {message}")

        # Handle local file sync
        if sync_local:
            local_file = f"{basename}.md"
            if os.path.exists(local_file):
                # Create .archived directory if it doesn't exist
                archive_dir = ".archived"
                os.makedirs(archive_dir, exist_ok=True)
                # Move file to archive
                archived_path = os.path.join(archive_dir, f"{basename}.md")
                shutil.move(local_file, archived_path)
                print(f"Local file moved to '{archived_path}'")
            else:
                print(f"Local file '{local_file}' not found (skipped)")

    except Exception as e:
        print(f"Error archiving file: {e}", file=sys.stderr)
        sys.exit(1)


def unarchive_file(client: AigonClient, basename: str, namespace: str = "user/",
                   sync_local: bool = False) -> None:
    """Restore an archived file to active status.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
        sync_local: If True, restore from .archived/ or download from FileDB
    """
    try:
        # Unarchive the file
        system = (namespace == "system/")
        result = client.unarchive_file(basename=basename, system=system)

        if not result.get('success'):
            print(f"Error unarchiving file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        print(f"File '{basename}' restored to active status")
        message = result.get('message', '')
        if message:
            print(f"Details: {message}")

        # Handle local file sync
        if sync_local:
            local_file = f"{basename}.md"
            archived_path = os.path.join(".archived", f"{basename}.md")

            if os.path.exists(archived_path):
                # Restore from local archive
                shutil.move(archived_path, local_file)
                print(f"Local file restored from '{archived_path}'")
            elif not os.path.exists(local_file):
                # Download from FileDB
                print(f"Downloading '{basename}' from FileDB...")
                download_file(client, basename=basename, namespace=namespace, overwrite=True)
            else:
                print(f"Local file '{local_file}' already exists")

    except Exception as e:
        print(f"Error unarchiving file: {e}", file=sys.stderr)
        sys.exit(1)


def undelete_file(client: AigonClient, basename: str, namespace: str = "user/",
                  sync_local: bool = False) -> None:
    """Restore a deleted file to active status.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
        sync_local: If True, download file from FileDB
    """
    try:
        # Undelete uses the same API as unarchive
        system = (namespace == "system/")
        result = client.unarchive_file(basename=basename, system=system)

        if not result.get('success'):
            print(f"Error undeleting file: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        print(f"File '{basename}' restored to active status")
        message = result.get('message', '')
        if message:
            print(f"Details: {message}")

        # Handle local file sync
        if sync_local:
            local_file = f"{basename}.md"
            if not os.path.exists(local_file):
                # Download from FileDB
                print(f"Downloading '{basename}' from FileDB...")
                download_file(client, basename=basename, namespace=namespace, overwrite=True)
            else:
                print(f"Local file '{local_file}' already exists")

    except Exception as e:
        print(f"Error undeleting file: {e}", file=sys.stderr)
        sys.exit(1)


def read_all_files(client: AigonClient, namespace: str = "user/", overwrite: bool = True, include_hidden: bool = False) -> None:
    """Read all files from FileDB namespace and save locally as .md files.

    By default, files starting with '_' are skipped and not downloaded.
    Use include_hidden=True to download all files including those starting with '_'.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to read files from
        overwrite: Whether to overwrite existing local files
        include_hidden: If True, include files starting with '_' (default: False)
    """
    try:
        # List all files in namespace
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.list_files(system=system)
        all_files = result.get('files', [])

        # Filter hidden files if not including them
        hidden_files = [f for f in all_files if f.get('basename', '').startswith('_')]
        if include_hidden:
            files = all_files
        else:
            files = [f for f in all_files if not f.get('basename', '').startswith('_')]

        if not files and not hidden_files:
            print(f"No files found in namespace '{namespace}'")
            return
        elif not files and hidden_files:
            print(f"No visible files found in namespace '{namespace}'")
            print(f"Note: {len(hidden_files)} files starting with '_' are hidden. Use --include-hidden to download all files.")
            return

        print(f"Found {len(files)} files in '{namespace}' to download")
        if not include_hidden and hidden_files:
            print(f"Note: {len(hidden_files)} files starting with '_' are hidden. Use --include-hidden to download all files.")
        print("-" * 60)

        success_count = 0
        error_count = 0
        backup_count = 0

        for file_info in files:
            basename = file_info.get('basename', 'unknown')
            version = file_info.get('version', 'unknown')

            try:
                print(f"Reading '{basename}' (v{version})...", end=" ")

                # Read from FileDB
                # Convert namespace to system parameter
                system = (namespace == "system/")
                read_result = client.read_file(basename=basename, system=system)

                if not read_result.get('success'):
                    print(f"ERROR: {read_result.get('error', 'Unknown error')}")
                    error_count += 1
                    continue

                # Extract content and metadata
                file_data = read_result.get('file_info', {})
                content = file_data.get('content', '')
                filedb_timestamp = file_data.get('created_at', None)

                local_filename = f"{basename}.md"
                local_path = Path(local_filename)

                # Check if file exists
                if local_path.exists():
                    if not overwrite:
                        print(f"SKIPPED (exists, use --overwrite)")
                        continue

                    # Create backup
                    backup_dir = Path(".backup")
                    backup_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_filename = f"{basename}_{timestamp}.md"
                    backup_path = backup_dir / backup_filename

                    shutil.copy2(local_path, backup_path)
                    backup_count += 1
                    print(f"backed up, ", end="")

                # Write to local file
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Set file timestamp to match FileDB timestamp
                if filedb_timestamp:
                    os.utime(local_path, (filedb_timestamp, filedb_timestamp))

                print(f"saved ({len(content)} chars)")
                success_count += 1

            except Exception as e:
                print(f"ERROR: {e}")
                error_count += 1

        # Print summary
        print("-" * 60)
        print(f"Summary: {success_count} files downloaded")
        if backup_count > 0:
            print(f"         {backup_count} files backed up to .backup/")
        if error_count > 0:
            print(f"         {error_count} errors occurred")

    except Exception as e:
        print(f"Error reading files: {e}", file=sys.stderr)
        sys.exit(1)


def update_all_files(client: AigonClient, namespace: str = "user/", overwrite: bool = True,
                    include_hidden: bool = False, auto_confirm: bool = False) -> None:
    """Update existing local files from FileDB, only downloading files with hash differences.

    By default, files starting with '_' are skipped and not checked.
    Use include_hidden=True to check all files including those starting with '_'.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to read files from
        overwrite: Whether to overwrite existing local files
        include_hidden: If True, include files starting with '_' (default: False)
        auto_confirm: If True, skip confirmation prompt (default: False)
    """
    try:
        # Find all local .md files
        local_files = list(Path(".").glob("*.md"))
        local_files = [f for f in local_files if '.backup' not in f.parts]

        # Filter hidden files if not including them
        hidden_local_files = [f for f in local_files if f.stem.startswith('_')]
        if include_hidden:
            local_files_to_check = local_files
        else:
            local_files_to_check = [f for f in local_files if not f.stem.startswith('_')]

        if not local_files_to_check:
            if not local_files and not hidden_local_files:
                print("No local .md files found")
            elif not local_files_to_check and hidden_local_files:
                print(f"No visible local .md files found")
                print(f"Note: {len(hidden_local_files)} files starting with '_' are hidden. Use --include-hidden to check all files.")
            return

        print(f"Found {len(local_files_to_check)} local files to check against FileDB '{namespace}'")
        if not include_hidden and hidden_local_files:
            print(f"Note: {len(hidden_local_files)} files starting with '_' are hidden. Use --include-hidden to check all files.")

        # Get all remote files with hashes
        system = (namespace == "system/")
        result = client.list_files(system=system)
        remote_files = {f['basename']: f for f in result.get('files', [])}

        print("Checking file hashes...")
        files_to_update = []
        files_current = []
        files_not_in_remote = []

        for file_path in local_files_to_check:
            basename = file_path.stem

            # Calculate local file hash
            try:
                with open(file_path, 'rb') as f:
                    content_bytes = f.read()
                    local_hash = hashlib.md5(content_bytes).hexdigest()
            except Exception as e:
                print(f"⚠️ Error reading local file {basename}: {e}")
                continue

            # Check if file exists in remote
            if basename not in remote_files:
                files_not_in_remote.append(basename)
                continue

            remote_file = remote_files[basename]
            remote_hash = remote_file.get('hash_MD5', '')

            if local_hash != remote_hash:
                files_to_update.append({
                    'basename': basename,
                    'local_hash': local_hash,
                    'remote_hash': remote_hash,
                    'version': remote_file.get('version', 'unknown')
                })
            else:
                files_current.append(basename)

        # Report results
        print(f"\nHash comparison results:")
        print(f"  ✅ Files already current: {len(files_current)}")
        print(f"  🔄 Files needing updates: {len(files_to_update)}")
        if files_not_in_remote:
            print(f"  ❌ Files not in FileDB: {len(files_not_in_remote)}")

        if not files_to_update:
            print("\nAll local files are already up to date!")
            return

        # Show files that need updating
        print(f"\nFiles needing updates (hash mismatch):")
        for file_info in files_to_update:
            basename = file_info['basename']
            local_hash_short = file_info['local_hash'][:16]
            remote_hash_short = file_info['remote_hash'][:16]
            version = file_info['version']
            print(f"  🔄 {basename} (local: {local_hash_short}..., remote: {remote_hash_short}... v{version})")

        if files_not_in_remote:
            print(f"\nFiles only in local (not in FileDB):")
            for basename in files_not_in_remote:
                print(f"  ❌ {basename}")

        # Confirmation prompt
        if not auto_confirm:
            response = input(f"\n{len(files_to_update)} files need updating. Continue? (y/N): ").strip().lower()
            if response not in ('y', 'yes'):
                print("Update cancelled.")
                return

        # Update files
        print(f"\nUpdating {len(files_to_update)} files...")
        print("-" * 60)

        success_count = 0
        error_count = 0
        backup_count = 0

        for file_info in files_to_update:
            basename = file_info['basename']

            try:
                print(f"Updating '{basename}'...", end=" ")

                # Read from FileDB
                read_result = client.read_file(basename=basename, system=system)

                if not read_result.get('success'):
                    print(f"ERROR: {read_result.get('error', 'Unknown error')}")
                    error_count += 1
                    continue

                # Extract content and metadata
                file_data = read_result.get('file_info', {})
                content = file_data.get('content', '')
                filedb_timestamp = file_data.get('created_at', None)

                local_filename = f"{basename}.md"
                local_path = Path(local_filename)

                # Create backup if file exists
                if local_path.exists():
                    if not overwrite:
                        print(f"SKIPPED (exists, use --overwrite)")
                        continue

                    backup_dir = Path(".backup")
                    backup_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_filename = f"{basename}_{timestamp}.md"
                    backup_path = backup_dir / backup_filename

                    shutil.copy2(local_path, backup_path)
                    backup_count += 1
                    print(f"backed up, ", end="")

                # Write to local file
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Set file timestamp to match FileDB timestamp
                if filedb_timestamp:
                    os.utime(local_path, (filedb_timestamp, filedb_timestamp))

                print(f"updated ({len(content)} chars)")
                success_count += 1

            except Exception as e:
                print(f"ERROR: {e}")
                error_count += 1

        # Print summary
        print("-" * 60)
        print(f"Summary: {success_count} files updated")
        if backup_count > 0:
            print(f"         {backup_count} files backed up to .backup/")
        if error_count > 0:
            print(f"         {error_count} errors occurred")
        if files_current:
            print(f"         {len(files_current)} files already current")

    except Exception as e:
        print(f"Error updating files: {e}", file=sys.stderr)
        sys.exit(1)


def write_all_files(client: AigonClient, namespace: str = "user/", pattern: str = "*.md",
                   include_hidden: bool = False, auto_confirm: bool = False) -> None:
    """Write all local .md files to FileDB, filtering hidden files by default.

    By default, local files starting with '_' are skipped and not uploaded.
    Use include_hidden=True to upload all files including those starting with '_'.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to write files to
        pattern: Glob pattern for files to upload (default: *.md)
        include_hidden: If True, include files starting with '_' (default: False)
    """
    try:
        # Find all matching files
        from pathlib import Path
        import glob

        all_files = list(Path(".").glob(pattern))

        # Filter out backup directory and hidden files
        all_files = [f for f in all_files if '.backup' not in f.parts]

        # Filter hidden files if not including them
        hidden_files = [f for f in all_files if f.stem.startswith('_')]
        if include_hidden:
            files = all_files
        else:
            files = [f for f in all_files if not f.stem.startswith('_')]

        if not files and not hidden_files:
            print(f"No files matching pattern '{pattern}' found")
            return
        elif not files and hidden_files:
            print(f"No visible files matching pattern '{pattern}' found")
            print(f"Note: {len(hidden_files)} files starting with '_' are hidden. Use --include-hidden to upload all files.")
            return

        print(f"Found {len(files)} files matching '{pattern}' to check for upload")
        if not include_hidden and hidden_files:
            print(f"Note: {len(hidden_files)} files starting with '_' are hidden. Use --include-hidden to upload all files.")

        # Get all remote files with hashes for comparison
        system = (namespace == "system/")
        result = client.list_files(system=system)
        remote_files = {f['basename']: f for f in result.get('files', [])}

        print("Checking file hashes...")
        files_to_upload = []
        files_current = []
        new_files = []

        for file_path in files:
            basename = file_path.stem

            # Calculate local file hash
            try:
                with open(file_path, 'rb') as f:
                    content_bytes = f.read()
                    local_hash = hashlib.md5(content_bytes).hexdigest()
            except Exception as e:
                print(f"⚠️ Error reading local file {basename}: {e}")
                continue

            # Check if file exists in remote and compare hashes
            if basename not in remote_files:
                new_files.append(file_path)
                continue

            remote_file = remote_files[basename]
            remote_hash = remote_file.get('hash_MD5', '')

            if local_hash != remote_hash:
                files_to_upload.append(file_path)
            else:
                files_current.append(basename)

        # Report results
        total_to_upload = len(files_to_upload) + len(new_files)
        print(f"\nHash comparison results:")
        print(f"  ✅ Files already current: {len(files_current)}")
        print(f"  🔄 Files needing updates: {len(files_to_upload)}")
        print(f"  ➕ New files to upload: {len(new_files)}")

        if not total_to_upload:
            print("\nAll local files are already up to date in FileDB!")
            return

        # Show files that need uploading
        if files_to_upload:
            print(f"\nFiles needing updates (hash mismatch):")
            for file_path in files_to_upload:
                basename = file_path.stem
                print(f"  🔄 {basename}")

        if new_files:
            print(f"\nNew files to upload:")
            for file_path in new_files:
                basename = file_path.stem
                print(f"  ➕ {basename}")

        # Confirmation prompt
        if not auto_confirm:
            response = input(f"\n{total_to_upload} files need uploading. Continue? (y/N): ").strip().lower()
            if response not in ('y', 'yes'):
                print("Upload cancelled.")
                return

        # Upload only the files that need it
        all_files_to_upload = files_to_upload + new_files
        print(f"\nUploading {len(all_files_to_upload)} files...")
        print("-" * 60)

        success_count = 0
        error_count = 0

        for file_path in all_files_to_upload:
            basename = file_path.stem  # Get filename without extension

            try:
                print(f"Writing '{basename}'...", end=" ")

                # Read local file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Write to FileDB
                # Convert namespace to system parameter
                system = (namespace == "system/")
                result = client.write_file(basename=basename, content=content, system=system)

                if not result.get('success'):
                    print(f"ERROR: {result.get('error', 'Unknown error')}")
                    error_count += 1
                    continue

                file_info = result.get('file_info', {})
                new_version = file_info.get('version', 'unknown')

                print(f"saved as v{new_version} ({len(content)} chars)")
                success_count += 1

            except Exception as e:
                print(f"ERROR: {e}")
                error_count += 1

        # Print summary
        print("-" * 60)
        print(f"Summary: {success_count} files uploaded")
        if error_count > 0:
            print(f"         {error_count} errors occurred")
        if files_current:
            print(f"         {len(files_current)} files already current")

    except Exception as e:
        print(f"Error writing files: {e}", file=sys.stderr)
        sys.exit(1)


def check_file(client: AigonClient, basename: str, namespace: str = "user/") -> dict:
    """Check if local file matches FileDB version.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file

    Returns:
        Dictionary with comparison results
    """
    try:
        local_filename = f"{basename}.md"
        local_path = Path(local_filename)

        if not local_path.exists():
            return {
                'basename': basename,
                'status': 'LOCAL_MISSING',
                'message': f"Local file '{local_filename}' not found"
            }

        # Get local file info
        with open(local_path, 'rb') as f:
            content_bytes = f.read()
            local_hash = hashlib.md5(content_bytes).hexdigest()
            local_length = len(content_bytes)

        local_stats = local_path.stat()
        local_mtime = int(local_stats.st_mtime)

        # Get remote file info
        try:
            # Convert namespace to system parameter
            system = (namespace == "system/")
            result = client.list_files(system=system)
            files = result.get('files', [])

            remote_file = None
            for f in files:
                if f.get('basename') == basename:
                    remote_file = f
                    break

            if not remote_file:
                return {
                    'basename': basename,
                    'status': 'REMOTE_MISSING',
                    'message': f"File '{basename}' not found in FileDB"
                }

            remote_hash = remote_file.get('hash_MD5', '')
            remote_length = remote_file.get('content_length', -1)
            remote_timestamp = remote_file.get('created_at', 0)

            # Helper function to format time difference
            def format_time_diff(seconds):
                if seconds < 60:
                    return f"{seconds}s"
                elif seconds < 3600:
                    return f"{seconds//60}m"
                elif seconds < 86400:
                    return f"{seconds//3600}h"
                else:
                    return f"{seconds//86400}d"

            # Helper function to determine which is newer
            def get_newer_info(local_time, remote_time):
                time_diff = abs(local_time - remote_time)
                if local_time > remote_time:
                    return f"local newer by {format_time_diff(time_diff)}"
                elif remote_time > local_time:
                    return f"remote newer by {format_time_diff(time_diff)}"
                else:
                    return "same timestamp"

            # Compare files
            if local_hash == remote_hash:
                return {
                    'basename': basename,
                    'status': 'MATCH',
                    'message': "Files match (identical hash)",
                    'local_hash': local_hash,
                    'remote_hash': remote_hash
                }

            # Check for likely match (fuzzy matching)
            time_diff = abs(local_mtime - remote_timestamp)
            time_threshold = 3600  # 1 hour tolerance
            newer_info = get_newer_info(local_mtime, remote_timestamp)

            if local_length == remote_length:
                if time_diff < time_threshold:
                    return {
                        'basename': basename,
                        'status': 'LIKELY_MATCH',
                        'message': f"Files likely match (same length, {newer_info})",
                        'local_hash': local_hash,
                        'remote_hash': remote_hash,
                        'length': local_length
                    }
                else:
                    return {
                        'basename': basename,
                        'status': 'POSSIBLE_MATCH',
                        'message': f"Files may match (same length, {newer_info})",
                        'local_hash': local_hash,
                        'remote_hash': remote_hash,
                        'length': local_length
                    }

            # Files differ
            return {
                'basename': basename,
                'status': 'DIFFER',
                'message': f"Files differ (length: {local_length} vs {remote_length}, {newer_info})",
                'local_hash': local_hash,
                'remote_hash': remote_hash,
                'local_length': local_length,
                'remote_length': remote_length
            }

        except Exception as e:
            return {
                'basename': basename,
                'status': 'ERROR',
                'message': f"Error checking remote file: {e}"
            }

    except Exception as e:
        return {
            'basename': basename,
            'status': 'ERROR',
            'message': f"Error checking file: {e}"
        }


def check_single_file(client: AigonClient, basename: str, namespace: str = "user/") -> None:
    """Check and display comparison for a single file.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
    """
    result = check_file(client, basename, namespace)

    status = result['status']
    message = result['message']

    # Emoji output based on status
    if status == 'MATCH':
        print(f"✅ {basename}: {message}")
    elif status == 'LIKELY_MATCH':
        print(f"🟡 {basename}: {message}")
    elif status == 'POSSIBLE_MATCH':
        print(f"🟠 {basename}: {message}")
    elif status == 'LOCAL_MISSING':
        print(f"❌ {basename}: {message}")
    elif status == 'REMOTE_MISSING':
        print(f"➕ {basename}: {message}")
    elif status == 'DIFFER':
        print(f"🔴 {basename}: {message}")
    else:
        print(f"⚠️ {basename}: {message}")

    # Show additional details for non-matches
    if status not in ['MATCH', 'LOCAL_MISSING', 'REMOTE_MISSING']:
        if 'local_hash' in result:
            print(f"  Local:  {result['local_hash'][:16]}...")
        if 'remote_hash' in result:
            print(f"  Remote: {result['remote_hash'][:16]}...")


def check_all_files(client: AigonClient, namespace: str = "user/", ignore_private: bool = False, only_present: bool = False) -> None:
    """Check all local .md files against FileDB versions.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to check against
        ignore_private: If True, ignore files starting with '_' or '-' (default: False)
        only_present: If True, only check files that exist locally (default: False)
    """
    try:
        # Find all local .md files
        all_local_files = list(Path(".").glob("*.md"))

        # Filter private files if requested
        if ignore_private:
            local_files = [f for f in all_local_files if not (f.stem.startswith('_') or f.stem.startswith('-'))]
            private_files_filtered = len(all_local_files) - len(local_files)
        else:
            local_files = all_local_files
            private_files_filtered = 0

        # Get all remote files ONCE
        # Convert namespace to system parameter
        system = (namespace == "system/")
        result = client.list_files(system=system)
        remote_files = {f['basename']: f for f in result.get('files', [])}

        print(f"Checking {len(local_files)} local files against FileDB '{namespace}'")
        if ignore_private and private_files_filtered > 0:
            print(f"Note: {private_files_filtered} private files (starting with '_' or '-') ignored")
        if only_present:
            print("Note: Only checking files that exist locally (--only-present)")
        print("-" * 60)

        stats = {
            'MATCH': 0,
            'LIKELY_MATCH': 0,
            'POSSIBLE_MATCH': 0,
            'DIFFER': 0,
            'LOCAL_MISSING': 0,
            'REMOTE_MISSING': 0,
            'ERROR': 0
        }

        # Helper functions (duplicated here for efficiency)
        def format_time_diff(seconds):
            if seconds < 60:
                return f"{seconds}s"
            elif seconds < 3600:
                return f"{seconds//60}m"
            elif seconds < 86400:
                return f"{seconds//3600}h"
            else:
                return f"{seconds//86400}d"

        def get_newer_info(local_time, remote_time):
            time_diff = abs(local_time - remote_time)
            if local_time > remote_time:
                return f"local newer by {format_time_diff(time_diff)}"
            elif remote_time > local_time:
                return f"remote newer by {format_time_diff(time_diff)}"
            else:
                return "same timestamp"

        # Check each local file
        for file_path in local_files:
            basename = file_path.stem

            try:
                # Get local file info
                with open(file_path, 'rb') as f:
                    content_bytes = f.read()
                    local_hash = hashlib.md5(content_bytes).hexdigest()
                    local_length = len(content_bytes)

                local_stats = file_path.stat()
                local_mtime = int(local_stats.st_mtime)

                # Check if remote file exists
                if basename not in remote_files:
                    stats['REMOTE_MISSING'] += 1
                    print(f"➕ {basename:<30} File '{basename}' not found in FileDB")
                    continue

                remote_file = remote_files[basename]
                remote_hash = remote_file.get('hash_MD5', '')
                remote_length = remote_file.get('content_length', -1)
                remote_timestamp = remote_file.get('created_at', 0)

                # Compare files
                if local_hash == remote_hash:
                    stats['MATCH'] += 1
                    print(f"✅ {basename:<30} Files match (identical hash)")
                    continue

                # Check for likely match (fuzzy matching)
                time_diff = abs(local_mtime - remote_timestamp)
                time_threshold = 3600  # 1 hour tolerance
                newer_info = get_newer_info(local_mtime, remote_timestamp)

                if local_length == remote_length:
                    if time_diff < time_threshold:
                        stats['LIKELY_MATCH'] += 1
                        print(f"🟡 {basename:<30} Files likely match (same length, {newer_info})")
                    else:
                        stats['POSSIBLE_MATCH'] += 1
                        print(f"🟠 {basename:<30} Files may match (same length, {newer_info})")
                else:
                    stats['DIFFER'] += 1
                    print(f"🔴 {basename:<30} Files differ (length: {local_length} vs {remote_length}, {newer_info})")

            except Exception as e:
                stats['ERROR'] += 1
                print(f"⚠️ {basename:<30} Error checking file: {e}")

        # Check for remote files not present locally (unless --only-present is used)
        if not only_present:
            for remote_basename in remote_files:
                local_path = Path(f"{remote_basename}.md")
                if not local_path.exists():
                    # Apply private file filtering to remote files too
                    if ignore_private and (remote_basename.startswith('_') or remote_basename.startswith('-')):
                        continue
                    stats['LOCAL_MISSING'] += 1
                    print(f"❌ {remote_basename:<30} Only in FileDB (not local)")

        # Print summary
        print("-" * 60)
        print("Summary:")
        print(f"  ✅ Matches:        {stats['MATCH']}")
        if stats['LIKELY_MATCH'] > 0:
            print(f"  🟡 Likely matches: {stats['LIKELY_MATCH']}")
        if stats['POSSIBLE_MATCH'] > 0:
            print(f"  🟠 Possible match: {stats['POSSIBLE_MATCH']}")
        if stats['DIFFER'] > 0:
            print(f"  🔴 Different:      {stats['DIFFER']}")
        if stats['REMOTE_MISSING'] > 0:
            print(f"  ➕ Local only:     {stats['REMOTE_MISSING']}")
        if stats['LOCAL_MISSING'] > 0:
            print(f"  ❌ Remote only:    {stats['LOCAL_MISSING']}")
        if stats['ERROR'] > 0:
            print(f"  ⚠️ Errors:         {stats['ERROR']}")

    except Exception as e:
        print(f"Error checking files: {e}", file=sys.stderr)
        sys.exit(1)


def hash_file(basename: str) -> None:
    """Calculate MD5 hash, timestamp, and length of a local file.

    Args:
        basename: Base filename without extension (will look for basename.md)
    """
    try:
        # Determine local file path
        local_filename = f"{basename}.md"
        local_path = Path(local_filename)

        if not local_path.exists():
            print(f"Local file '{local_filename}' not found.", file=sys.stderr)
            sys.exit(1)

        # Calculate MD5 hash
        md5_hash = hashlib.md5()
        with open(local_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)

        # Get file stats
        file_stats = local_path.stat()
        file_size = file_stats.st_size
        modified_time_local = datetime.fromtimestamp(file_stats.st_mtime)
        modified_time_utc = datetime.utcfromtimestamp(file_stats.st_mtime)

        # Print results
        print(f"File: {local_filename}")
        print(f"MD5 Hash: {md5_hash.hexdigest()}")
        print(f"Size: {file_size} bytes")
        print(f"Unix Timestamp: {int(file_stats.st_mtime)}")
        print(f"Modified (UTC): {modified_time_utc.strftime('%Y-%m-%d %H:%M:%S')} Z")
        print(f"Modified (Local): {modified_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    except Exception as e:
        print(f"Error calculating hash: {e}", file=sys.stderr)
        sys.exit(1)


def init_workspace(client: AigonClient, force: bool = False) -> None:
    """Initialize empty directory with .claude structure and system commands.

    Args:
        client: Authenticated Aigon client
        force: Force initialization even if directory is not empty
    """
    try:
        current_dir = Path(".")

        # Check if directory is empty (unless force is used)
        if not force:
            # Check for any files or directories (excluding hidden files starting with .)
            existing_items = [item for item in current_dir.iterdir()
                            if not item.name.startswith('.')]
            if existing_items:
                print("ERROR: Directory is not empty. Use --force to initialize anyway.", file=sys.stderr)
                print(f"Found {len(existing_items)} items:", file=sys.stderr)
                for item in existing_items[:5]:  # Show first 5 items
                    print(f"  - {item.name}", file=sys.stderr)
                if len(existing_items) > 5:
                    print(f"  ... and {len(existing_items) - 5} more", file=sys.stderr)
                sys.exit(1)

        # Create .claude directory structure
        claude_dir = Path(".claude")
        commands_dir = claude_dir / "commands"

        # Remove existing .claude directory if it exists
        if claude_dir.exists():
            print("Removing existing .claude directory...")
            shutil.rmtree(claude_dir)

        # Create fresh directories
        print("Creating .claude/commands directory structure...")
        commands_dir.mkdir(parents=True, exist_ok=True)

        # Get system files
        print("Fetching system files...")
        result = client.list_files(system=True)
        system_files = result.get('files', [])

        # Filter command files (files starting with "command-" or "command_")
        command_files = [f for f in system_files if f.get('basename', '').startswith(('command-', 'command_'))]

        if not command_files:
            print("No command files found in system namespace")
        else:
            print(f"Found {len(command_files)} command files in system namespace")
            print("-" * 60)

            success_count = 0
            error_count = 0

            for file_info in command_files:
                basename = file_info.get('basename', '')
                version = file_info.get('version', 'unknown')

                # Transform filename: command-X or command_X -> X (replacing all - with _)
                if basename.startswith('command-'):
                    new_basename = basename[8:]  # Remove "command-" prefix
                    new_basename = new_basename.replace('-', '_')  # Replace - with _
                elif basename.startswith('command_'):
                    new_basename = basename[8:]  # Remove "command_" prefix
                    new_basename = new_basename.replace('-', '_')  # Replace - with _
                else:
                    continue  # Skip if doesn't start with command- or command_

                try:
                    print(f"Downloading '{basename}' -> '{new_basename}'...", end=" ")

                    # Read from system FileDB
                    read_result = client.read_file(basename=basename, system=True)

                    if not read_result.get('success'):
                        print(f"ERROR: {read_result.get('error', 'Unknown error')}")
                        error_count += 1
                        continue

                    # Extract content
                    file_data = read_result.get('file_info', {})
                    content = file_data.get('content', '')
                    filedb_timestamp = file_data.get('created_at', None)

                    # Write to .claude/commands directory
                    local_path = commands_dir / f"{new_basename}.md"
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    # Set file timestamp to match FileDB timestamp
                    if filedb_timestamp:
                        os.utime(local_path, (filedb_timestamp, filedb_timestamp))

                    print(f"saved ({len(content)} chars)")
                    success_count += 1

                except Exception as e:
                    print(f"ERROR: {e}")
                    error_count += 1

            print("-" * 60)
            print(f"Commands downloaded: {success_count}")
            if error_count > 0:
                print(f"Errors: {error_count}")

        # Check for special config file and create _conflict.toml
        print("\nChecking for special configuration file...")
        try:
            config_result = client.read_file(basename="-filedb-config-toml", system=False)
            if config_result.get('success'):
                file_data = config_result.get('file_info', {})
                content = file_data.get('content', '')

                # Extract content between triple quotes
                import re
                triple_quote_pattern = r'```(.*?)```'
                matches = re.findall(triple_quote_pattern, content, re.DOTALL)

                if matches:
                    toml_content = matches[0].strip()

                    # Save as _conflict.toml
                    conflict_path = Path("_conflict.toml")
                    with open(conflict_path, 'w', encoding='utf-8') as f:
                        f.write(toml_content)

                    print(f"✅ Created _conflict.toml from config file ({len(toml_content)} chars)")
                else:
                    print("⚠️ Config file found but no content between triple quotes")
            else:
                print("No special config file found (this is normal)")
        except Exception as e:
            print(f"Note: Could not process config file: {e}")

        # Now run readall for user workspace
        print("\nDownloading user workspace files...")
        read_all_files(client, namespace="user/", overwrite=True, include_hidden=True)  # Include hidden files for init

        print(f"\n✅ Workspace initialized successfully!")
        print(f"Structure created:")
        print(f"  .claude/commands/ - System command files")
        print(f"  *.md files - User workspace files")
        if Path("_conflict.toml").exists():
            print(f"  _conflict.toml - Special configuration file")

    except Exception as e:
        print(f"Error initializing workspace: {e}", file=sys.stderr)
        sys.exit(1)


def search_files(client: AigonClient,
                    query: str,
                    filename: Optional[str] = None,
                    include_current: bool = True,
                    include_archived: bool = False,
                    include_deleted: bool = False,
                    include_all_versions: bool = False,
                    limit: int = 10,
                    max_content_length: int = -1,
                    namespace: str = "user/",
                    output_format: str = "llm",
                    directory: Optional[str] = None) -> None:
    """Search through FileDB files by content and/or filename with flexible constraints.

    Args:
        client: Authenticated Aigon client
        query: Search query string for content matching
        filename: Optional filename pattern with wildcards (*, ?)
        include_current: Include active files in results
        include_archived: Include archived files in results
        include_deleted: Include deleted files in results
        include_all_versions: Include all versions, not just latest
        limit: Maximum number of results to return
        max_content_length: Maximum content length to return (-1 = no limit)
        namespace: Namespace to search (user/ or system/)
        output_format: Output format (llm, json, table, files)
        directory: Directory to save files (default: _filedb_search)
    """
    try:
        # Convert namespace to system parameter
        system = (namespace == "system/")

        result = client.search_files(
            query=query,
            filename=filename,
            include_current=include_current,
            include_archived=include_archived,
            include_deleted=include_deleted,
            include_all_versions=include_all_versions,
            limit=limit,
            max_content_length=max_content_length,
            system=system
        )

        if not result.get('success'):
            print(f"Error searching files: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

        if output_format == "llm":
            # LLM format: concise list of matching files with brief preview
            matches = result.get('matches_found', [])
            if not matches:
                print(f"No files found matching '{query}'")
                return
            total = result.get('total_matches', len(matches))
            print(f"{len(matches)} match(es) for '{query}':")
            for f in matches:
                name = f.get('basename', 'unknown')
                version = f.get('version', '?')
                # Show first 60 chars of content as preview
                content = f.get('content', '')[:60].replace('\n', ' ')
                if len(f.get('content', '')) > 60:
                    content += "..."
                print(f"  {name} (v{version}): {content}")
        elif output_format == "json":
            print(json.dumps(result, indent=2))
        elif output_format == "table":
            matches = result.get('matches_found', [])
            if not matches:
                print(f"No files found matching '{query}'")
                return

            total_matches = result.get('total_matches', len(matches))
            showing = result.get('showing', len(matches))

            # Build search description
            search_desc = f"'{query}'"
            if filename:
                search_desc += f" with filename pattern '{filename}'"

            print(f"Search results for {search_desc} in '{namespace}' ({showing} of {total_matches} matches):")
            print("-" * 80)

            for i, file_info in enumerate(matches, 1):
                basename = file_info.get('basename', 'unknown')
                version = file_info.get('version', 'unknown')
                content_preview = file_info.get('content', '')[:100]
                updated = file_info.get('updated_at', 'unknown')
                file_status = file_info.get('status', 'current')

                # Show content preview with line breaks removed
                content_preview = content_preview.replace('\n', ' ').replace('\r', ' ')
                if len(file_info.get('content', '')) > 100:
                    content_preview += "..."

                print(f"{i}. {basename} (v{version}) [{file_status}]")
                print(f"   {content_preview}")
                print(f"   Updated: {updated}")
                print()

        elif output_format == "files":
            # Save search results as individual files
            if directory is None:
                directory = "_filedb_search"

            # Create directory if it doesn't exist
            os.makedirs(directory, exist_ok=True)

            matches = result.get('matches_found', [])
            if not matches:
                print(f"No files found matching '{query}' to save")
                return

            saved_files = []
            for file_info in matches:
                basename = file_info.get('basename', 'unknown')
                version = file_info.get('version', 'unknown')
                content = file_info.get('content', '')

                # Generate filename
                output_filename = f"{basename}_v{version}.md"
                filepath = os.path.join(directory, output_filename)

                # Prepare content with metadata
                metadata = f"# FileDB Search Result: {basename}\n\n"
                metadata += f"- **Query**: {query}\n"
                if filename:
                    metadata += f"- **Filename Pattern**: {filename}\n"
                metadata += f"- **Version**: {version}\n"
                metadata += f"- **Status**: {file_info.get('status', 'current')}\n"
                metadata += f"- **Updated**: {file_info.get('updated_at', 'unknown')}\n"
                metadata += f"- **Namespace**: {namespace}\n\n"
                metadata += "---\n\n"

                full_content = metadata + content

                # Write file
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(full_content)

                saved_files.append(filepath)

            print(f"Saved {len(saved_files)} search results for '{query}' to {directory}/:")
            for filepath in saved_files:
                print(f"  - {os.path.basename(filepath)}")
        else:
            print(f"Unknown output format: {output_format}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error searching files: {e}", file=sys.stderr)
        sys.exit(1)


def share_file_cmd(client: AigonClient, basename: str, user_ids: list,
                   namespace: str = "user/") -> None:
    """Share file with specified users (always shares latest version).

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        user_ids: List of user IDs to share with
        namespace: Namespace of the file
    """
    try:
        system = (namespace == "system/")
        result = client.share_file(basename, user_ids, version=None, system=system)

        if result.get('success'):
            inner = result.get('result', {})
            unique_id = inner.get('unique_id', '?')
            version = inner.get('version', '?')
            shared_with = inner.get('shared_with', [])
            users_added = inner.get('users_added', [])
            print(f"Shared {basename} [{unique_id}] v{version} with users: {', '.join(map(str, users_added))}")
            if len(shared_with) > len(users_added):
                print(f"  Total shared with: {', '.join(map(str, shared_with))}")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error sharing file: {e}", file=sys.stderr)
        sys.exit(1)


def unshare_file_cmd(client: AigonClient, basename: str, namespace: str = "user/") -> None:
    """Remove all sharing from all versions of file.

    Args:
        client: Authenticated Aigon client
        basename: Base filename without extension
        namespace: Namespace of the file
    """
    try:
        system = (namespace == "system/")
        result = client.unshare_file(basename, system=system)

        if result.get('success'):
            inner = result.get('result', {})
            versions_updated = inner.get('versions_updated', 0)
            print(f"Removed all sharing from {basename} ({versions_updated} version(s) updated)")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error unsharing file: {e}", file=sys.stderr)
        sys.exit(1)


def list_shared_files_cmd(client: AigonClient, output_format: str = "llm") -> None:
    """List files shared with current user (by others).

    Args:
        client: Authenticated Aigon client
        output_format: Output format (llm, json, table)
    """
    try:
        result = client.list_shared_files()
        files = result.get('files', [])

        if output_format == "llm":
            if not files:
                print("No files shared with you")
                return
            print(f"{len(files)} shared file(s):")
            for f in files:
                owner = f.get('owner_user_id', '?')
                name = f.get('basename', 'unknown')
                version = f.get('version', '?')
                unique_id = f.get('unique_id', '')[:6]
                print(f"  {name} v{version} ({unique_id}) from user {owner}")
        elif output_format == "json":
            print(json.dumps(result, indent=2))
        elif output_format == "table":
            if not files:
                print("No files shared with you")
                return
            print(f"{'BASENAME':<20} {'VERSION':<8} {'UNIQUE_ID':<12} {'OWNER'}")
            print("-" * 60)
            for f in files:
                name = f.get('basename', 'unknown')
                version = f.get('version', '?')
                unique_id = f.get('unique_id', '')[:10]
                owner = f.get('owner_user_id', '?')
                print(f"{name:<20} v{version:<7} {unique_id:<12} {owner}")
        else:
            print(f"Unknown output format: {output_format}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error listing shared files: {e}", file=sys.stderr)
        sys.exit(1)


def list_files_i_shared_cmd(client: AigonClient, namespace: str = "user/",
                             output_format: str = "llm") -> None:
    """List files that current user has shared with others.

    Args:
        client: Authenticated Aigon client
        namespace: Namespace to list from
        output_format: Output format (llm, json, table)
    """
    try:
        system = (namespace == "system/")
        result = client.list_files_i_shared(system=system)
        files = result.get('files', [])

        if output_format == "llm":
            if not files:
                print("You haven't shared any files")
                return
            print(f"{len(files)} file(s) you've shared:")
            for f in files:
                name = f.get('basename', 'unknown')
                current_version = f.get('current_version', '?')
                shared_versions = f.get('shared_versions', [])

                # Show each shared version
                for sv in shared_versions:
                    v = sv.get('version', '?')
                    users = sv.get('shared_with', [])
                    marker = " (current)" if v == current_version else ""
                    print(f"  {name} v{v}{marker} → {len(users)} user(s): {', '.join(map(str, users))}")
        elif output_format == "json":
            print(json.dumps(result, indent=2))
        elif output_format == "table":
            if not files:
                print("You haven't shared any files")
                return
            print(f"{'BASENAME':<20} {'VERSION':<10} {'CURRENT':<8} {'SHARED WITH'}")
            print("-" * 70)
            for f in files:
                name = f.get('basename', 'unknown')
                current_version = f.get('current_version', '?')
                for sv in f.get('shared_versions', []):
                    v = sv.get('version', '?')
                    users = sv.get('shared_with', [])
                    is_current = "yes" if v == current_version else ""
                    print(f"{name:<20} v{v:<9} {is_current:<8} {', '.join(map(str, users))}")
        else:
            print(f"Unknown output format: {output_format}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error listing shared files: {e}", file=sys.stderr)
        sys.exit(1)


def register_filedb_commands(subparsers):
    """Register FileDB commands with argument parser.

    Args:
        subparsers: argparse subparsers object
    """
    # FileDB command group
    filedb_parser = subparsers.add_parser('filedb', help='FileDB operations')
    filedb_subparsers = filedb_parser.add_subparsers(dest='filedb_command', help='FileDB commands')

    # List command
    list_parser = filedb_subparsers.add_parser('list', help='List files in namespace')
    list_parser.add_argument('--namespace', default='user/', help='Namespace to list (default: user/)')
    list_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    list_parser.add_argument('--format', choices=['llm', 'json', 'table'], default='llm',
                        help='Output format (default: llm for concise output)')
    list_parser.add_argument('--include-hidden', action='store_true', dest='include_hidden',
                        help='Include files starting with "_" (hidden by default)')

    # Read command (to stdout)
    read_parser = filedb_subparsers.add_parser('read', help='Read file content to stdout')
    read_parser.add_argument('basename', help='Base filename without extension')
    read_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    read_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    read_parser.add_argument('--version', type=int, help='Specific version to read')

    # Download command (save to file)
    download_parser = filedb_subparsers.add_parser('download', help='Download file from FileDB and save locally')
    download_parser.add_argument('basename', nargs='?', help='Base filename without extension')
    download_parser.add_argument('--all', action='store_true', dest='download_all',
                        help='Download all files that exist locally (update existing .md files only)')
    download_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    download_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    download_parser.add_argument('--version', type=int, help='Specific version to download')
    download_parser.add_argument('--no-overwrite', dest='overwrite', action='store_false', default=True,
                        help='Do not overwrite existing local file')

    # Create command
    create_parser = filedb_subparsers.add_parser('create', help='Create a new empty file in FileDB')
    create_parser.add_argument('basename', help='Base filename without extension')
    create_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    create_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')

    # Upload command
    upload_parser = filedb_subparsers.add_parser('upload', help='Upload file to FileDB')
    upload_parser.add_argument('basename', nargs='?', help='Base filename without extension')
    upload_parser.add_argument('--all', action='store_true', dest='upload_all',
                        help='Upload all local .md files that exist in FileDB (update only, no create)')
    upload_parser.add_argument('--path', help='Path to source file (default: basename.md)')
    upload_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    upload_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    upload_parser.add_argument('--share', nargs='+', type=int, metavar='USER_ID',
                        help='Share with these user IDs after upload')
    upload_parser.add_argument('--reshare', action='store_true',
                        help='Re-share with same users as previous version')
    upload_parser.add_argument('--no-overwrite', action='store_true',
                        help='Refuse upload if remote version is newer than local')

    # Delete command
    delete_parser = filedb_subparsers.add_parser('delete', help='Soft delete a file from FileDB (recoverable)')
    delete_parser.add_argument('basename', help='Base filename without extension')
    delete_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    delete_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    delete_parser.add_argument('--sync-local', action='store_true', dest='sync_local',
                            help='Also delete local file')
    delete_parser.add_argument('--no-sync-local', action='store_false', dest='sync_local',
                            help='Do not touch local file (default)')

    # Archive command
    archive_parser = filedb_subparsers.add_parser('archive', help='Archive a file (hidden but preserved)')
    archive_parser.add_argument('basename', help='Base filename without extension')
    archive_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    archive_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    archive_parser.add_argument('--sync-local', action='store_true', dest='sync_local',
                            help='Move local file to .archived/ folder')
    archive_parser.add_argument('--no-sync-local', action='store_false', dest='sync_local',
                            help='Do not touch local file (default)')

    # Unarchive command
    unarchive_parser = filedb_subparsers.add_parser('unarchive', help='Restore archived file to active status')
    unarchive_parser.add_argument('basename', help='Base filename without extension')
    unarchive_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    unarchive_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    unarchive_parser.add_argument('--sync-local', action='store_true', dest='sync_local',
                            help='Restore from .archived/ or download from FileDB')
    unarchive_parser.add_argument('--no-sync-local', action='store_false', dest='sync_local',
                            help='Do not touch local file (default)')

    # Undelete command
    undelete_parser = filedb_subparsers.add_parser('undelete', help='Restore deleted file to active status')
    undelete_parser.add_argument('basename', help='Base filename without extension')
    undelete_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    undelete_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    undelete_parser.add_argument('--sync-local', action='store_true', dest='sync_local',
                            help='Download file from FileDB')
    undelete_parser.add_argument('--no-sync-local', action='store_false', dest='sync_local',
                            help='Do not touch local file (default)')

    # Hash command
    hash_parser = filedb_subparsers.add_parser('hash', help='Calculate MD5 hash, timestamp, and size of local file')
    hash_parser.add_argument('basename', help='Base filename without extension (will look for basename.md)')

    # Readall command
    readall_parser = filedb_subparsers.add_parser('readall', help='Read all files from namespace and save locally')
    readall_parser.add_argument('--namespace', default='user/', help='Namespace to read from (default: user/)')
    readall_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    readall_parser.add_argument('--no-overwrite', dest='overwrite', action='store_false', default=True,
                            help='Do not overwrite existing local files')
    readall_parser.add_argument('--include-hidden', action='store_true', dest='include_hidden',
                            help='Include files starting with "_" (hidden by default)')

    # Writeall command
    writeall_parser = filedb_subparsers.add_parser('writeall', help='Write all local .md files to FileDB with hash-based selection')
    writeall_parser.add_argument('--namespace', default='user/', help='Namespace to write to (default: user/)')
    writeall_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    writeall_parser.add_argument('--pattern', default='*.md', help='Glob pattern for files to upload (default: *.md)')
    writeall_parser.add_argument('--include-hidden', action='store_true', dest='include_hidden',
                            help='Include files starting with "_" (hidden by default)')
    writeall_parser.add_argument('--yes', action='store_true', dest='auto_confirm',
                            help='Skip confirmation prompt and proceed automatically')

    # Updateall command
    updateall_parser = filedb_subparsers.add_parser('updateall', help='Update existing local files from FileDB (hash-based selection)')
    updateall_parser.add_argument('--namespace', default='user/', help='Namespace to read from (default: user/)')
    updateall_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    updateall_parser.add_argument('--no-overwrite', dest='overwrite', action='store_false', default=True,
                            help='Do not overwrite existing local files')
    updateall_parser.add_argument('--include-hidden', action='store_true', dest='include_hidden',
                            help='Include files starting with "_" (hidden by default)')
    updateall_parser.add_argument('--yes', action='store_true', dest='auto_confirm',
                            help='Skip confirmation prompt and proceed automatically')

    # Check command
    check_parser = filedb_subparsers.add_parser('check', help='Check if local file(s) match FileDB version. No args = all .md files')
    check_parser.add_argument('basenames', nargs='*', help='Base filename(s) without extension. If none provided, checks all .md files in current directory')
    check_parser.add_argument('--namespace', default='user/', help='Namespace to check against (default: user/)')
    check_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')

    # Checkall command
    checkall_parser = filedb_subparsers.add_parser('checkall', help='Check all local files against FileDB')
    checkall_parser.add_argument('--namespace', default='user/', help='Namespace to check against (default: user/)')
    checkall_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    checkall_parser.add_argument('--ignore-private', action='store_true', dest='ignore_private',
                            help='Ignore files starting with "_" or "-" (private files)')
    checkall_parser.add_argument('--only-present', action='store_true', dest='only_present',
                            help='Only check files that exist locally (skip remote-only files)')

    # Init command
    init_parser = filedb_subparsers.add_parser('init', help='Initialize empty directory with .claude structure and system commands')
    init_parser.add_argument('--force', action='store_true', help='Force initialization even if directory is not empty')

    # Search command
    search_parser = filedb_subparsers.add_parser('search', help='Search through FileDB files by content and/or filename')
    search_parser.add_argument('query', help='Search query string')
    search_parser.add_argument('--filename', help='Filename pattern with wildcards (*, ?, []) - optional')
    search_parser.add_argument('--namespace', default='user/', help='Namespace to search (default: user/)')
    search_parser.add_argument('--sys', action='store_true', help='Use system/ namespace (overrides --namespace)')
    search_parser.add_argument('--include-current', action='store_true', default=True,
                            help='Include active files in results (default: True)')
    search_parser.add_argument('--include-archived', action='store_true',
                            help='Include archived files in results')
    search_parser.add_argument('--include-deleted', action='store_true',
                            help='Include deleted files in results')
    search_parser.add_argument('--include-all-versions', action='store_true',
                            help='Include all versions, not just latest')
    search_parser.add_argument('--limit', type=int, default=10,
                            help='Maximum number of results to return (default: 10)')
    search_parser.add_argument('--max-content-length', type=int, default=-1,
                            help='Maximum content length to return (-1 = no limit)')
    search_parser.add_argument('--format', choices=['llm', 'json', 'table', 'files'], default='llm',
                            help='Output format (default: llm for concise output)')
    search_parser.add_argument('--directory', default='_filedb_search',
                            help='Directory to save files when using --format files (default: _filedb_search)')

    # Share command
    share_parser = filedb_subparsers.add_parser('share', help='Share file with users (latest version)')
    share_parser.add_argument('basename', help='File to share')
    share_parser.add_argument('user_ids', nargs='+', type=int, help='User IDs to share with')
    share_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    share_parser.add_argument('--sys', action='store_true', help='Use system/ namespace')

    # Unshare command
    unshare_parser = filedb_subparsers.add_parser('unshare', help='Remove all sharing from file (all versions)')
    unshare_parser.add_argument('basename', help='File to unshare')
    unshare_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    unshare_parser.add_argument('--sys', action='store_true', help='Use system/ namespace')

    # List shared command (files shared with me)
    list_shared_parser = filedb_subparsers.add_parser('list-shared', help='List files shared with you')
    list_shared_parser.add_argument('--format', choices=['llm', 'json', 'table'], default='llm',
                                    help='Output format (default: llm)')

    # List sharing command (files I have shared)
    list_sharing_parser = filedb_subparsers.add_parser('list-sharing', help='List files you have shared')
    list_sharing_parser.add_argument('--namespace', default='user/', help='Namespace (default: user/)')
    list_sharing_parser.add_argument('--sys', action='store_true', help='Use system/ namespace')
    list_sharing_parser.add_argument('--format', choices=['llm', 'json', 'table'], default='llm',
                                     help='Output format (default: llm)')

    # Help command
    help_parser = filedb_subparsers.add_parser('help', help='Show FileDB help information')
    help_parser.add_argument('subcommand', nargs='?', help='Show help for specific FileDB subcommand')


def handle_filedb_command(args, client: AigonClient):
    """Handle FileDB commands.

    Args:
        args: Parsed command-line arguments
        client: Authenticated Aigon client
    """
    # Helper function to get the namespace, checking for --sys flag
    def get_namespace():
        if hasattr(args, 'sys') and args.sys:
            return 'system/'
        return getattr(args, 'namespace', 'user/')

    if args.filedb_command == 'list':
        include_hidden = getattr(args, 'include_hidden', False)
        list_files(client, namespace=get_namespace(), output_format=args.format, include_hidden=include_hidden)
    elif args.filedb_command == 'read':
        read_file(client, basename=args.basename, namespace=get_namespace(),
                version=args.version)
    elif args.filedb_command == 'download':
        if getattr(args, 'download_all', False):
            # Download all files that exist locally
            download_all_present(client, namespace=get_namespace(), overwrite=args.overwrite)
        elif args.basename:
            download_file(client, basename=args.basename, namespace=get_namespace(),
                    version=args.version, overwrite=args.overwrite)
        else:
            print("Error: basename required (or use --all)")
            sys.exit(1)
    elif args.filedb_command == 'create':
        create_file(client, basename=args.basename, namespace=get_namespace())
    elif args.filedb_command == 'upload':
        if getattr(args, 'upload_all', False):
            # Upload all local files that exist in FileDB
            upload_all_present(client, namespace=get_namespace())
        elif args.basename:
            upload_file(
                client,
                basename=args.basename,
                file_path=args.path,
                namespace=get_namespace(),
                share_with=getattr(args, 'share', None),
                reshare=getattr(args, 'reshare', False),
                no_overwrite=getattr(args, 'no_overwrite', False)
            )
        else:
            print("Error: basename required (or use --all)")
            sys.exit(1)
    elif args.filedb_command == 'delete':
        sync_local = getattr(args, 'sync_local', False)
        delete_file(client, basename=args.basename, namespace=get_namespace(), sync_local=sync_local)
    elif args.filedb_command == 'archive':
        sync_local = getattr(args, 'sync_local', False)
        archive_file(client, basename=args.basename, namespace=get_namespace(), sync_local=sync_local)
    elif args.filedb_command == 'unarchive':
        sync_local = getattr(args, 'sync_local', False)
        unarchive_file(client, basename=args.basename, namespace=get_namespace(), sync_local=sync_local)
    elif args.filedb_command == 'undelete':
        sync_local = getattr(args, 'sync_local', False)
        undelete_file(client, basename=args.basename, namespace=get_namespace(), sync_local=sync_local)
    elif args.filedb_command == 'hash':
        hash_file(basename=args.basename)
    elif args.filedb_command == 'readall':
        include_hidden = getattr(args, 'include_hidden', False)
        read_all_files(client, namespace=get_namespace(), overwrite=args.overwrite, include_hidden=include_hidden)
    elif args.filedb_command == 'writeall':
        include_hidden = getattr(args, 'include_hidden', False)
        auto_confirm = getattr(args, 'auto_confirm', False)
        write_all_files(client, namespace=get_namespace(), pattern=args.pattern, include_hidden=include_hidden, auto_confirm=auto_confirm)
    elif args.filedb_command == 'updateall':
        include_hidden = getattr(args, 'include_hidden', False)
        auto_confirm = getattr(args, 'auto_confirm', False)
        update_all_files(client, namespace=get_namespace(), overwrite=args.overwrite, include_hidden=include_hidden, auto_confirm=auto_confirm)
    elif args.filedb_command == 'check':
        basenames = args.basenames
        if not basenames:
            # No args: check all .md files in current directory
            local_md_files = list(Path(".").glob("*.md"))
            basenames = [f.stem for f in local_md_files]
            if not basenames:
                print("No .md files found in current directory")
                sys.exit(0)
            print(f"Checking {len(basenames)} .md files...")
        for basename in basenames:
            check_single_file(client, basename=basename, namespace=get_namespace())
    elif args.filedb_command == 'checkall':
        ignore_private = getattr(args, 'ignore_private', False)
        only_present = getattr(args, 'only_present', False)
        check_all_files(client, namespace=get_namespace(), ignore_private=ignore_private, only_present=only_present)
    elif args.filedb_command == 'init':
        init_workspace(client, force=args.force)
    elif args.filedb_command == 'search':
        search_files(client,
                    query=args.query,
                    filename=args.filename,
                    include_current=args.include_current,
                    include_archived=args.include_archived,
                    include_deleted=args.include_deleted,
                    include_all_versions=args.include_all_versions,
                    limit=args.limit,
                    max_content_length=args.max_content_length,
                    namespace=get_namespace(),
                    output_format=args.format,
                    directory=args.directory)
    elif args.filedb_command == 'share':
        share_file_cmd(client, basename=args.basename, user_ids=args.user_ids,
                       namespace=get_namespace())
    elif args.filedb_command == 'unshare':
        unshare_file_cmd(client, basename=args.basename, namespace=get_namespace())
    elif args.filedb_command == 'list-shared':
        list_shared_files_cmd(client, output_format=args.format)
    elif args.filedb_command == 'list-sharing':
        list_files_i_shared_cmd(client, namespace=get_namespace(), output_format=args.format)
    elif args.filedb_command == 'help':
        if hasattr(args, 'subcommand') and args.subcommand:
            # Show help for specific filedb subcommand
            os.system(f"aigon filedb {args.subcommand} --help")
        else:
            # Show general filedb help directly
            print("FileDB Help - File management with versioning\n")
            print("Available FileDB commands:")
            print("  list      - List files in namespace")
            print("  read      - Read file content to stdout")
            print("  download  - Download file and save locally")
            print("  upload    - Upload file to FileDB")
            print("  create    - Create a new empty file")
            print("  delete    - Soft delete a file (recoverable)")
            print("  undelete  - Restore a deleted file")
            print("  archive   - Archive a file (hidden but preserved)")
            print("  unarchive - Restore an archived file")
            print("  readall   - Read all files from namespace")
            print("  writeall  - Write all local .md files to FileDB (hash-based selection)")
            print("  updateall - Update existing local files from FileDB (hash-based selection)")
            print("  check     - Check if local file matches FileDB")
            print("  checkall  - Check all local files against FileDB")
            print("  hash      - Calculate MD5 hash of local file")
            print("  init      - Initialize workspace with .claude structure and system commands")
            print("  search    - Search through FileDB files by content")
            print("  help      - Show FileDB help information")
            print("\nFile Status Lifecycle:")
            print("  ACTIVE -> delete -> DELETED -> undelete -> ACTIVE")
            print("  ACTIVE -> archive -> ARCHIVED -> unarchive -> ACTIVE")
            print("\nLocal File Sync Options:")
            print("  --sync-local     - Sync local file with FileDB operation")
            print("                     delete: deletes local file")
            print("                     archive: moves local to .archived/")
            print("                     unarchive: restores from .archived/ or downloads")
            print("                     undelete: downloads from FileDB")
            print("  --no-sync-local  - Do not touch local file (default)")
            print("\nNamespace Options:")
            print("  --namespace <name>  - Use specific namespace (default: user/)")
            print("  --sys               - Use system/ namespace (shortcut for system files)")
            print("\nHidden File Options:")
            print("  --include-hidden    - Include files starting with '_' (hidden by default)")
            print("                        Available for: list, readall, writeall, updateall commands")
            print("\nConfirmation Options:")
            print("  --yes               - Skip confirmation prompts (available for writeall, updateall)")
            print("                        Use with caution for batch operations")
            print("\nCheckall Filtering Options:")
            print("  --ignore-private    - Ignore files starting with '_' or '-' (available for checkall)")
            print("  --only-present      - Only check files that exist locally (available for checkall)")
            print("\nFor detailed command help: aigon filedb <command> --help")
            print("Examples:")
            print("  aigon filedb list --namespace user/")
            print("  aigon filedb list --sys")
            print("  aigon filedb list --include-hidden")
            print("  aigon filedb read myfile --version 2")
            print("  aigon filedb write myfile --path ./local_file.md")
            print("  aigon filedb write sysconfig --sys --path ./config.md")
            print("  aigon filedb readall --include-hidden")
            print("  aigon filedb writeall --include-hidden")
            print("  aigon filedb writeall --yes")
            print("  aigon filedb updateall")
            print("  aigon filedb updateall --yes --include-hidden")
            print("  aigon filedb checkall --ignore-private")
            print("  aigon filedb checkall --only-present")
            print("  aigon filedb init")
            print("  aigon filedb init --force")
    else:
        print(f"Unknown FileDB command: {args.filedb_command}", file=sys.stderr)
        sys.exit(1)
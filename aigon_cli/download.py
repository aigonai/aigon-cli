"""Unified download command for notes, attachments, and files.

Calls the unified /download/{unique_id} endpoint which auto-detects type.

(c) Stefan LOESCH 2026. All rights reserved.
"""

import mimetypes
import os
import sys

# MIME type to extension mapping (inlined from app.common.mime_utils)
_MIME_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/flac": "flac",
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "text/plain": "txt",
    "text/csv": "csv",
    "text/markdown": "md",
    "application/json": "json",
    "application/xml": "xml",
    "application/zip": "zip",
    "application/gzip": "gz",
}


def get_extension_from_mime(mime_type: str) -> str:
    """Get file extension from MIME type with dot prefix."""
    base_mime = mime_type.split(";")[0].strip().lower()
    ext = _MIME_TO_EXTENSION.get(base_mime)
    if ext is None:
        # Fallback to stdlib
        guessed = mimetypes.guess_extension(base_mime)
        return guessed if guessed else ".bin"
    return f".{ext}"


def handle_download_command(args, client) -> None:
    """Handle download command.

    Args:
        args: Parsed command-line arguments with:
            - unique_id: Resource unique ID (supports version suffix for files)
            - download: Download directory (None = stdout)
            - filename: Custom filename (optional)
            - uniquefn: Use unique filename based on unique_id (default True)
        client: Authenticated Aigon client
    """
    try:
        unique_id = args.unique_id
        download_directory = args.download
        custom_filename = getattr(args, "filename", None)
        use_unique_filename = getattr(args, "uniquefn", True)

        # Call unified download endpoint (auto-detects type)
        content, mime_type, api_filename = client.download_resource(unique_id)

        # Check if MIME type is displayable (text-based)
        is_displayable = mime_type and any(
            mime_type.startswith(prefix) for prefix in ["text/", "application/json", "application/xml"]
        )

        # Require --download for non-displayable content
        if not is_displayable and download_directory is None:
            print(f"Error: Resource has MIME type '{mime_type}' which cannot be displayed to stdout.", file=sys.stderr)
            print("Use --download <directory> to save the file.", file=sys.stderr)
            sys.exit(1)

        # Save or output
        if download_directory is not None:
            # Determine final filename
            if custom_filename:
                # Use custom filename
                filename = custom_filename
            elif use_unique_filename:
                # Create unique filename: unique_id + extension from API filename
                # Extract base unique_id (remove version suffix like +2 or -1)
                base_unique_id = unique_id.split("+")[0].split("-")[0]

                # Extract extension from API filename
                _, ext = os.path.splitext(api_filename)
                if not ext:
                    # Fallback: Get extension from MIME type (centralized mapping)
                    ext = get_extension_from_mime(mime_type)

                filename = f"{base_unique_id}{ext}"
            else:
                # Use API-provided filename (may not be unique)
                filename = api_filename

            # Save to file
            output_path = os.path.join(download_directory, filename)
            with open(output_path, "wb") as f:
                f.write(content)
            print(f"Downloaded: {output_path} ({len(content)} bytes, {mime_type})")
        else:
            # Output to stdout (text only)
            if mime_type == "application/json":
                # Pretty-print JSON
                import json

                json_data = json.loads(content.decode("utf-8"))
                print(json.dumps(json_data, indent=2))
            else:
                # Raw output
                sys.stdout.buffer.write(content)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def register_download_commands(subparsers) -> None:
    """Register download commands.

    Args:
        subparsers: Argparse subparsers object
    """
    download_parser = subparsers.add_parser("download", help="Download note, attachment, or file by unique_id")

    download_parser.add_argument(
        "unique_id",
        help="Unique ID of resource (note/attachment/file). "
        "Supports prefix matching (min 2 chars). "
        "For files, append version: AB12345678+2 or AB12345678-1",
    )

    download_parser.add_argument(
        "--download",
        "-d",
        nargs="?",
        const=".",
        default=None,
        metavar="DIRECTORY",
        help="Download to directory (default: current directory). Without this flag, output to stdout (text only).",
    )

    download_parser.add_argument(
        "--filename",
        "-f",
        type=str,
        default=None,
        metavar="FILENAME",
        help="Custom filename to save as (overrides --uniquefn). Example: --filename my_file.jpg",
    )

    download_parser.add_argument(
        "--uniquefn",
        action="store_true",
        default=True,
        help="Use unique filename: unique_id + extension (default: enabled). "
        "Use --no-uniquefn to save with original filename from API.",
    )

    download_parser.add_argument(
        "--no-uniquefn",
        dest="uniquefn",
        action="store_false",
        help="Save with original filename from API (not unique, may overwrite). "
        "By default, files are saved with unique filenames.",
    )

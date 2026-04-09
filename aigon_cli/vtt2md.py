#!/usr/bin/env python3
"""
VTT to Markdown Converter - Aigon CLI Tool
Converts VTT transcript files to clean Markdown format

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import re
import sys
from datetime import datetime
from pathlib import Path


def parse_timestamp(timestamp_str):
    """Parse VTT timestamp (HH:MM:SS.mmm) to seconds."""
    try:
        # Format: 00:00:13.390
        parts = timestamp_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except (ValueError, IndexError):
        return None


def format_duration(seconds):
    """Format seconds to HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_full_name(speaker_short):
    """Map short speaker names to full names."""
    name_mapping = {
        "Mark": "Mark Richardson",
        "mbr": "Mark Richardson",
        "Stefan Loesch": "Stefan Loesch",
        "Stefan": "Stefan Loesch",
    }
    return name_mapping.get(speaker_short, speaker_short)


def format_timestamp_short(timestamp_str):
    """Format timestamp to shorter form (H:MM:SS or MM:SS)."""
    if not timestamp_str:
        return ""
    # Remove milliseconds: 00:05:13.390 -> 00:05:13
    ts = timestamp_str.split(".")[0]
    # Remove leading zeros from hours: 00:05:13 -> 5:13 or 01:05:13 -> 1:05:13
    parts = ts.split(":")
    hours = int(parts[0])
    if hours == 0:
        return f"{int(parts[1])}:{parts[2]}"
    else:
        return f"{hours}:{parts[1]}:{parts[2]}"


def parse_vtt_file(vtt_path):
    """Parse a VTT file and extract speaker dialogues and metadata."""
    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove WEBVTT header
    content = re.sub(r"^WEBVTT\s*\n", "", content)

    # Split into blocks (separated by double newlines)
    blocks = content.split("\n\n")

    dialogues = []
    current_speaker = None
    current_text = []
    current_timestamp = None  # Track timestamp for current speaker block
    speakers = set()
    start_time = None
    end_time = None

    for block in blocks:
        lines = block.strip().split("\n")

        # Skip empty blocks or blocks that are just numbers
        if not lines or (len(lines) == 1 and lines[0].isdigit()):
            continue

        # Extract timestamp if present
        timestamp_line = None
        block_timestamp = None
        for line in lines:
            if "-->" in line:
                timestamp_line = line
                break

        # Extract start and end times from first and last timestamps
        if timestamp_line:
            match = re.search(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})", timestamp_line)
            if match:
                block_timestamp = match.group(1)
                if start_time is None:
                    start_time = match.group(1)
                end_time = match.group(2)

        # Find the dialogue line (not timestamp, not number)
        dialogue_line = None
        for line in lines:
            # Skip numbers and timestamps
            if line.isdigit() or "-->" in line:
                continue
            if line.strip():
                dialogue_line = line.strip()
                break

        if not dialogue_line:
            continue

        # Extract speaker and text
        # Format is usually "Speaker Name: text"
        if ":" in dialogue_line:
            parts = dialogue_line.split(":", 1)
            speaker = parts[0].strip()
            text = parts[1].strip() if len(parts) > 1 else ""

            # Track unique speakers
            speakers.add(speaker)

            # If same speaker continues, append to their text
            if speaker == current_speaker and current_text:
                current_text.append(text)
            else:
                # Save previous speaker's dialogue
                if current_speaker and current_text:
                    dialogues.append(
                        {"speaker": current_speaker, "text": " ".join(current_text), "timestamp": current_timestamp}
                    )

                # Start new speaker
                current_speaker = speaker
                current_text = [text] if text else []
                current_timestamp = block_timestamp
        else:
            # No speaker marker, might be continuation
            if current_speaker:
                current_text.append(dialogue_line)

    # Don't forget the last dialogue
    if current_speaker and current_text:
        dialogues.append({"speaker": current_speaker, "text": " ".join(current_text), "timestamp": current_timestamp})

    metadata = {"speakers": sorted(list(speakers)), "start_time": start_time, "end_time": end_time, "duration": None}

    # Calculate duration if we have both times
    if start_time and end_time:
        start_seconds = parse_timestamp(start_time)
        end_seconds = parse_timestamp(end_time)
        if start_seconds is not None and end_seconds is not None:
            metadata["duration"] = format_duration(end_seconds - start_seconds)

    return dialogues, metadata


def format_as_markdown(dialogues, metadata=None, title=None, date=None, format_type="markdown"):
    """Format dialogues as Markdown with YAML frontmatter and timestamps."""
    md_lines = []

    # Add YAML frontmatter
    md_lines.append("---")

    if title:
        md_lines.append(f"title: {title}")

    if date:
        md_lines.append(f"date: {date}")

    if metadata:
        # Add duration
        if metadata.get("duration"):
            md_lines.append(f"duration: {metadata['duration']}")

        # Add participants as simple list
        if metadata.get("speakers"):
            md_lines.append("participants:")
            for speaker in metadata["speakers"]:
                full_name = get_full_name(speaker)
                md_lines.append(f"  - {full_name}")

    md_lines.append("---\n")

    # Group consecutive dialogues by same speaker
    if not dialogues:
        return "No dialogue found."

    current_speaker = None
    current_paragraphs = []
    current_timestamp = None

    for dialogue in dialogues:
        speaker = dialogue["speaker"]
        text = dialogue["text"]
        timestamp = dialogue.get("timestamp")

        if speaker == current_speaker:
            # Same speaker, add as new paragraph
            current_paragraphs.append(text)
        else:
            # New speaker, output previous and start new
            if current_speaker:
                if current_timestamp:
                    ts_short = format_timestamp_short(current_timestamp)
                    md_lines.append(f"\n**{current_speaker}:** [{ts_short}]\n")
                else:
                    md_lines.append(f"\n**{current_speaker}:**\n")
                for para in current_paragraphs:
                    if para.strip():
                        md_lines.append(f"{para}\n")

            current_speaker = speaker
            current_paragraphs = [text]
            current_timestamp = timestamp

    # Output last speaker
    if current_speaker:
        if current_timestamp:
            ts_short = format_timestamp_short(current_timestamp)
            md_lines.append(f"\n**{current_speaker}:** [{ts_short}]\n")
        else:
            md_lines.append(f"\n**{current_speaker}:**\n")
        for para in current_paragraphs:
            if para.strip():
                md_lines.append(f"{para}\n")

    return "\n".join(md_lines)


def extract_date_from_filename(filename):
    """Extract date from GMT timestamp in filename."""
    # Pattern: GMT20251208-145648
    match = re.search(r"GMT(\d{8})-", filename)
    if match:
        date_str = match.group(1)
        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            # Include day of week
            return date_obj.strftime("%a %B %d, %Y")
        except (ValueError, IndexError):
            pass
    return None


def convert_vtt_to_md(vtt_path, output_path=None, title=None, format_type="markdown", use_stdout=False):
    """Convert a VTT file to Markdown."""
    vtt_path = Path(vtt_path)

    if not vtt_path.exists():
        print(f"Error: File not found: {vtt_path}", file=sys.stderr)
        return False

    # Parse VTT
    if not use_stdout:
        print(f"Parsing {vtt_path.name}...", file=sys.stderr)
    dialogues, metadata = parse_vtt_file(vtt_path)

    # Extract date from filename
    date = extract_date_from_filename(vtt_path.name)

    # Generate title if not provided
    if not title:
        title = "Meeting Transcript"

    # Format as Markdown
    markdown = format_as_markdown(dialogues, metadata=metadata, title=title, date=date, format_type=format_type)

    # Output to stdout or file
    if use_stdout:
        print(markdown)
    else:
        # Determine output path
        if not output_path:
            output_path = vtt_path.with_suffix(".md")
        else:
            output_path = Path(output_path)

        # Write output
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        print(f"✓ Created {output_path.name} ({len(dialogues)} dialogue blocks)", file=sys.stderr)

    return True


def convert_directory(directory, output_dir=None, format_type="markdown"):
    """Convert all VTT files in a directory."""
    directory = Path(directory)

    if not directory.is_dir():
        print(f"Error: Not a directory: {directory}", file=sys.stderr)
        return

    vtt_files = sorted(directory.glob("*.vtt"))

    if not vtt_files:
        print(f"No VTT files found in {directory}", file=sys.stderr)
        return

    print(f"Found {len(vtt_files)} VTT file(s)\n", file=sys.stderr)

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)

    for vtt_file in vtt_files:
        output_path = None
        if output_dir:
            output_path = output_dir / vtt_file.with_suffix(".md").name

        convert_vtt_to_md(vtt_file, output_path, format_type=format_type)

    print("\n✓ Conversion complete!", file=sys.stderr)


def register_vtt2md_commands(subparsers):
    """Register vtt2md subcommands."""
    vtt2md_parser = subparsers.add_parser(
        "vtt2md",
        help="Convert VTT transcript files to Markdown",
        description="Convert VTT transcript files to clean Markdown format",
    )

    vtt2md_parser.add_argument("input", help="Input VTT file or directory")
    vtt2md_parser.add_argument("output", nargs="?", help="Output file or directory (optional)")
    vtt2md_parser.add_argument("--stdout", action="store_true", help="Output to stdout instead of file")
    vtt2md_parser.add_argument(
        "--format",
        choices=["markdown", "plain"],
        default="markdown",
        help="Output format: markdown (with YAML frontmatter) or plain (default: markdown)",
    )
    vtt2md_parser.add_argument("-o", "--output-dir", help="Output directory (alternative to positional output arg)")
    vtt2md_parser.add_argument("-t", "--title", help="Custom title for the transcript")


def handle_vtt2md_command(args):
    """Handle vtt2md command."""
    input_path = Path(args.input)
    output_path = args.output or args.output_dir

    if not input_path.exists():
        print(f"Error: Path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if input_path.is_file():
        if args.stdout and input_path.is_file():
            # Single file to stdout
            convert_vtt_to_md(input_path, format_type=args.format, use_stdout=True, title=args.title)
        else:
            # Single file to file
            convert_vtt_to_md(input_path, output_path, format_type=args.format, title=args.title)
    elif input_path.is_dir():
        if args.stdout:
            print("Error: --stdout cannot be used with directory input", file=sys.stderr)
            sys.exit(1)
        convert_directory(input_path, output_path, format_type=args.format)
    else:
        print(f"Error: Invalid path: {input_path}", file=sys.stderr)
        sys.exit(1)

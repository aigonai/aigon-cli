# Aigon CLI

Command-line interface for the [Aigon](https://aigon.ai) AI assistant ecosystem.

## Installation

Install [uv](https://docs.astral.sh/uv/) (if not installed):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install aigon-cli:

```bash
uv tool install aigon-cli
```

Optionally install the markdown viewer:

```bash
uv tool install aigon-viewer
```

## Usage

```bash
aigon --help          # Show all commands
aigon --version       # Show version
aigon config          # Configure API connection
aigon notes search    # Search notes
aigon files ls        # List files
aigon viewer launch   # Launch markdown viewer (requires aigon-viewer)
```

## Configuration

Run `aigon config` to set up your API token and URL. Configuration is stored in `~/.aigon`.

## Commands

| Command | Description |
|---------|-------------|
| `config` | Manage API configuration |
| `notes` | Search, read, and manage notes |
| `files` | File management (list, upload, download) |
| `download` | Download any resource by unique ID |
| `viewer` | Launch markdown viewer (requires aigon-viewer) |
| `report` | Generate reports |
| `event` | Event and participant management |
| `crypto` | Encryption/decryption tools |
| `vtt2md` | Convert VTT transcripts to markdown |
| `search` | Global search across all resources |
| `llm` | LLM-related commands |

## License

(c) Stefan LOESCH 2025-26. All rights reserved.

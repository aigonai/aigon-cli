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

### Standalone zipapp (no dependencies)

Download the latest `aigon.pyz` from [GitHub Releases](https://github.com/aigonai/aigon-cli/releases/latest):

```bash
curl -Lo aigon.pyz https://github.com/aigonai/aigon-cli/releases/latest/download/aigon.pyz
chmod +x aigon.pyz
./aigon.pyz --version
```

Requires only Python 3.10+.

## Usage

```bash
aigon --help            # Show all subcommands
aigon --version         # Show version
aigon notetaker help    # Show notetaker subcommands
aigon llm               # LLM-friendly command reference
```

## Subcommands

| Subcommand | Description |
|---------|-------------|
| `llm` | LLM-friendly command reference |
| `viewer` | Launch markdown viewer (requires aigon-viewer) |
| `notetaker` | Search, read, and manage notes |
| `event` | Event and participant management |
| `report` | Generate reports |
| `filedb` | File management (list, upload, download, sync) |
| `search` | Global search across all resources |
| `download` | Download any resource by unique ID |
| `config` | Manage API configuration |

## Configuration

Run `aigon config` to set up your API token and URL. Configuration is stored in `~/.aigon`.

## License

(c) Stefan LOESCH 2025-26. All rights reserved.

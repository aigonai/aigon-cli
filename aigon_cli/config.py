#!/usr/bin/env python3
"""Aigon CLI - Configuration management.

Handles reading/writing configuration from ~/.aigon file.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import configparser
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Default config path, can be overridden by AIGON_CLI_CONFIG_FILE env var or --config-file CLI option
_config_path: Optional[Path] = None
_local_config_warning_shown: bool = False


def get_config_path() -> Path:
    """Get the config file path.

    Priority:
    1. Explicitly set via set_config_path() (from --config-file CLI option)
    2. Local .aigon in current directory (with warning)
    3. AIGON_CLI_CONFIG_FILE environment variable
    4. Default: ~/.aigon

    Returns:
        Path to config file
    """
    global _config_path, _local_config_warning_shown
    if _config_path is not None:
        return _config_path

    # Check for local .aigon in current directory
    local_config = Path.cwd() / ".aigon"
    if local_config.exists():
        # Show warning only once per execution
        if not _local_config_warning_shown:
            print(f"Warning: Using local config file: ./.aigon", file=sys.stderr)
            _local_config_warning_shown = True
        return local_config

    env_path = os.getenv("AIGON_CLI_CONFIG_FILE")
    if env_path:
        return Path(env_path)

    return Path.home() / ".aigon"


def set_config_path(path: str) -> None:
    """Set the config file path (from --config-file CLI option).

    Args:
        path: Path to config file
    """
    global _config_path
    _config_path = Path(path)


def load_config() -> configparser.ConfigParser:
    """Load configuration from config file.

    Returns:
        ConfigParser instance (empty if file doesn't exist)
    """
    config = configparser.ConfigParser()
    config_path = get_config_path()
    if config_path.exists():
        config.read(config_path)
    return config


def save_config(config: configparser.ConfigParser) -> None:
    """Save configuration to config file.

    Args:
        config: ConfigParser instance to save
    """
    config_path = get_config_path()
    with open(config_path, 'w') as f:
        config.write(f)


def get_config_value(section: str, key: str) -> Optional[str]:
    """Get a value from config file.

    Args:
        section: Config section name
        key: Config key name

    Returns:
        Value if found, None otherwise
    """
    config = load_config()
    if config.has_option(section, key):
        return config.get(section, key)
    return None


def set_config_value(section: str, key: str, value: str) -> None:
    """Set a value in config file.

    Args:
        section: Config section name
        key: Config key name
        value: Value to set
    """
    config = load_config()
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, key, value)
    save_config(config)


def unset_config_value(section: str, key: str) -> bool:
    """Remove a value from config file.

    Args:
        section: Config section name
        key: Config key name

    Returns:
        True if key existed and was removed, False if key didn't exist
    """
    config = load_config()
    if config.has_option(section, key):
        config.remove_option(section, key)
        # Remove section if empty
        if not config.options(section):
            config.remove_section(section)
        save_config(config)
        return True
    return False


def get_api_token() -> Optional[str]:
    """Get API token from environment or config file.

    Priority:
    - If both env and config exist and differ: ERROR
    - If both exist and match: return value
    - If only env exists: return env value
    - If only config exists: return config value
    - If neither exists: return None

    Returns:
        API token string or None if not found

    Raises:
        SystemExit: If env and config both exist with different values
    """
    env_token = os.getenv("AIGON_API_TOKEN")
    config_token = get_config_value('api', 'token')

    if env_token and config_token:
        if env_token != config_token:
            print("ERROR: API token conflict detected!", file=sys.stderr)
            print("", file=sys.stderr)
            print("  AIGON_API_TOKEN environment variable is set", file=sys.stderr)
            print("  AND ~/.aigon [api] token is set", file=sys.stderr)
            print("  BUT they have different values!", file=sys.stderr)
            print("", file=sys.stderr)
            print("Please resolve by either:", file=sys.stderr)
            print("  1. Unset the environment variable: unset AIGON_API_TOKEN", file=sys.stderr)
            print("  2. Remove from config: aigon config unset api.token", file=sys.stderr)
            print("  3. Make them match", file=sys.stderr)
            sys.exit(1)
        # Both exist and match
        return env_token

    # Return whichever exists (or None if neither)
    return env_token or config_token


def get_api_url() -> str:
    """Get API URL from environment or config file.

    Returns:
        API URL string (defaults to https://api.aigon.ai)
    """
    env_url = os.getenv("AIGON_API_URL")
    config_url = get_config_value('api', 'url')

    # Similar conflict check
    if env_url and config_url and env_url != config_url:
        print("ERROR: API URL conflict detected!", file=sys.stderr)
        print("  AIGON_API_URL env and ~/.aigon [api] url differ", file=sys.stderr)
        sys.exit(1)

    return env_url or config_url or "https://api.aigon.ai"


# ===== CLI Commands =====

def register_config_commands(subparsers) -> None:
    """Register config commands with argument parser."""
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_subparsers = config_parser.add_subparsers(dest='config_command', help='Config commands')

    # aigon config show
    show_parser = config_subparsers.add_parser('show', help='Show current configuration')
    show_parser.add_argument('--secrets', action='store_true',
                            help='Show secret values (tokens, keys)')

    # aigon config set <key> <value>
    set_parser = config_subparsers.add_parser('set', help='Set a configuration value')
    set_parser.add_argument('key', help='Config key (e.g., api.token, api.url, encryption.key)')
    set_parser.add_argument('value', help='Value to set')

    # aigon config unset <key>
    unset_parser = config_subparsers.add_parser('unset', help='Remove a configuration value')
    unset_parser.add_argument('key', help='Config key to remove (e.g., api.token)')

    # aigon config get <key>
    get_parser = config_subparsers.add_parser('get', help='Get a configuration value')
    get_parser.add_argument('key', help='Config key (e.g., api.token)')
    get_parser.add_argument('--secrets', action='store_true',
                           help='Show secret values (tokens, keys)')

    # aigon config help
    config_subparsers.add_parser('help', help='Show config help')


def handle_config_command(args) -> None:
    """Handle config commands."""
    if args.config_command == 'show':
        cmd_show(show_secrets=args.secrets)
    elif args.config_command == 'set':
        cmd_set(args.key, args.value)
    elif args.config_command == 'unset':
        cmd_unset(args.key)
    elif args.config_command == 'get':
        cmd_get(args.key, show_secrets=getattr(args, 'secrets', False))
    elif args.config_command == 'help':
        cmd_help()
    else:
        cmd_help()


def _parse_key(key: str) -> tuple:
    """Parse a dotted key into section and option.

    Args:
        key: Key in format "section.option" (e.g., "api.token")

    Returns:
        Tuple of (section, option)
    """
    if '.' not in key:
        print(f"Error: Invalid key format '{key}'", file=sys.stderr)
        print("Expected format: section.key (e.g., api.token, encryption.key)", file=sys.stderr)
        sys.exit(1)

    parts = key.split('.', 1)
    return parts[0], parts[1]


def _is_secret_key(section: str, option: str) -> bool:
    """Check if a config key is a secret."""
    secret_keys = [
        ('api', 'token'),
        ('encryption', 'key'),
    ]
    return (section, option) in secret_keys


def _mask_value(value: str) -> str:
    """Mask a secret value for display."""
    if len(value) <= 8:
        return '*' * len(value)
    return value[:4] + '*' * (len(value) - 8) + value[-4:]


def cmd_show(show_secrets: bool = False) -> None:
    """Show current configuration."""
    config = load_config()
    config_path = get_config_path()

    print(f"Config file: {config_path}")
    if not config_path.exists():
        print("  (file does not exist)")
        print("")
    else:
        print("")

    # Show file config
    if config.sections():
        print("File configuration:")
        for section in config.sections():
            print(f"  [{section}]")
            for option in config.options(section):
                value = config.get(section, option)
                if _is_secret_key(section, option) and not show_secrets:
                    value = _mask_value(value)
                print(f"    {option} = {value}")
        print("")
    else:
        print("File configuration: (empty)")
        print("")

    # Show environment overrides
    env_vars = [
        ('AIGON_API_TOKEN', 'api.token'),
        ('AIGON_API_URL', 'api.url'),
        ('AIGON_CLI_CONFIG_FILE', None),  # Special: not a config key, just env var
    ]

    print("Environment variables:")
    found_env = False
    for env_var, config_key in env_vars:
        value = os.getenv(env_var)
        if value:
            found_env = True
            if config_key:
                section, option = _parse_key(config_key)
                if _is_secret_key(section, option) and not show_secrets:
                    value = _mask_value(value)
            print(f"  {env_var} = {value}")

    if not found_env:
        print("  (none set)")

    print("")
    print("Use --secrets to show full token/key values")


def cmd_set(key: str, value: str) -> None:
    """Set a configuration value."""
    section, option = _parse_key(key)

    # Check for environment conflict on secrets
    if section == 'api' and option == 'token':
        env_token = os.getenv('AIGON_API_TOKEN')
        if env_token and env_token != value:
            print("Warning: AIGON_API_TOKEN environment variable is also set", file=sys.stderr)
            print("         The environment variable will take precedence", file=sys.stderr)
            print("         Consider: unset AIGON_API_TOKEN", file=sys.stderr)
            print("")

    set_config_value(section, option, value)

    if _is_secret_key(section, option):
        print(f"Set {key} = {_mask_value(value)}")
    else:
        print(f"Set {key} = {value}")


def cmd_unset(key: str) -> None:
    """Remove a configuration value."""
    section, option = _parse_key(key)

    if unset_config_value(section, option):
        print(f"Removed {key}")
    else:
        print(f"Key {key} was not set")


def cmd_get(key: str, show_secrets: bool = False) -> None:
    """Get a configuration value."""
    section, option = _parse_key(key)

    value = get_config_value(section, option)
    if value is None:
        print(f"{key}: (not set)")
    elif _is_secret_key(section, option) and not show_secrets:
        print(f"{key} = {_mask_value(value)}")
    else:
        print(f"{key} = {value}")


def cmd_help() -> None:
    """Show config help."""
    print("Aigon Config - Configuration Management")
    print("")
    print("Commands:")
    print("  aigon config show [--secrets]      Show all configuration")
    print("  aigon config get <key> [--secrets] Get a specific value")
    print("  aigon config set <key> <value>     Set a configuration value")
    print("  aigon config unset <key>           Remove a configuration value")
    print("")
    print("Configuration Variables:")
    print("")
    print("  api.token")
    print("    Description: API authentication token for REST API access")
    print("    Required: Yes (for API commands)")
    print("    How to get: Use Telegram bot @aigon_auth_bot, send /get")
    print("    Example: abc123def456789...")
    print("")
    print("  api.url")
    print("    Description: Base URL for the Aigon REST API server")
    print("    Required: No")
    print("    Default: https://api.aigon.ai")
    print("    Example: https://api.example.com or http://localhost:8000")
    print("    Use Cases: Local development, custom server deployment")
    print("")
    print("  encryption.key")
    print("    Description: Encryption key for 'aigon crypto' commands")
    print("    Required: No (only for crypto commands)")
    print("    Format: Base64-encoded 32-byte key")
    print("    Example: YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY=")
    print("")
    print("  encryption.backend")
    print("    Description: Encryption library to use for crypto operations")
    print("    Required: No")
    print("    Default: auto")
    print("    Valid Values:")
    print("      - auto: Try native (cryptography), fallback to vendored (PyCryptodome)")
    print("      - native: Use cryptography library (pip install cryptography)")
    print("      - vendored: Use PyCryptodome library (pip install pycryptodome)")
    print("")
    print("Config File Format:")
    print("  INI format with sections [api], [encryption], etc.")
    print("  Example ~/.aigon file:")
    print("    [api]")
    print("    token = your_token_here")
    print("    url = https://api.aigon.ai")
    print("")
    print("    [encryption]")
    print("    key = your_base64_key_here")
    print("    backend = auto")
    print("")
    print("Config File Location Priority:")
    print("  1. --config-file <path>           (command line argument)")
    print("  2. ./.aigon                       (local directory - prints warning)")
    print("  3. AIGON_CLI_CONFIG_FILE env var  (environment variable)")
    print("  4. ~/.aigon                       (global default)")
    print("")
    print("Config File Creation:")
    print("  - By default, creates/modifies ~/.aigon (global)")
    print("  - If ./.aigon exists (even if empty), uses local instead of global")
    print("  - Force local: touch ./.aigon && aigon config set <key> <value>")
    print("  - If --config-file or env var set, creates at that location")
    print("")
    print("Examples:")
    print("  aigon config set api.token abc123def456")
    print("  aigon config set api.url https://api.example.com")
    print("  aigon config set encryption.backend native")
    print("  aigon config show --secrets")
    print("  aigon config get api.url")
    print("  aigon config unset api.token")
    print("  aigon --config-file /path/to/config config show")

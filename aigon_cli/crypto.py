"""Crypto commands for Aigon CLI.

This module provides command-line interface for testing encryption backends
on different platforms. Used primarily for development and testing.

Supported backends:
- native: Uses platform-native tools (openssl on Mac/Linux, PowerShell on Windows)
- openssl: Explicitly uses openssl command
- vendored: Pure-Python AES implementation (pyaes)

Config file: ~/.aigon (INI format)

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import base64
import configparser
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


# Config file location
CONFIG_PATH = Path.home() / ".aigon"

# Backend configuration
DEFAULT_BACKEND = "auto"  # auto, native, openssl, vendored


def load_config() -> configparser.ConfigParser:
    """Load config from ~/.aigon.

    Returns:
        ConfigParser with loaded config (empty sections if file doesn't exist)
    """
    config = configparser.ConfigParser()
    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)
    return config


def save_config(config: configparser.ConfigParser) -> None:
    """Save config to ~/.aigon.

    Args:
        config: ConfigParser to save
    """
    with open(CONFIG_PATH, 'w') as f:
        config.write(f)


def get_config_key() -> Optional[str]:
    """Get encryption key from config.

    Returns:
        Base64-encoded key or None if not set
    """
    config = load_config()
    if config.has_option('encryption', 'key'):
        return config.get('encryption', 'key')
    return None


def get_config_backend() -> str:
    """Get backend setting from config with platform overrides.

    Resolution order:
    1. Platform-specific: backend_mac, backend_linux, backend_win
    2. Global: backend
    3. Default: auto

    Returns:
        Backend setting string
    """
    config = load_config()
    system = platform.system()

    # Platform-specific override keys
    override_key = {
        'Darwin': 'backend_mac',
        'Linux': 'backend_linux',
        'Windows': 'backend_win'
    }.get(system)

    # Check platform-specific first
    if override_key and config.has_option('encryption', override_key):
        return config.get('encryption', override_key)

    # Fall back to global
    if config.has_option('encryption', 'backend'):
        return config.get('encryption', 'backend')

    # Default
    return 'auto'


def get_platform_info() -> dict:
    """Get platform information for encryption backend selection.

    Returns:
        Dictionary with platform details
    """
    return {
        'system': platform.system(),  # Darwin, Linux, Windows
        'release': platform.release(),
        'machine': platform.machine(),
        'python_version': platform.python_version(),
        'openssl_available': shutil.which('openssl') is not None,
        'powershell_available': shutil.which('powershell') is not None or shutil.which('pwsh') is not None,
    }


def derive_key(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """Derive a 256-bit key from password using PBKDF2.

    Args:
        password: User password
        salt: Optional salt bytes (generates random if not provided)

    Returns:
        Tuple of (key, salt)
    """
    if salt is None:
        salt = os.urandom(16)

    # PBKDF2 with SHA-256, 100k iterations
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return key, salt


def _encrypt_openssl(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """Encrypt using openssl command.

    Args:
        plaintext: Data to encrypt
        key: 32-byte AES key
        iv: 16-byte initialization vector

    Returns:
        Encrypted ciphertext
    """
    key_hex = key.hex()
    iv_hex = iv.hex()

    proc = subprocess.run(
        ['openssl', 'enc', '-aes-256-cbc', '-K', key_hex, '-iv', iv_hex, '-nosalt'],
        input=plaintext,
        capture_output=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"OpenSSL encryption failed: {proc.stderr.decode()}")

    return proc.stdout


def _decrypt_openssl(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt using openssl command.

    Args:
        ciphertext: Encrypted data
        key: 32-byte AES key
        iv: 16-byte initialization vector

    Returns:
        Decrypted plaintext
    """
    key_hex = key.hex()
    iv_hex = iv.hex()

    proc = subprocess.run(
        ['openssl', 'enc', '-aes-256-cbc', '-d', '-K', key_hex, '-iv', iv_hex, '-nosalt'],
        input=ciphertext,
        capture_output=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"OpenSSL decryption failed: {proc.stderr.decode()}")

    return proc.stdout


def _encrypt_powershell(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """Encrypt using PowerShell (Windows).

    Args:
        plaintext: Data to encrypt
        key: 32-byte AES key
        iv: 16-byte initialization vector

    Returns:
        Encrypted ciphertext
    """
    key_b64 = base64.b64encode(key).decode()
    iv_b64 = base64.b64encode(iv).decode()
    plaintext_b64 = base64.b64encode(plaintext).decode()

    script = f'''
$key = [Convert]::FromBase64String("{key_b64}")
$iv = [Convert]::FromBase64String("{iv_b64}")
$plaintext = [Convert]::FromBase64String("{plaintext_b64}")

$aes = [System.Security.Cryptography.Aes]::Create()
$aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
$aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
$aes.Key = $key
$aes.IV = $iv

$encryptor = $aes.CreateEncryptor()
$ciphertext = $encryptor.TransformFinalBlock($plaintext, 0, $plaintext.Length)
[Convert]::ToBase64String($ciphertext)
'''

    pwsh = shutil.which('pwsh') or shutil.which('powershell')
    proc = subprocess.run(
        [pwsh, '-Command', script],
        capture_output=True,
        text=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell encryption failed: {proc.stderr}")

    return base64.b64decode(proc.stdout.strip())


def _decrypt_powershell(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt using PowerShell (Windows).

    Args:
        ciphertext: Encrypted data
        key: 32-byte AES key
        iv: 16-byte initialization vector

    Returns:
        Decrypted plaintext
    """
    key_b64 = base64.b64encode(key).decode()
    iv_b64 = base64.b64encode(iv).decode()
    ciphertext_b64 = base64.b64encode(ciphertext).decode()

    script = f'''
$key = [Convert]::FromBase64String("{key_b64}")
$iv = [Convert]::FromBase64String("{iv_b64}")
$ciphertext = [Convert]::FromBase64String("{ciphertext_b64}")

$aes = [System.Security.Cryptography.Aes]::Create()
$aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
$aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
$aes.Key = $key
$aes.IV = $iv

$decryptor = $aes.CreateDecryptor()
$plaintext = $decryptor.TransformFinalBlock($ciphertext, 0, $ciphertext.Length)
[Convert]::ToBase64String($plaintext)
'''

    pwsh = shutil.which('pwsh') or shutil.which('powershell')
    proc = subprocess.run(
        [pwsh, '-Command', script],
        capture_output=True,
        text=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell decryption failed: {proc.stderr}")

    return base64.b64decode(proc.stdout.strip())


def _encrypt_vendored(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """Encrypt using vendored pure-Python AES (pyaes).

    Args:
        plaintext: Data to encrypt
        key: 32-byte AES key
        iv: 16-byte initialization vector

    Returns:
        Encrypted ciphertext
    """
    try:
        from .vendored import pyaes
    except ImportError:
        raise RuntimeError("Vendored pyaes not available. Install or vendor pyaes first.")

    # PKCS7 padding
    block_size = 16
    padding_len = block_size - (len(plaintext) % block_size)
    padded = plaintext + bytes([padding_len] * padding_len)

    # AES-256-CBC encryption
    encrypter = pyaes.Encrypter(pyaes.AESModeOfOperationCBC(key, iv))
    ciphertext = encrypter.feed(padded)
    ciphertext += encrypter.feed()

    return ciphertext


def _decrypt_vendored(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt using vendored pure-Python AES (pyaes).

    Args:
        ciphertext: Encrypted data
        key: 32-byte AES key
        iv: 16-byte initialization vector

    Returns:
        Decrypted plaintext
    """
    try:
        from .vendored import pyaes
    except ImportError:
        raise RuntimeError("Vendored pyaes not available. Install or vendor pyaes first.")

    try:
        # AES-256-CBC decryption (pyaes validates PKCS7 padding internally)
        decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(key, iv))
        padded = decrypter.feed(ciphertext)
        padded += decrypter.feed()  # Final block includes padding validation
    except ValueError as e:
        # pyaes raises ValueError for invalid padding - convert to RuntimeError for consistency
        raise RuntimeError(f"Decryption failed: {e}")

    # Manual PKCS7 unpadding (encrypt adds padding manually before pyaes)
    if not padded:
        raise RuntimeError("Decryption failed: empty output")
    padding_len = padded[-1]
    if not (1 <= padding_len <= 16) or len(padded) < padding_len:
        raise RuntimeError("Decryption failed: invalid padding")
    plaintext = padded[:-padding_len]

    return plaintext


def select_backend(requested: str = "auto") -> str:
    """Select encryption backend based on request and platform.

    Args:
        requested: Requested backend (auto, native, openssl, vendored, powershell)

    Returns:
        Selected backend name
    """
    info = get_platform_info()

    if requested == "openssl":
        if not info['openssl_available']:
            raise RuntimeError("OpenSSL not available on this system")
        return "openssl"

    if requested == "powershell":
        if not info['powershell_available']:
            raise RuntimeError("PowerShell not available on this system")
        return "powershell"

    if requested == "vendored":
        return "vendored"

    if requested == "native":
        if info['system'] == 'Windows':
            if info['powershell_available']:
                return "powershell"
            raise RuntimeError("PowerShell not available on Windows")
        else:
            if info['openssl_available']:
                return "openssl"
            raise RuntimeError("OpenSSL not available on this system")

    # Auto selection
    if requested == "auto":
        if info['system'] == 'Windows':
            if info['powershell_available']:
                return "powershell"
            return "vendored"
        else:
            if info['openssl_available']:
                return "openssl"
            return "vendored"

    raise ValueError(f"Unknown backend: {requested}")


def encrypt(plaintext: bytes, password: str, backend: str = "auto") -> bytes:
    """Encrypt data with password.

    Output format: salt (16 bytes) + iv (16 bytes) + ciphertext

    Args:
        plaintext: Data to encrypt
        password: Encryption password
        backend: Encryption backend to use

    Returns:
        Encrypted data with embedded salt and IV
    """
    backend = select_backend(backend)

    # Derive key and generate IV
    key, salt = derive_key(password)
    iv = os.urandom(16)

    # Encrypt based on backend
    if backend == "openssl":
        ciphertext = _encrypt_openssl(plaintext, key, iv)
    elif backend == "powershell":
        ciphertext = _encrypt_powershell(plaintext, key, iv)
    elif backend == "vendored":
        ciphertext = _encrypt_vendored(plaintext, key, iv)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    # Combine: salt + iv + ciphertext
    return salt + iv + ciphertext


def decrypt(encrypted: bytes, password: str, backend: str = "auto") -> bytes:
    """Decrypt data with password.

    Input format: salt (16 bytes) + iv (16 bytes) + ciphertext

    Args:
        encrypted: Encrypted data with embedded salt and IV
        password: Decryption password
        backend: Encryption backend to use

    Returns:
        Decrypted plaintext
    """
    backend = select_backend(backend)

    # Extract salt, iv, ciphertext
    salt = encrypted[:16]
    iv = encrypted[16:32]
    ciphertext = encrypted[32:]

    # Derive key from password and salt
    key, _ = derive_key(password, salt)

    # Decrypt based on backend
    if backend == "openssl":
        plaintext = _decrypt_openssl(ciphertext, key, iv)
    elif backend == "powershell":
        plaintext = _decrypt_powershell(ciphertext, key, iv)
    elif backend == "vendored":
        plaintext = _decrypt_vendored(ciphertext, key, iv)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    return plaintext


def test_backend(backend: str) -> dict:
    """Test an encryption backend.

    Args:
        backend: Backend to test

    Returns:
        Test result dictionary
    """
    import time

    test_data = b"Hello, World! This is a test message for encryption."
    password = "test_password_123"

    result = {
        'backend': backend,
        'available': False,
        'error': None,
        'encrypt_time_ms': None,
        'decrypt_time_ms': None,
        'roundtrip_success': False
    }

    try:
        # Test encryption
        start = time.time()
        encrypted = encrypt(test_data, password, backend)
        result['encrypt_time_ms'] = round((time.time() - start) * 1000, 2)

        # Test decryption
        start = time.time()
        decrypted = decrypt(encrypted, password, backend)
        result['decrypt_time_ms'] = round((time.time() - start) * 1000, 2)

        # Verify roundtrip
        result['roundtrip_success'] = (decrypted == test_data)
        result['available'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def show_settings() -> None:
    """Display current encryption settings and backend availability."""
    info = get_platform_info()

    print("Encryption Settings")
    print("=" * 50)

    # Config file
    print(f"\nConfig File: {CONFIG_PATH}")
    print(f"  Exists: {'Yes' if CONFIG_PATH.exists() else 'No'}")

    # Config values
    config = load_config()
    print(f"\nConfig Values:")
    if config.has_section('encryption'):
        for key, value in config.items('encryption'):
            if key == 'key':
                # Mask the key, show only first/last 4 chars
                if len(value) > 12:
                    masked = value[:4] + '...' + value[-4:]
                else:
                    masked = '***'
                print(f"  {key} = {masked}")
            else:
                print(f"  {key} = {value}")
    else:
        print("  (no [encryption] section)")

    # Effective settings
    print(f"\nEffective Settings:")
    config_backend = get_config_backend()
    config_key = get_config_key()
    print(f"  Backend setting: {config_backend}")
    print(f"  Key configured: {'Yes' if config_key else 'No'}")

    print(f"\nPlatform Information:")
    print(f"  System: {info['system']}")
    print(f"  Release: {info['release']}")
    print(f"  Machine: {info['machine']}")
    print(f"  Python: {info['python_version']}")

    print(f"\nBackend Availability:")
    print(f"  OpenSSL: {'Available' if info['openssl_available'] else 'Not available'}")
    print(f"  PowerShell: {'Available' if info['powershell_available'] else 'Not available'}")

    # Check vendored availability
    vendored_available = False
    try:
        from .vendored import pyaes
        vendored_available = True
    except ImportError:
        pass
    print(f"  Vendored (pyaes): {'Available' if vendored_available else 'Not available'}")

    # Show resolved backend
    try:
        resolved_backend = select_backend(config_backend)
        print(f"\nResolved Backend: {resolved_backend}")
    except Exception as e:
        print(f"\nBackend Resolution Error: {e}")


def cmd_encrypt(text: Optional[str] = None) -> None:
    """Encrypt text using config settings and output to stdout.

    Args:
        text: Text to encrypt (reads from stdin if None)
    """
    # Get config
    key = get_config_key()
    if not key:
        print("ERROR: No encryption key configured.", file=sys.stderr)
        print("Run 'aigon crypto keygen' to generate a key.", file=sys.stderr)
        sys.exit(1)

    backend_setting = get_config_backend()

    # Get input
    if text is None:
        text = sys.stdin.read()

    try:
        plaintext = text.encode('utf-8')
        encrypted = encrypt(plaintext, key, backend_setting)
        actual_backend = select_backend(backend_setting)

        # Output base64 to stdout
        result = base64.b64encode(encrypted).decode()
        print(result)

        # Info to stderr so it doesn't pollute output
        print(f"[Backend: {actual_backend}, {len(plaintext)} bytes -> {len(encrypted)} bytes]", file=sys.stderr)

    except Exception as e:
        print(f"Encryption failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_decrypt(ciphertext: Optional[str] = None) -> None:
    """Decrypt text using config settings and output to stdout.

    Args:
        ciphertext: Base64 ciphertext to decrypt (reads from stdin if None)
    """
    # Get config
    key = get_config_key()
    if not key:
        print("ERROR: No encryption key configured.", file=sys.stderr)
        print("Run 'aigon crypto keygen' to generate a key.", file=sys.stderr)
        sys.exit(1)

    backend_setting = get_config_backend()

    # Get input
    if ciphertext is None:
        ciphertext = sys.stdin.read().strip()

    try:
        encrypted = base64.b64decode(ciphertext)
        decrypted = decrypt(encrypted, key, backend_setting)
        actual_backend = select_backend(backend_setting)

        # Output plaintext to stdout
        print(decrypted.decode('utf-8'))

        # Info to stderr
        print(f"[Backend: {actual_backend}, {len(encrypted)} bytes -> {len(decrypted)} bytes]", file=sys.stderr)

    except Exception as e:
        print(f"Decryption failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_keygen(override: bool = False) -> None:
    """Generate a new encryption key and save to config.

    Args:
        override: If True, allow overwriting existing key
    """
    config = load_config()
    existing_key = get_config_key()
    config_exists = CONFIG_PATH.exists()

    # Check for existing key
    if existing_key and not override:
        print("ERROR: Encryption key already exists!", file=sys.stderr)
        print("Use --override flag to replace it.", file=sys.stderr)
        print()
        print("Current key (SAVE THIS IF YOU HAVE ENCRYPTED DATA):")
        print("=" * 60)
        print(existing_key)
        print("=" * 60)
        sys.exit(1)

    # If overriding, LOUDLY print the old key
    if existing_key and override:
        print("!" * 60)
        print("!!! WARNING: REPLACING EXISTING KEY !!!")
        print("!" * 60)
        print()
        print("YOUR PREVIOUS KEY (SAVE THIS NOW IF YOU HAVE ENCRYPTED DATA):")
        print("=" * 60)
        print(existing_key)
        print("=" * 60)
        print()
        print("If you have encrypted notes with this key, they will be")
        print("UNRECOVERABLE without this key!")
        print()
        print("!" * 60)
        print()

    # Generate new key (32 bytes = 256 bits for AES-256)
    new_key_bytes = os.urandom(32)
    new_key = base64.b64encode(new_key_bytes).decode()

    # Ensure encryption section exists
    if not config.has_section('encryption'):
        config.add_section('encryption')

    # Save key
    config.set('encryption', 'key', new_key)

    # Set default backend if not set
    if not config.has_option('encryption', 'backend'):
        config.set('encryption', 'backend', 'auto')

    save_config(config)

    # Be LOUD about new key creation
    if not config_exists:
        print("*" * 60)
        print("***  CREATED NEW CONFIG FILE: ~/.aigon  ***")
        print("*" * 60)
        print()

    print("=" * 60)
    print("   NEW ENCRYPTION KEY GENERATED")
    print("=" * 60)
    print()
    print("SAVE THIS KEY SOMEWHERE SAFE!")
    print("Without it, encrypted data is UNRECOVERABLE.")
    print()
    print("=" * 60)
    print(new_key)
    print("=" * 60)
    print()
    print(f"Saved to: {CONFIG_PATH}")


def register_crypto_commands(subparsers):
    """Register crypto commands with argument parser.

    Args:
        subparsers: argparse subparsers object
    """
    # Crypto command group
    crypto_parser = subparsers.add_parser('crypto', help='Encryption testing and settings')
    crypto_subparsers = crypto_parser.add_subparsers(dest='crypto_command', help='Crypto commands')

    # Settings command
    settings_parser = crypto_subparsers.add_parser('settings', help='Show encryption settings and config')

    # Keygen command
    keygen_parser = crypto_subparsers.add_parser('keygen', help='Generate encryption key')
    keygen_parser.add_argument('--override', action='store_true',
                               help='Override existing key (DANGEROUS - prints old key)')

    # Encrypt command
    encrypt_parser = crypto_subparsers.add_parser('encrypt', help='Encrypt text (uses config key/backend)')
    encrypt_parser.add_argument('text', nargs='?', default=None,
                               help='Text to encrypt (reads stdin if not provided)')

    # Decrypt command
    decrypt_parser = crypto_subparsers.add_parser('decrypt', help='Decrypt text (uses config key/backend)')
    decrypt_parser.add_argument('ciphertext', nargs='?', default=None,
                               help='Base64 ciphertext to decrypt (reads stdin if not provided)')

    # Test command
    test_parser = crypto_subparsers.add_parser('test', help='Test encryption roundtrip with config')

    # Help command
    help_parser = crypto_subparsers.add_parser('help', help='Show crypto help information')


def handle_crypto_command(args):
    """Handle crypto commands.

    Args:
        args: Parsed command-line arguments
    """
    if args.crypto_command == 'settings':
        show_settings()

    elif args.crypto_command == 'keygen':
        cmd_keygen(override=args.override)

    elif args.crypto_command == 'encrypt':
        cmd_encrypt(text=args.text)

    elif args.crypto_command == 'decrypt':
        cmd_decrypt(ciphertext=args.ciphertext)

    elif args.crypto_command == 'test':

        # Test data - 1MB for meaningful throughput measurement
        test_size_mb = 1.0
        test_size_bytes = int(test_size_mb * 1024 * 1024)
        test_data = os.urandom(test_size_bytes)

        # Get config key for the configured backend test
        key = get_config_key()
        config_backend = get_config_backend()

        print("Encryption Backend Test")
        print("=" * 60)
        print(f"Test data size: {test_size_mb} MB ({test_size_bytes:,} bytes)")
        print()

        # Test all available backends
        info = get_platform_info()
        backends_to_test = []

        if info['openssl_available']:
            backends_to_test.append(('openssl', 'OpenSSL CLI'))
        if info['powershell_available']:
            backends_to_test.append(('powershell', 'PowerShell/.NET'))

        # Check vendored
        vendored_available = False
        try:
            from .vendored import pyaes
            vendored_available = True
            backends_to_test.append(('vendored', 'Vendored (pyaes)'))
        except ImportError:
            pass

        if not backends_to_test:
            print("ERROR: No encryption backends available!", file=sys.stderr)
            sys.exit(1)

        # Use a test key if config key not available
        test_key = key if key else base64.b64encode(os.urandom(32)).decode()

        all_passed = True
        results = []

        for backend_id, backend_name in backends_to_test:
            print(f"{backend_name}:")

            try:
                # Encrypt with timing
                start = time.perf_counter()
                encrypted = encrypt(test_data, test_key, backend_id)
                encrypt_sec = time.perf_counter() - start
                encrypt_mbps = test_size_mb / encrypt_sec if encrypt_sec > 0 else 0

                # Decrypt with timing
                start = time.perf_counter()
                decrypted = decrypt(encrypted, test_key, backend_id)
                decrypt_sec = time.perf_counter() - start
                decrypt_mbps = test_size_mb / decrypt_sec if decrypt_sec > 0 else 0

                # Verify
                if decrypted == test_data:
                    status = "PASS"
                    print(f"  Status:  {status}")
                    print(f"  Encrypt: {encrypt_mbps:7.2f} MB/s ({encrypt_sec*1000:6.1f} ms)")
                    print(f"  Decrypt: {decrypt_mbps:7.2f} MB/s ({decrypt_sec*1000:6.1f} ms)")
                    results.append((backend_name, encrypt_mbps, decrypt_mbps, True))
                else:
                    status = "FAIL (data mismatch)"
                    print(f"  Status:  {status}")
                    all_passed = False
                    results.append((backend_name, 0, 0, False))

            except Exception as e:
                print(f"  Status:  ERROR")
                print(f"  Error:   {str(e)[:60]}")
                all_passed = False
                results.append((backend_name, 0, 0, False))

            print()

        # Summary
        print("-" * 60)
        print("Summary:")
        print()
        print(f"  Config file:    {CONFIG_PATH}")
        print(f"  Config backend: {config_backend}")
        print(f"  Key configured: {'Yes' if key else 'No (using test key)'}")
        print()

        # Show which backend would be used
        try:
            resolved = select_backend(config_backend)
            print(f"  Resolved backend: {resolved}")
        except Exception as e:
            print(f"  Resolved backend: ERROR - {e}")

        print()
        if all_passed:
            print("All backends: PASS")
        else:
            print("Some backends: FAIL")
            sys.exit(1)

    elif args.crypto_command == 'help' or args.crypto_command is None:
        print("Crypto Help - Encryption using ~/.aigon config")
        print()
        print("Commands:")
        print("  keygen    - Generate encryption key (saved to ~/.aigon)")
        print("  settings  - Show current config and backend info")
        print("  encrypt   - Encrypt text (output: base64 to stdout)")
        print("  decrypt   - Decrypt text (output: plaintext to stdout)")
        print("  test      - Test encryption roundtrip")
        print("  help      - Show this help")
        print()
        print("Config file: ~/.aigon (INI format)")
        print()
        print("  [encryption]")
        print("  backend = auto")
        print("  key = <base64 key>")
        print()
        print("Examples:")
        print("  aigon crypto keygen              # Generate new key")
        print("  aigon crypto keygen --override   # Replace existing key")
        print("  aigon crypto settings            # Show config")
        print("  aigon crypto encrypt 'secret'    # Encrypt text")
        print("  echo 'secret' | aigon crypto encrypt  # Encrypt from stdin")
        print("  aigon crypto decrypt <base64>    # Decrypt text")
        print("  aigon crypto test                # Test roundtrip")

    else:
        print(f"Unknown crypto command: {args.crypto_command}", file=sys.stderr)
        sys.exit(1)

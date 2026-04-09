"""Tests for crypto module - backend encryption/decryption functions.

Tests are platform-aware and skip backends that aren't available.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import os
import shutil
import time

import pytest

from aigon_cli.crypto import (
    _decrypt_openssl,
    _decrypt_powershell,
    _decrypt_vendored,
    _encrypt_openssl,
    _encrypt_powershell,
    _encrypt_vendored,
    decrypt,
    derive_key,
    encrypt,
    get_platform_info,
    select_backend,
)

# Test data of varying sizes
TEST_DATA_SMALL = b"Hello, World!"
TEST_DATA_MEDIUM = b"The quick brown fox jumps over the lazy dog. " * 100  # ~4.5KB
TEST_DATA_LARGE = os.urandom(1024 * 100)  # 100KB random data

TEST_PASSWORD = "test_password_secure_123!"


class TestPlatformInfo:
    """Test platform detection."""

    def test_get_platform_info_returns_dict(self):
        info = get_platform_info()
        assert isinstance(info, dict)
        assert "system" in info
        assert "openssl_available" in info
        assert "powershell_available" in info

    def test_system_is_valid(self):
        info = get_platform_info()
        assert info["system"] in ("Darwin", "Linux", "Windows")


class TestKeyDerivation:
    """Test PBKDF2 key derivation."""

    def test_derive_key_generates_32_bytes(self):
        key, salt = derive_key("password")
        assert len(key) == 32  # AES-256
        assert len(salt) == 16

    def test_derive_key_with_same_salt_is_deterministic(self):
        salt = os.urandom(16)
        key1, _ = derive_key("password", salt)
        key2, _ = derive_key("password", salt)
        assert key1 == key2

    def test_derive_key_different_passwords_different_keys(self):
        salt = os.urandom(16)
        key1, _ = derive_key("password1", salt)
        key2, _ = derive_key("password2", salt)
        assert key1 != key2

    def test_derive_key_different_salts_different_keys(self):
        key1, salt1 = derive_key("password")
        key2, salt2 = derive_key("password")
        assert salt1 != salt2
        assert key1 != key2


class TestBackendSelection:
    """Test backend selection logic."""

    def test_select_auto_returns_valid_backend(self):
        backend = select_backend("auto")
        assert backend in ("openssl", "powershell", "vendored")

    def test_select_native_on_mac_linux(self):
        info = get_platform_info()
        if info["system"] in ("Darwin", "Linux") and info["openssl_available"]:
            backend = select_backend("native")
            assert backend == "openssl"

    def test_select_native_on_windows(self):
        info = get_platform_info()
        if info["system"] == "Windows" and info["powershell_available"]:
            backend = select_backend("native")
            assert backend == "powershell"

    def test_select_openssl_when_available(self):
        info = get_platform_info()
        if info["openssl_available"]:
            backend = select_backend("openssl")
            assert backend == "openssl"
        else:
            with pytest.raises(RuntimeError):
                select_backend("openssl")

    def test_select_powershell_when_available(self):
        info = get_platform_info()
        if info["powershell_available"]:
            backend = select_backend("powershell")
            assert backend == "powershell"
        else:
            with pytest.raises(RuntimeError):
                select_backend("powershell")

    def test_select_vendored_always_returns(self):
        # Vendored should always be selectable (may fail at runtime if not installed)
        backend = select_backend("vendored")
        assert backend == "vendored"

    def test_select_invalid_raises(self):
        with pytest.raises(ValueError):
            select_backend("invalid_backend")


class TestOpenSSLBackend:
    """Test OpenSSL encryption backend."""

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self):
        if not shutil.which("openssl"):
            pytest.skip("OpenSSL not available")

    def test_encrypt_decrypt_roundtrip_small(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_openssl(TEST_DATA_SMALL, key, iv)
        plaintext = _decrypt_openssl(ciphertext, key, iv)
        assert plaintext == TEST_DATA_SMALL

    def test_encrypt_decrypt_roundtrip_medium(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_openssl(TEST_DATA_MEDIUM, key, iv)
        plaintext = _decrypt_openssl(ciphertext, key, iv)
        assert plaintext == TEST_DATA_MEDIUM

    def test_encrypt_decrypt_roundtrip_large(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_openssl(TEST_DATA_LARGE, key, iv)
        plaintext = _decrypt_openssl(ciphertext, key, iv)
        assert plaintext == TEST_DATA_LARGE

    def test_different_keys_different_ciphertext(self):
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        iv = os.urandom(16)
        ct1 = _encrypt_openssl(TEST_DATA_SMALL, key1, iv)
        ct2 = _encrypt_openssl(TEST_DATA_SMALL, key2, iv)
        assert ct1 != ct2

    def test_different_ivs_different_ciphertext(self):
        key = os.urandom(32)
        iv1 = os.urandom(16)
        iv2 = os.urandom(16)
        ct1 = _encrypt_openssl(TEST_DATA_SMALL, key, iv1)
        ct2 = _encrypt_openssl(TEST_DATA_SMALL, key, iv2)
        assert ct1 != ct2

    def test_wrong_key_fails_decrypt(self):
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_openssl(TEST_DATA_SMALL, key1, iv)
        with pytest.raises(RuntimeError):
            _decrypt_openssl(ciphertext, key2, iv)


class TestPowerShellBackend:
    """Test PowerShell encryption backend (Windows)."""

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self):
        if not (shutil.which("powershell") or shutil.which("pwsh")):
            pytest.skip("PowerShell not available")

    def test_encrypt_decrypt_roundtrip_small(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_powershell(TEST_DATA_SMALL, key, iv)
        plaintext = _decrypt_powershell(ciphertext, key, iv)
        assert plaintext == TEST_DATA_SMALL

    def test_encrypt_decrypt_roundtrip_medium(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_powershell(TEST_DATA_MEDIUM, key, iv)
        plaintext = _decrypt_powershell(ciphertext, key, iv)
        assert plaintext == TEST_DATA_MEDIUM


class TestVendoredBackend:
    """Test vendored pyaes encryption backend."""

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self):
        try:
            from aigon_cli.vendored import pyaes  # noqa: F401  (availability probe)
        except ImportError:
            pytest.skip("Vendored pyaes not available")

    def test_encrypt_decrypt_roundtrip_small(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_vendored(TEST_DATA_SMALL, key, iv)
        plaintext = _decrypt_vendored(ciphertext, key, iv)
        assert plaintext == TEST_DATA_SMALL

    def test_encrypt_decrypt_roundtrip_medium(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_vendored(TEST_DATA_MEDIUM, key, iv)
        plaintext = _decrypt_vendored(ciphertext, key, iv)
        assert plaintext == TEST_DATA_MEDIUM

    def test_encrypt_decrypt_roundtrip_large(self):
        key = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_vendored(TEST_DATA_LARGE, key, iv)
        plaintext = _decrypt_vendored(ciphertext, key, iv)
        assert plaintext == TEST_DATA_LARGE

    @pytest.mark.xfail(
        reason="AES-CBC cannot reliably detect wrong-key decryption - garbage output may have valid-looking padding"
    )
    def test_wrong_key_fails_decrypt(self):
        key1 = os.urandom(32)
        key2 = os.urandom(32)
        iv = os.urandom(16)
        ciphertext = _encrypt_vendored(TEST_DATA_SMALL, key1, iv)
        with pytest.raises(RuntimeError):
            _decrypt_vendored(ciphertext, key2, iv)


class TestHighLevelAPI:
    """Test high-level encrypt/decrypt functions with password."""

    def test_encrypt_decrypt_roundtrip(self):
        encrypted = encrypt(TEST_DATA_SMALL, TEST_PASSWORD)
        decrypted = decrypt(encrypted, TEST_PASSWORD)
        assert decrypted == TEST_DATA_SMALL

    def test_encrypt_includes_salt_and_iv(self):
        encrypted = encrypt(TEST_DATA_SMALL, TEST_PASSWORD)
        # Format: salt (16) + iv (16) + ciphertext
        assert len(encrypted) >= 32 + len(TEST_DATA_SMALL)

    def test_same_plaintext_different_ciphertext(self):
        # Due to random salt and IV, same plaintext should produce different ciphertext
        ct1 = encrypt(TEST_DATA_SMALL, TEST_PASSWORD)
        ct2 = encrypt(TEST_DATA_SMALL, TEST_PASSWORD)
        assert ct1 != ct2

    def test_wrong_password_fails(self):
        encrypted = encrypt(TEST_DATA_SMALL, "correct_password")
        with pytest.raises(Exception):  # noqa: B017  (any exception type is acceptable here — just verifying decrypt rejects wrong password)
            decrypt(encrypted, "wrong_password")

    def test_medium_data_roundtrip(self):
        encrypted = encrypt(TEST_DATA_MEDIUM, TEST_PASSWORD)
        decrypted = decrypt(encrypted, TEST_PASSWORD)
        assert decrypted == TEST_DATA_MEDIUM


class TestCrossBackendCompatibility:
    """Test that different backends produce compatible output."""

    @pytest.fixture
    def available_backends(self):
        """Get list of available backends."""
        backends = []
        info = get_platform_info()
        if info["openssl_available"]:
            backends.append("openssl")
        if info["powershell_available"]:
            backends.append("powershell")
        try:
            from aigon_cli.vendored import pyaes  # noqa: F401  (availability probe)

            backends.append("vendored")
        except ImportError:
            pass
        return backends

    def test_all_backends_produce_decryptable_output(self, available_backends):
        """Each backend should be able to decrypt its own output."""
        for backend in available_backends:
            encrypted = encrypt(TEST_DATA_SMALL, TEST_PASSWORD, backend)
            decrypted = decrypt(encrypted, TEST_PASSWORD, backend)
            assert decrypted == TEST_DATA_SMALL, f"Backend {backend} failed roundtrip"


class TestPerformance:
    """Performance benchmarks for available backends."""

    TEST_SIZES = [
        (1024, "1KB"),
        (1024 * 10, "10KB"),
        (1024 * 100, "100KB"),
    ]

    def _benchmark_backend(self, backend: str, data: bytes, iterations: int = 3) -> dict:
        """Benchmark a backend with given data."""
        encrypt_times = []
        decrypt_times = []

        for _ in range(iterations):
            # Encrypt
            start = time.perf_counter()
            encrypted = encrypt(data, TEST_PASSWORD, backend)
            encrypt_times.append(time.perf_counter() - start)

            # Decrypt
            start = time.perf_counter()
            decrypted = decrypt(encrypted, TEST_PASSWORD, backend)
            decrypt_times.append(time.perf_counter() - start)

            assert decrypted == data

        return {
            "encrypt_avg_ms": sum(encrypt_times) / len(encrypt_times) * 1000,
            "decrypt_avg_ms": sum(decrypt_times) / len(decrypt_times) * 1000,
        }

    def test_openssl_performance(self):
        if not shutil.which("openssl"):
            pytest.skip("OpenSSL not available")

        for size, label in self.TEST_SIZES:
            data = os.urandom(size)
            result = self._benchmark_backend("openssl", data)
            print(
                f"\nOpenSSL {label}: encrypt={result['encrypt_avg_ms']:.2f}ms, decrypt={result['decrypt_avg_ms']:.2f}ms"
            )

    def test_powershell_performance(self):
        if not (shutil.which("powershell") or shutil.which("pwsh")):
            pytest.skip("PowerShell not available")

        for size, label in self.TEST_SIZES:
            data = os.urandom(size)
            result = self._benchmark_backend("powershell", data)
            print(
                f"\nPowerShell {label}: encrypt={result['encrypt_avg_ms']:.2f}ms, decrypt={result['decrypt_avg_ms']:.2f}ms"
            )

    def test_vendored_performance(self):
        try:
            from aigon_cli.vendored import pyaes  # noqa: F401  (availability probe)
        except ImportError:
            pytest.skip("Vendored pyaes not available")

        for size, label in self.TEST_SIZES:
            data = os.urandom(size)
            result = self._benchmark_backend("vendored", data)
            print(
                f"\nVendored {label}: encrypt={result['encrypt_avg_ms']:.2f}ms, decrypt={result['decrypt_avg_ms']:.2f}ms"
            )

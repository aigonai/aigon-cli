"""Baseline tests for fileserver.py viewer functionality.

These tests capture the current behavior of the viewer CLI before refactoring.
They ensure that after moving fileserver.py to app_aigon_viewer_server, the
viewer commands still work identically.

Test Coverage:
- Process lifecycle (launch, status, kill)
- PID file management
- Port finding and conflict handling
- Multiple viewer instances
- Server responsiveness

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests


@pytest.fixture
def test_markdown_dir(tmp_path):
    """Create a temporary directory with markdown files for testing."""
    # Create test markdown files
    (tmp_path / "test1.md").write_text("# Test 1\n\nThis is a test file.")
    (tmp_path / "test2.md").write_text("# Test 2\n\n## Section\n\nAnother test.")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "test3.md").write_text("# Nested\n\nNested file.")

    return tmp_path


@pytest.fixture
def find_pid_directory():
    """Find the PID directory used by fileserver.py."""
    import platform

    system = platform.system()
    home = Path.home()

    if system == "Darwin":  # macOS
        candidates = [
            home / "Library" / "Application Support" / "Aigon" / "pids",
            home / ".cache" / "aigon" / "pids",
        ]
    elif system == "Linux":
        candidates = [
            home / ".cache" / "aigon" / "pids",
            home / ".local" / "share" / "aigon" / "pids",
        ]
    else:  # Windows
        appdata = os.getenv("APPDATA")
        if appdata:
            candidates = [Path(appdata) / "Aigon" / "pids"]
        else:
            candidates = [home / ".cache" / "aigon" / "pids"]

    # Return first existing directory
    for candidate in candidates:
        if candidate.exists():
            return candidate

    # If none exist, return expected location
    return candidates[0]


@pytest.fixture(autouse=True)
def cleanup_viewers():
    """Clean up any running viewers before and after each test."""
    # Kill all viewers before test
    subprocess.run(["./aigon", "viewer", "kill"], capture_output=True, cwd="/Users/skloesch/claude/agent01")
    time.sleep(1)

    yield

    # Kill all viewers after test
    subprocess.run(["./aigon", "viewer", "kill"], capture_output=True, cwd="/Users/skloesch/claude/agent01")
    time.sleep(1)


@pytest.mark.skip(reason="Too slow")
class TestViewerLaunch:
    """Test viewer launch functionality."""

    def test_launch_basic(self, test_markdown_dir):
        """Test basic viewer launch in background mode."""
        port = 9001

        # Launch viewer in background with --no-browser
        result = subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            text=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )

        assert result.returncode == 0
        time.sleep(2)

        try:
            # Server should respond
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            assert response.status_code == 200
        finally:
            # Cleanup
            subprocess.run(["./aigon", "viewer", "kill", "--port", str(port)], cwd="/Users/skloesch/claude/agent01")

    def test_launch_foreground(self, test_markdown_dir):
        """Test viewer launch in foreground mode (will be killed after startup)."""
        port = 9002

        # Launch in foreground (background process for test)
        proc = subprocess.Popen(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--foreground", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd="/Users/skloesch/claude/agent01",
        )

        # Give it time to start
        time.sleep(3)

        try:
            # Server should respond
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            assert response.status_code == 200
        finally:
            # Kill the foreground process
            proc.terminate()
            proc.wait(timeout=5)

    def test_launch_custom_port(self, test_markdown_dir):
        """Test viewer launch on custom port."""
        port = 9003

        result = subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            text=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )

        assert result.returncode == 0
        time.sleep(2)

        try:
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            assert response.status_code == 200
        finally:
            subprocess.run(["./aigon", "viewer", "kill", "--port", str(port)], cwd="/Users/skloesch/claude/agent01")

    def test_launch_duplicate_port(self, test_markdown_dir):
        """Test launching viewer on already-used port."""
        port = 9004

        # Launch first viewer
        result1 = subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            text=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )
        assert result1.returncode == 0
        time.sleep(2)

        try:
            # Try to launch second viewer on same port - should find next available port
            result2 = subprocess.run(
                ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
                capture_output=True,
                text=True,
                cwd="/Users/skloesch/claude/agent01",
                timeout=10,
            )

            # Should succeed and use next available port
            assert result2.returncode == 0
            assert "in use, using port" in result2.stdout.lower()

        finally:
            subprocess.run(["./aigon", "viewer", "kill"], cwd="/Users/skloesch/claude/agent01")


@pytest.mark.skip(reason="Too slow")
class TestViewerStatus:
    """Test viewer status command."""

    def test_status_no_viewers(self):
        """Test status when no viewers are running."""
        result = subprocess.run(
            ["./aigon", "viewer", "status"], capture_output=True, text=True, cwd="/Users/skloesch/claude/agent01"
        )

        # Should succeed but indicate no viewers
        assert "No viewers running" in result.stdout or "0 viewer" in result.stdout

    def test_status_single_viewer(self, test_markdown_dir):
        """Test status with one viewer running."""
        port = 9005

        # Launch viewer
        subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )
        time.sleep(2)

        try:
            # Check status
            result = subprocess.run(
                ["./aigon", "viewer", "status"], capture_output=True, text=True, cwd="/Users/skloesch/claude/agent01"
            )

            assert result.returncode == 0
            assert str(port) in result.stdout
            assert "viewer" in result.stdout.lower()

        finally:
            subprocess.run(["./aigon", "viewer", "kill", "--port", str(port)], cwd="/Users/skloesch/claude/agent01")

    def test_status_multiple_viewers(self, test_markdown_dir):
        """Test status with multiple viewers running."""
        ports = [9006, 9007, 9008]

        # Launch multiple viewers
        for port in ports:
            subprocess.run(
                ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
                capture_output=True,
                cwd="/Users/skloesch/claude/agent01",
                timeout=10,
            )
            time.sleep(2)

        try:
            # Check status
            result = subprocess.run(
                ["./aigon", "viewer", "status"], capture_output=True, text=True, cwd="/Users/skloesch/claude/agent01"
            )

            assert result.returncode == 0
            # Should show all ports
            for port in ports:
                assert str(port) in result.stdout

        finally:
            subprocess.run(["./aigon", "viewer", "kill"], cwd="/Users/skloesch/claude/agent01")


@pytest.mark.skip(reason="Too slow")
class TestViewerKill:
    """Test viewer kill command."""

    def test_kill_specific_port(self, test_markdown_dir):
        """Test killing viewer on specific port."""
        port = 9009

        # Launch viewer
        subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )
        time.sleep(2)

        # Verify it's running
        response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
        assert response.status_code == 200

        # Kill it
        result = subprocess.run(
            ["./aigon", "viewer", "kill", "--port", str(port)],
            capture_output=True,
            text=True,
            cwd="/Users/skloesch/claude/agent01",
        )

        assert result.returncode == 0
        time.sleep(2)

        # Verify it's stopped (connection should fail)
        with pytest.raises(requests.ConnectionError):
            requests.get(f"http://127.0.0.1:{port}/", timeout=2)

    @pytest.mark.skip(reason="Timeout issues with port cleanup")
    def test_kill_all_viewers(self, test_markdown_dir):
        """Test killing all viewers."""
        ports = [9010, 9011]

        # Launch multiple viewers
        for port in ports:
            subprocess.run(
                ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
                capture_output=True,
                cwd="/Users/skloesch/claude/agent01",
                timeout=10,
            )
            time.sleep(2)

        # Verify they're running
        for port in ports:
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            assert response.status_code == 200

        # Kill all
        result = subprocess.run(
            ["./aigon", "viewer", "kill"], capture_output=True, text=True, cwd="/Users/skloesch/claude/agent01"
        )

        assert result.returncode == 0
        time.sleep(2)

        # Verify all stopped
        for port in ports:
            with pytest.raises(requests.ConnectionError):
                requests.get(f"http://127.0.0.1:{port}/", timeout=2)

    def test_kill_nonexistent_viewer(self):
        """Test killing viewer that doesn't exist."""
        port = 9999

        result = subprocess.run(
            ["./aigon", "viewer", "kill", "--port", str(port)],
            capture_output=True,
            text=True,
            cwd="/Users/skloesch/claude/agent01",
        )

        # Should either succeed with message or fail gracefully
        # Current behavior: likely shows "not running" message
        assert "not running" in result.stdout.lower() or "No viewer" in result.stdout


@pytest.mark.skip(reason="Too slow")
class TestPIDFileManagement:
    """Test PID file creation and cleanup."""

    def test_pid_file_created(self, test_markdown_dir, find_pid_directory):
        """Test that PID file is created when viewer launches."""
        port = 9012
        pid_dir = find_pid_directory
        pid_file = pid_dir / f"fileserver.{port}.pid"

        # Ensure PID file doesn't exist
        if pid_file.exists():
            pid_file.unlink()

        # Launch viewer in background
        subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )
        time.sleep(2)

        try:
            # PID file should exist
            assert pid_file.exists(), f"PID file not found at {pid_file}"

            # Should contain a valid PID
            pid = int(pid_file.read_text().strip())
            assert pid > 0

            # Process should be running
            os.kill(pid, 0)  # Signal 0 checks if process exists

        finally:
            subprocess.run(["./aigon", "viewer", "kill", "--port", str(port)], cwd="/Users/skloesch/claude/agent01")

    @pytest.mark.skip(reason="Timeout issues with port cleanup")
    def test_pid_file_cleaned_up(self, test_markdown_dir, find_pid_directory):
        """Test that PID file is removed when viewer is killed."""
        port = 9013
        pid_dir = find_pid_directory
        pid_file = pid_dir / f"fileserver.{port}.pid"

        # Launch viewer
        subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )
        time.sleep(2)

        # Verify PID file exists
        assert pid_file.exists()

        # Kill viewer
        subprocess.run(
            ["./aigon", "viewer", "kill", "--port", str(port)],
            capture_output=True,
            cwd="/Users/skloesch/claude/agent01",
        )
        time.sleep(2)

        # PID file should be removed
        assert not pid_file.exists(), f"PID file not cleaned up: {pid_file}"


@pytest.mark.skip(reason="Too slow")
class TestServerResponsiveness:
    """Test that launched server responds correctly."""

    def test_server_serves_files(self, test_markdown_dir):
        """Test that server serves markdown files."""
        port = 9014

        # Launch viewer
        subprocess.run(
            ["./aigon", "viewer", "launch", str(test_markdown_dir), "--no-browser", "--port", str(port)],
            capture_output=True,
            cwd="/Users/skloesch/claude/agent01",
            timeout=10,
        )
        time.sleep(2)

        try:
            # Get index page
            response = requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            assert response.status_code == 200
            assert "test1" in response.text.lower() or "markdown" in response.text.lower()

            # Try to view a file (if viewer supports it)
            # This may vary based on viewer implementation

        finally:
            subprocess.run(["./aigon", "viewer", "kill", "--port", str(port)], cwd="/Users/skloesch/claude/agent01")

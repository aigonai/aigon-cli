"""
Basic functionality tests for REST API CLI client.

These tests verify core functionality without requiring a running server.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""
import pytest
from unittest.mock import Mock, patch
from aigon_cli.client import AigonClient


def test_aigon_client_initialization():
    """Test that AigonClient can be initialized properly."""
    # Test basic initialization with mock to avoid real connection
    with patch('aigon_cli.client.requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = AigonClient(base_url="http://test", api_token="test_token")

        # Should have required attributes
        assert client.base_url == "http://test"
        assert hasattr(client, 'headers')


def test_aigon_client_default_url():
    """Test that AigonClient uses default URL when none provided."""
    with patch('aigon_cli.client.requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = AigonClient()

        # Should use default production URL
        assert client.base_url == "https://api.aigon.ai"


def test_aigon_client_api_methods_exist():
    """Test that all expected API methods exist."""
    with patch('aigon_cli.client.requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = AigonClient()

        # File operations
        assert hasattr(client, 'list_files')
        assert hasattr(client, 'read_file')
        assert hasattr(client, 'write_file')
        assert hasattr(client, 'create_file')
        assert hasattr(client, 'delete_file')
        assert hasattr(client, 'archive_file')
        assert hasattr(client, 'unarchive_file')

        # Note operations
        assert hasattr(client, 'search_notes')
        assert hasattr(client, 'get_recent_notes')

        # System operations
        assert hasattr(client, 'get_api_info')
        assert hasattr(client, 'get_health')
        assert hasattr(client, 'list_endpoints')


def test_aigon_client_authentication_headers():
    """Test that authentication headers are set correctly."""
    with patch('aigon_cli.client.requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = AigonClient(api_token="test_token_123")

        # Should have headers dict with auth
        assert client.headers == {
            'Authorization': 'Bearer test_token_123',
            'Content-Type': 'application/json'
        }


class TestSaveReportVisibility:
    """Tests for report visibility functionality in save_report."""

    def test_save_report_accepts_visibility_parameters(self):
        """Test that save_report method accepts event and visible_to_participants parameters."""
        with patch('aigon_cli.client.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            client = AigonClient(api_token="test_token")

            # Check method signature includes visibility params
            import inspect
            sig = inspect.signature(client.save_report)
            param_names = list(sig.parameters.keys())

            assert 'event' in param_names
            assert 'visible_to_participants' in param_names

    def test_save_report_sends_visibility_in_body(self):
        """Test that save_report includes visibility in request body."""
        with patch('aigon_cli.client.requests.get') as mock_get, \
             patch('aigon_cli.client.requests.post') as mock_post:
            # Mock initialization
            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get.return_value = mock_get_response

            # Mock save_report call
            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {'unique_id': 'test123'}
            mock_post.return_value = mock_post_response

            client = AigonClient(api_token="test_token")
            client.save_report(
                content="# Test",
                event="hackathon",
                visible_to_participants=True
            )

            # Verify the request body
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            body = call_kwargs.kwargs['json']

            assert body['event'] == 'hackathon'
            assert body['visible_to_participants'] is True

    def test_save_report_admin_only(self):
        """Test that visible_to_participants=False creates admin-only report."""
        with patch('aigon_cli.client.requests.get') as mock_get, \
             patch('aigon_cli.client.requests.post') as mock_post:
            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {'unique_id': 'test123'}
            mock_post.return_value = mock_post_response

            client = AigonClient(api_token="test_token")
            client.save_report(
                content="# Test",
                event="hackathon",
                visible_to_participants=False
            )

            body = mock_post.call_args.kwargs['json']
            assert body['visible_to_participants'] is False

    def test_save_report_without_visibility(self):
        """Test that save_report works without visibility parameters."""
        with patch('aigon_cli.client.requests.get') as mock_get, \
             patch('aigon_cli.client.requests.post') as mock_post:
            mock_get_response = Mock()
            mock_get_response.status_code = 200
            mock_get.return_value = mock_get_response

            mock_post_response = Mock()
            mock_post_response.status_code = 200
            mock_post_response.json.return_value = {'unique_id': 'test123'}
            mock_post.return_value = mock_post_response

            client = AigonClient(api_token="test_token")
            client.save_report(content="# Test")

            body = mock_post.call_args.kwargs['json']
            assert 'event' not in body
            assert 'visible_to_participants' not in body

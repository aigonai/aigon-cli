"""
Tests for note sanitization - ensuring internal fields are never exposed.

These tests verify that:
1. The _sanitize_note_for_output() function removes internal fields
2. Search, read, and get_notes_by_id all sanitize JSON output
3. The numeric 'id' field is never exposed to users

(c) Stefan LOESCH 2025-26. All rights reserved.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from aigon_cli.notetaker import (
    _sanitize_note_for_output,
    _format_note_llm,
    _format_note_summary,
    search_notes,
    recent_notes,
    get_notes_by_id
)


class TestSanitizeNoteForOutput:
    """Tests for the _sanitize_note_for_output function."""

    def test_removes_numeric_id(self):
        """Test that numeric id field is removed."""
        note = {
            'id': 12345,
            'unique_id': 'abc123def456',
            'content': 'Test content',
            'content_type': 'text'
        }
        result = _sanitize_note_for_output(note)

        assert 'id' not in result
        assert result['unique_id'] == 'abc123def456'
        assert result['content'] == 'Test content'

    def test_removes_user_id_pk_int(self):
        """Test that user_id_pk_int field is removed."""
        note = {
            'id': 123,
            'user_id_pk_int': 456,
            'unique_id': 'abc123',
            'content': 'Test'
        }
        result = _sanitize_note_for_output(note)

        assert 'user_id_pk_int' not in result
        assert 'id' not in result

    def test_removes_agent_field(self):
        """Test that agent field is removed."""
        note = {
            'id': 123,
            'agent': 'notetaker',
            'unique_id': 'abc123',
            'content': 'Test'
        }
        result = _sanitize_note_for_output(note)

        assert 'agent' not in result

    def test_removes_attachment_internal_fields(self):
        """Test that attachment internal fields are removed."""
        note = {
            'id': 123,
            'unique_id': 'abc123',
            'content': 'Test',
            'att_id': 789,
            'att_filename': 'internal_name.ogg',
            'att_original_filename': 'voice.ogg',
            'att_file_type': 'audio',
            'att_mime_type': 'audio/ogg',
            'att_content_size': 1024
        }
        result = _sanitize_note_for_output(note)

        assert 'att_id' not in result
        assert 'att_filename' not in result
        assert 'att_original_filename' not in result
        assert 'att_file_type' not in result
        assert 'att_mime_type' not in result
        assert 'att_content_size' not in result

    def test_preserves_safe_fields(self):
        """Test that safe fields are preserved."""
        note = {
            'id': 123,
            'unique_id': 'abc123def456',
            'content': 'Test content',
            'content_type': 'text',
            'created_at': 1700000000,
            'exported_at': 1700001000,
            'processed_at': 1700002000,
        }
        result = _sanitize_note_for_output(note)

        assert result['unique_id'] == 'abc123def456'
        assert result['content'] == 'Test content'
        assert result['content_type'] == 'text'
        assert result['created_at'] == 1700000000
        assert result['exported_at'] == 1700001000
        assert result['processed_at'] == 1700002000

    def test_does_not_modify_original(self):
        """Test that original note dict is not modified."""
        note = {
            'id': 123,
            'unique_id': 'abc123',
            'content': 'Test'
        }
        original_keys = set(note.keys())

        result = _sanitize_note_for_output(note)

        # Original should be unchanged
        assert set(note.keys()) == original_keys
        assert note['id'] == 123


class TestFormatNoteLLM:
    """Tests for the _format_note_llm function."""

    def test_includes_unique_id(self):
        """Test that unique_id is included in LLM format."""
        note = {
            'unique_id': 'abc123def456789',
            'content': 'Test content',
            'content_type': 'text'
        }
        result = _format_note_llm(note)

        assert 'abc123' in result  # Short ID
        assert 'abc123def456789' in result  # Full ID

    def test_does_not_include_numeric_id(self):
        """Test that numeric id is NOT included in LLM format."""
        note = {
            'id': 12345,
            'unique_id': 'abc123def456',
            'content': 'Test content',
            'content_type': 'text'
        }
        result = _format_note_llm(note)

        # The numeric ID should NOT appear in the output
        assert '12345' not in result

    def test_includes_content_type(self):
        """Test that content_type is included."""
        note = {
            'unique_id': 'abc123',
            'content': 'Test',
            'content_type': 'audio'
        }
        result = _format_note_llm(note)

        assert 'audio' in result


class TestSearchNotesOutput:
    """Tests for search_notes output sanitization."""

    @patch('aigon_cli.notetaker.AigonClient')
    def test_search_json_output_sanitized(self, mock_client_class):
        """Test that search JSON output is sanitized."""
        # Setup mock client
        mock_client = MagicMock()
        # search_notes returns FTS results (with unique_id)
        mock_client.search_notes.return_value = [
            {
                'unique_id': 'abc123',
                'relevance': 0.5,
            }
        ]
        # get_notes_by_ids returns full note data
        mock_client.get_notes_by_ids.return_value = [
            {
                'id': 123,
                'unique_id': 'abc123',
                'content': 'Test',
                'content_type': 'text',
                'user_id_pk_int': 456,
                'agent': 'notetaker'
            }
        ]

        # Capture stdout
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            search_notes(mock_client, query='test', output_format='json')
            output = mock_stdout.getvalue()

        # Parse output as JSON
        result = json.loads(output)

        # Should be sanitized
        assert len(result) == 1
        assert 'id' not in result[0]
        assert 'user_id_pk_int' not in result[0]
        assert 'agent' not in result[0]
        assert result[0]['unique_id'] == 'abc123'

    @patch('aigon_cli.notetaker.AigonClient')
    def test_search_llm_format_is_default(self, mock_client_class):
        """Test that LLM format is the default for search."""
        mock_client = MagicMock()
        # search_notes returns FTS results (with unique_id)
        mock_client.search_notes.return_value = [
            {
                'unique_id': 'abc123def456',
                'relevance': 0.5,
            }
        ]
        # get_notes_by_ids returns full note data
        mock_client.get_notes_by_ids.return_value = [
            {
                'id': 123,
                'unique_id': 'abc123def456',
                'content': 'Test content',
                'content_type': 'text'
            }
        ]

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            # Don't specify format - should default to llm
            search_notes(mock_client, query='test')
            output = mock_stdout.getvalue()

        # LLM format has specific markers
        assert '--- BEGIN NOTE ---' in output
        assert 'unique_id:' in output
        # Should NOT be JSON
        try:
            json.loads(output)
            pytest.fail("Output should not be valid JSON (should be LLM format)")
        except json.JSONDecodeError:
            pass  # Expected - it's LLM format, not JSON


class TestRecentNotesOutput:
    """Tests for recent_notes output sanitization."""

    @patch('aigon_cli.notetaker.AigonClient')
    def test_recent_json_output_sanitized(self, mock_client_class):
        """Test that recent_notes JSON output is sanitized."""
        mock_client = MagicMock()
        mock_client.get_recent_notes.return_value = [
            {
                'id': 789,
                'unique_id': 'xyz789',
                'content': 'Recent note',
                'content_type': 'text',
                'user_id_pk_int': 123
            }
        ]

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            recent_notes(mock_client, output_format='json')
            output = mock_stdout.getvalue()

        result = json.loads(output)

        assert len(result) == 1
        assert 'id' not in result[0]
        assert 'user_id_pk_int' not in result[0]
        assert result[0]['unique_id'] == 'xyz789'


class TestGetNotesByIdOutput:
    """Tests for get_notes_by_id output sanitization."""

    @patch('aigon_cli.notetaker.AigonClient')
    def test_get_by_id_json_output_sanitized(self, mock_client_class):
        """Test that get_notes_by_id JSON output is sanitized."""
        mock_client = MagicMock()
        mock_client.get_notes_by_ids.return_value = [
            {
                'id': 456,
                'unique_id': 'def456',
                'content': 'Specific note',
                'content_type': 'audio',
                'agent': 'notetaker',
                'att_id': 999
            }
        ]

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            get_notes_by_id(mock_client, unique_ids=['def456'], output_format='json')
            output = mock_stdout.getvalue()

        result = json.loads(output)

        assert len(result) == 1
        assert 'id' not in result[0]
        assert 'agent' not in result[0]
        assert 'att_id' not in result[0]
        assert result[0]['unique_id'] == 'def456'

    @patch('aigon_cli.notetaker.AigonClient')
    def test_get_by_id_llm_format_is_default(self, mock_client_class):
        """Test that LLM format is the default for get_notes_by_id."""
        mock_client = MagicMock()
        mock_client.get_notes_by_ids.return_value = [
            {
                'id': 123,
                'unique_id': 'abc123def456',
                'content': 'Test content',
                'content_type': 'text'
            }
        ]

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            # Don't specify format - should default to llm
            get_notes_by_id(mock_client, unique_ids=['abc123'])
            output = mock_stdout.getvalue()

        # LLM format has specific markers
        assert '--- BEGIN NOTE ---' in output
        assert 'unique_id:' in output


class TestInternalFieldsNeverExposed:
    """Integration tests ensuring internal fields are never exposed."""

    def test_all_internal_fields_in_sanitize_list(self):
        """Test that all known internal fields are in the sanitize list."""
        from aigon_cli.notetaker import _sanitize_note_for_output

        # These fields should NEVER appear in output
        internal_fields = {
            'id',  # Database primary key
            'user_id_pk_int',  # Internal user reference
            'agent',  # Internal agent identifier
            'att_id',  # Attachment internal ID
            'att_filename',  # Internal filename
            'att_original_filename',
            'att_file_type',
            'att_mime_type',
            'att_content_size'
        }

        # Create a note with all internal fields
        note = {field: f'value_{field}' for field in internal_fields}
        note['unique_id'] = 'safe_field'
        note['content'] = 'also_safe'

        result = _sanitize_note_for_output(note)

        # None of the internal fields should be present
        for field in internal_fields:
            assert field not in result, f"Internal field '{field}' was not removed"

        # Safe fields should be preserved
        assert result['unique_id'] == 'safe_field'
        assert result['content'] == 'also_safe'


class TestMarkNotesOutput:
    """Tests for mark_notes output formats."""

    @patch('aigon_cli.notetaker.AigonClient')
    def test_mark_notes_llm_format_is_concise(self, mock_client_class):
        """Test that mark_notes LLM format is very concise."""
        from aigon_cli.notetaker import mark_notes

        mock_client = MagicMock()
        mock_client.mark_notes.return_value = {
            'success': True,
            'batch_size': 3,
            'found_count': 3,
            'requested_count': 3
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mark_notes(mock_client, unique_ids=['abc', 'def', 'ghi'],
                      processed=True, output_format='llm')
            output = mock_stdout.getvalue()

        # LLM format should be very concise - single line
        assert output.strip() == "Marked 3 note(s) as processed"

    @patch('aigon_cli.notetaker.AigonClient')
    def test_mark_notes_json_format_full_details(self, mock_client_class):
        """Test that mark_notes JSON format returns full details."""
        from aigon_cli.notetaker import mark_notes

        mock_client = MagicMock()
        mock_client.mark_notes.return_value = {
            'success': True,
            'batch_size': 2,
            'found_count': 2
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mark_notes(mock_client, unique_ids=['abc', 'def'],
                      processed=True, output_format='json')
            output = mock_stdout.getvalue()

        # JSON format should be full output
        result = json.loads(output)
        assert result['success'] == True
        assert result['batch_size'] == 2

    @patch('aigon_cli.notetaker.AigonClient')
    def test_mark_notes_unprocessed_message(self, mock_client_class):
        """Test that unmark message says 'unprocessed'."""
        from aigon_cli.notetaker import mark_notes

        mock_client = MagicMock()
        mock_client.mark_notes.return_value = {
            'success': True,
            'batch_size': 1
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mark_notes(mock_client, unique_ids=['abc'],
                      processed=False, output_format='llm')
            output = mock_stdout.getvalue()

        assert "unprocessed" in output

    @patch('aigon_cli.notetaker.AigonClient')
    def test_mark_notes_exported_only(self, mock_client_class):
        """Test marking as exported only (without processed)."""
        from aigon_cli.notetaker import mark_notes

        mock_client = MagicMock()
        mock_client.mark_notes.return_value = {
            'success': True,
            'batch_size': 2
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mark_notes(mock_client, unique_ids=['abc', 'def'],
                      exported=True, output_format='llm')
            output = mock_stdout.getvalue()

        assert "exported" in output

    @patch('aigon_cli.notetaker.AigonClient')
    def test_mark_notes_both_flags(self, mock_client_class):
        """Test marking both processed and exported."""
        from aigon_cli.notetaker import mark_notes

        mock_client = MagicMock()
        mock_client.mark_notes.return_value = {
            'success': True,
            'batch_size': 1
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mark_notes(mock_client, unique_ids=['abc'],
                      processed=True, exported=True, output_format='llm')
            output = mock_stdout.getvalue()

        assert "processed" in output
        assert "exported" in output


class TestFileDBListOutput:
    """Tests for filedb list output formats."""

    @patch('aigon_cli.filedb.AigonClient')
    def test_list_files_llm_format_is_concise(self, mock_client_class):
        """Test that list_files LLM format is concise."""
        from aigon_cli.filedb import list_files

        mock_client = MagicMock()
        mock_client.list_files.return_value = {
            'files': [
                {'basename': 'file1', 'version': 3, 'unique_id': 'ABC123DEFG'},
                {'basename': 'file2', 'version': 1, 'unique_id': 'XYZ789HIJK'}
            ]
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            list_files(mock_client, output_format='llm')
            output = mock_stdout.getvalue()

        # Should be concise format with version and 6-char unique_id
        assert '2 file(s):' in output
        assert 'file1 (v3, ABC123)' in output
        assert 'file2 (v1, XYZ789)' in output

    @patch('aigon_cli.filedb.AigonClient')
    def test_list_files_llm_is_default(self, mock_client_class):
        """Test that LLM format is the default for list_files."""
        from aigon_cli.filedb import list_files

        mock_client = MagicMock()
        mock_client.list_files.return_value = {
            'files': [{'basename': 'test', 'version': 1, 'unique_id': 'TEST123456'}]
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            # Don't specify format - should default to llm
            list_files(mock_client)
            output = mock_stdout.getvalue()

        # Should NOT be JSON
        try:
            json.loads(output)
            pytest.fail("Default output should not be JSON (should be LLM format)")
        except json.JSONDecodeError:
            pass  # Expected


class TestFileDBSearchOutput:
    """Tests for filedb search output formats."""

    @patch('aigon_cli.filedb.AigonClient')
    def test_search_files_llm_format_is_concise(self, mock_client_class):
        """Test that search_files LLM format is concise."""
        from aigon_cli.filedb import search_files

        mock_client = MagicMock()
        mock_client.search_files.return_value = {
            'success': True,
            'matches_found': [
                {'basename': 'notes', 'version': 2, 'content': 'Meeting notes from Monday'},
                {'basename': 'todo', 'version': 1, 'content': 'Buy groceries'}
            ],
            'total_matches': 2
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            search_files(mock_client, query='meeting', output_format='llm')
            output = mock_stdout.getvalue()

        # Should be concise format
        assert "2 match(es) for 'meeting'" in output
        assert 'notes (v2)' in output

    @patch('aigon_cli.filedb.AigonClient')
    def test_search_files_llm_is_default(self, mock_client_class):
        """Test that LLM format is the default for search_files."""
        from aigon_cli.filedb import search_files

        mock_client = MagicMock()
        mock_client.search_files.return_value = {
            'success': True,
            'matches_found': [{'basename': 'test', 'version': 1, 'content': 'test'}],
            'total_matches': 1
        }

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            # Don't specify format - should default to llm
            search_files(mock_client, query='test')
            output = mock_stdout.getvalue()

        # Should NOT be JSON
        try:
            json.loads(output)
            pytest.fail("Default output should not be JSON (should be LLM format)")
        except json.JSONDecodeError:
            pass  # Expected


class TestFormatNoteSummary:
    """Tests for the _format_note_summary function."""

    def test_includes_short_id(self):
        """Test that short unique_id is included in summary format."""
        note = {
            "unique_id": "abc123def456789",
            "content": "Test content",
            "content_type": "text",
            "created_at": 1700000000
        }
        result = _format_note_summary(note)

        assert "abc123" in result  # Short ID

    def test_includes_content_length(self):
        """Test that content length (len:) is included."""
        note = {
            "unique_id": "abc123",
            "content": "Hello world",  # 11 characters
            "content_type": "text",
            "created_at": 1700000000
        }
        result = _format_note_summary(note)

        assert "len:11" in result

    def test_includes_summary_when_present(self):
        """Test that summary is included when present."""
        note = {
            "unique_id": "abc123",
            "content": "Full content here",
            "content_type": "text",
            "created_at": 1700000000,
            "summary": "Brief summary of the note"
        }
        result = _format_note_summary(note)

        assert "Brief summary of the note" in result

    def test_shows_placeholder_when_no_summary(self):
        """Test that placeholder is shown when no summary."""
        note = {
            "unique_id": "abc123",
            "content": "Full content",
            "content_type": "text",
            "created_at": 1700000000
        }
        result = _format_note_summary(note)

        assert "(no summary)" in result

    def test_includes_date(self):
        """Test that date is included."""
        note = {
            "unique_id": "abc123",
            "content": "Content",
            "content_type": "text",
            "created_at": 1700000000  # 2023-11-14
        }
        result = _format_note_summary(note)

        assert "20231114" in result  # Date format YYYYMMDD

    def test_does_not_include_content(self):
        """Test that full content is NOT included in summary format."""
        note = {
            "unique_id": "abc123",
            "content": "This is the full content that should not appear verbatim",
            "content_type": "text",
            "created_at": 1700000000,
            "summary": "Just a summary"
        }
        result = _format_note_summary(note)

        # Full content should NOT appear
        assert "This is the full content" not in result
        # But summary and length should
        assert "Just a summary" in result
        assert "len:" in result


"""
Test file that ONLY tests the signature of restapi_cli module components.

This test file ONLY checks:
a) All expected methods and properties are present
b) No unexpected methods or properties exist

This is purely a signature test - it does NOT test functionality.

We are testing the signatures of:
- app.restapi_cli.client module and all classes exported from it

Specifically testing:
- app.restapi_cli.client.AigonClient (REST API client class)

This test checks BOTH public API and internal implementation details (private methods/properties).

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

import inspect

from aigon_cli.client import AigonClient
from tests.utils.signature_test_helpers import assert_signatures_match


def test_aigon_client_signature():
    """Test that AigonClient has exactly the expected methods and properties."""
    # Expected public methods for Aigon client
    expected_public_methods = {
        "create_file",
        "delete_file",
        "get_recent_notes",
        "list_files",
        "read_file",
        "search_notes",
        "search_files",
        "write_file",
        "global_search",
        "get_api_info",
        "get_health",
        "list_endpoints",
        "archive_file",
        "unarchive_file",
        "get_note_by_id",
        "get_notes_by_ids",
        "mark_notes",
        "update_notes",
        "get_attachment",
        "get_attachment_by_unique_id",
        "save_report",
        "share_file",
        "unshare_file",
        "list_shared_files",
        "list_files_i_shared",
        "download_resource",
        "mailbox_reply",
        "mailbox_send",
    }

    # Expected private methods for Aigon client
    expected_private_methods = {"__init__", "_handle_auth_error"}

    # Expected properties
    expected_public_properties = set()
    expected_private_properties = set()

    # Get all methods and properties
    actual_public_methods = set()
    actual_private_methods = set()
    actual_public_properties = set()
    actual_private_properties = set()

    for name, obj in inspect.getmembers(AigonClient):
        is_method = inspect.ismethod(obj) or inspect.isfunction(obj)
        is_property = isinstance(inspect.getattr_static(AigonClient, name), property)

        if is_method:
            if name.startswith("_"):
                actual_private_methods.add(name)
            else:
                actual_public_methods.add(name)
        elif is_property:
            if name.startswith("_"):
                actual_private_properties.add(name)
            else:
                actual_public_properties.add(name)

    # Check methods match exactly
    assert_signatures_match(actual_public_methods, expected_public_methods, "AigonClient public methods")
    assert_signatures_match(actual_private_methods, expected_private_methods, "AigonClient private methods")

    # Check properties match exactly
    assert_signatures_match(actual_public_properties, expected_public_properties, "AigonClient public properties")
    assert_signatures_match(actual_private_properties, expected_private_properties, "AigonClient private properties")

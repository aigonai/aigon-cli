"""
Test file that tests the signature of requests_shim module.

This test file checks:
a) All expected functions are present
b) Functions have the expected parameters

This is primarily a signature test to ensure the shim maintains
compatibility with the requests library interface it replaces.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""
import inspect
from aigon_cli import requests_shim
from tests.utils.signature_test_helpers import assert_signatures_match


def test_requests_shim_functions_signature():
    """Test that requests_shim has exactly the expected functions."""
    expected_public_functions = {
        'get', 'post', 'put', 'delete'
    }

    expected_private_functions = {
        '_build_url', '_make_request'
    }

    # Get all functions
    actual_public_functions = set()
    actual_private_functions = set()

    for name, obj in inspect.getmembers(requests_shim, inspect.isfunction):
        if name.startswith('_'):
            actual_private_functions.add(name)
        else:
            actual_public_functions.add(name)

    assert_signatures_match(actual_public_functions, expected_public_functions, "requests_shim public functions")
    assert_signatures_match(actual_private_functions, expected_private_functions, "requests_shim private functions")


def test_requests_shim_classes_signature():
    """Test that requests_shim has expected classes."""
    expected_classes = {'Response', 'HTTPError', 'exceptions'}

    # Exclude typing imports like Any, Dict, Optional
    typing_classes = {'Any', 'Dict', 'Optional'}

    actual_classes = set()
    for name, obj in inspect.getmembers(requests_shim, inspect.isclass):
        if not name.startswith('_') and name not in typing_classes:
            actual_classes.add(name)

    assert_signatures_match(actual_classes, expected_classes, "requests_shim classes")


def test_get_function_parameters():
    """Test that get() function has correct parameters."""
    sig = inspect.signature(requests_shim.get)
    params = list(sig.parameters.keys())
    assert params == ['url', 'headers', 'params'], f"get() params: {params}"


def test_post_function_parameters():
    """Test that post() function has correct parameters."""
    sig = inspect.signature(requests_shim.post)
    params = list(sig.parameters.keys())
    assert params == ['url', 'headers', 'params', 'json'], f"post() params: {params}"


def test_put_function_parameters():
    """Test that put() function has correct parameters including json."""
    sig = inspect.signature(requests_shim.put)
    params = list(sig.parameters.keys())
    assert params == ['url', 'headers', 'params', 'data', 'json'], f"put() params: {params}"


def test_delete_function_parameters():
    """Test that delete() function has correct parameters."""
    sig = inspect.signature(requests_shim.delete)
    params = list(sig.parameters.keys())
    assert params == ['url', 'headers', 'params'], f"delete() params: {params}"

"""
Helper functions for signature tests to provide meaningful error messages.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""


def assert_signatures_match(actual, expected, signature_type="signatures"):
    """
    Assert that actual and expected sets match, providing meaningful difference messages.

    Args:
        actual: Set of actual method/property names
        expected: Set of expected method/property names
        signature_type: Type of signatures being compared (e.g., "methods", "properties")
    """
    if actual != expected:
        missing = expected - actual
        unexpected = actual - expected

        error_parts = []

        if missing:
            error_parts.append(f"Missing {signature_type}: {sorted(missing)}")

        if unexpected:
            error_parts.append(f"Unexpected {signature_type}: {sorted(unexpected)}")

        error_message = f"{signature_type.capitalize()} mismatch! " + " | ".join(error_parts)

        # Add full sets for debugging if needed
        error_message += f"\n\nExpected {len(expected)} {signature_type}: {sorted(expected)}"
        error_message += f"\n\nActual {len(actual)} {signature_type}: {sorted(actual)}"

        raise AssertionError(error_message)

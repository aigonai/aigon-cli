"""Tests for the LLM-friendly help content in aigon_cli.llm.

(c) Stefan LOESCH 2025-26. All rights reserved.
"""

from aigon_cli import llm


def test_no_stale_last_flag():
    """No help-text string in llm.py should reference --last (not a real flag).

    The `--last` flag does not exist anywhere in the aigon-cli argparse
    definitions; references to it in help text are stale and would cause
    an LLM to issue a broken command. The trailing space in the match
    string avoids false positives on hypothetical --last-* flags.
    """
    # Concatenate every string constant exposed by the llm module.
    strings = [value for value in vars(llm).values() if isinstance(value, str)]
    # Also pull strings embedded in function source (the current show_llm_help_*
    # functions hold their content as local `help_text` literals).
    import inspect

    for value in vars(llm).values():
        if inspect.isfunction(value):
            try:
                strings.append(inspect.getsource(value))
            except (OSError, TypeError):
                pass

    combined = "\n".join(strings)
    assert "--last " not in combined, (
        "Stale --last reference found in aigon_cli.llm help text. "
        "The flag does not exist; use --newest (for quick-peek mode) "
        "or --days (for time filter) depending on intent."
    )

import pytest


@pytest.mark.live
def test_live_registry_diagnostic_placeholder():
    """Run manually after selecting a known-bad library title.

    The effectiveness gate is deliberately not a default network test: the
    expected corrected actress list must come from a user's observed case.
    """
    pytest.skip("requires a user-supplied known-bad title and live network")

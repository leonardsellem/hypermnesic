"""U1 smoke test: the package imports and exposes a version string."""

import hypermnesic


def test_package_imports_and_has_version():
    assert isinstance(hypermnesic.__version__, str)
    assert hypermnesic.__version__.count(".") >= 1


def test_cli_help_runs():
    from hypermnesic.cli import main

    assert main([]) == 0

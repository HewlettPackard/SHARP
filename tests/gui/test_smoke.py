"""
Smoke tests for GUI tab modules.

These tests verify that each tab's UI function can be called without errors
and returns valid Shiny UI components. They do not test visual rendering
but ensure the module imports and basic UI construction work correctly.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

import pytest
from shiny import ui


class TestSummaryTabSmoke:
    """Smoke tests for Summary tab."""

    def test_summary_ui_imports(self):
        """Verify summary_ui can be imported."""
        from src.gui.modules.summary import summary_ui
        assert callable(summary_ui)

    def test_summary_ui_returns_nav_panel(self):
        """Verify summary_ui returns a valid UI component."""
        from src.gui.modules.summary import summary_ui
        result = summary_ui()
        assert result is not None
        # Should be a nav_panel (TagChild)
        assert hasattr(result, 'tagify') or isinstance(result, (ui.Tag, ui.TagList))

    def test_summary_server_imports(self):
        """Verify summary_server can be imported."""
        from src.gui.modules.summary import summary_server
        assert callable(summary_server)


class TestMeasureTabSmoke:
    """Smoke tests for Measure tab."""

    def test_measure_ui_imports(self):
        """Verify measure_ui can be imported."""
        from src.gui.modules.measure import measure_ui
        assert callable(measure_ui)

    def test_measure_ui_returns_nav_panel(self):
        """Verify measure_ui returns a valid UI component."""
        from src.gui.modules.measure import measure_ui
        result = measure_ui()
        assert result is not None
        assert hasattr(result, 'tagify') or isinstance(result, (ui.Tag, ui.TagList))

    def test_measure_server_imports(self):
        """Verify measure_server can be imported."""
        from src.gui.modules.measure import measure_server
        assert callable(measure_server)


class TestProfileTabSmoke:
    """Smoke tests for Profile tab."""

    def test_profile_ui_imports(self):
        """Verify profile_ui can be imported."""
        from src.gui.modules.profile import profile_ui
        assert callable(profile_ui)

    def test_profile_ui_returns_nav_panel(self):
        """Verify profile_ui returns a valid UI component."""
        from src.gui.modules.profile import profile_ui
        result = profile_ui()
        assert result is not None
        assert hasattr(result, 'tagify') or isinstance(result, (ui.Tag, ui.TagList))

    def test_profile_server_imports(self):
        """Verify profile_server can be imported."""
        from src.gui.modules.profile import profile_server
        assert callable(profile_server)


class TestExploreTabSmoke:
    """Smoke tests for Explore tab."""

    def test_explore_ui_imports(self):
        """Verify explore_ui can be imported."""
        from src.gui.modules.explore import explore_ui
        assert callable(explore_ui)

    def test_explore_ui_returns_nav_panel(self):
        """Verify explore_ui returns a valid UI component."""
        from src.gui.modules.explore import explore_ui
        result = explore_ui()
        assert result is not None
        assert hasattr(result, 'tagify') or isinstance(result, (ui.Tag, ui.TagList))

    def test_explore_server_imports(self):
        """Verify explore_server can be imported."""
        from src.gui.modules.explore import explore_server
        assert callable(explore_server)


class TestCompareTabSmoke:
    """Smoke tests for Compare tab."""

    def test_compare_ui_imports(self):
        """Verify compare_ui can be imported."""
        from src.gui.modules.compare import compare_ui
        assert callable(compare_ui)

    def test_compare_ui_returns_nav_panel(self):
        """Verify compare_ui returns a valid UI component."""
        from src.gui.modules.compare import compare_ui
        result = compare_ui()
        assert result is not None
        assert hasattr(result, 'tagify') or isinstance(result, (ui.Tag, ui.TagList))

    def test_compare_server_imports(self):
        """Verify compare_server can be imported."""
        from src.gui.modules.compare import compare_server
        assert callable(compare_server)


class TestModulesPackageSmoke:
    """Smoke tests for the modules package __init__."""

    def test_all_exports_available(self):
        """Verify all expected exports are available from the package."""
        from src.gui.modules import (
            summary_ui, summary_server,
            measure_ui, measure_server,
            profile_ui, profile_server,
            explore_ui, explore_server,
            compare_ui, compare_server
        )
        # All imports succeeded
        assert all([
            callable(summary_ui), callable(summary_server),
            callable(measure_ui), callable(measure_server),
            callable(profile_ui), callable(profile_server),
            callable(explore_ui), callable(explore_server),
            callable(compare_ui), callable(compare_server)
        ])

    def test_module_all_list_complete(self):
        """Verify __all__ contains expected exports."""
        from src.gui import modules
        expected = {
            "summary_ui", "summary_server",
            "measure_ui", "measure_server",
            "profile_ui", "profile_server",
            "explore_ui", "explore_server",
            "compare_ui", "compare_server"
        }
        assert set(modules.__all__) == expected


class TestAppSmoke:
    """Smoke tests for the main app module."""

    def test_app_imports(self):
        """Verify main app can be imported without errors."""
        from src.gui import app
        assert hasattr(app, 'app')

    def test_app_is_shiny_app(self):
        """Verify app is a valid Shiny App instance."""
        from src.gui.app import app
        # Shiny App objects have a specific structure
        assert app is not None
        # Check it's callable or has the expected Shiny app attributes
        assert hasattr(app, 'ui') or callable(app)

"""
Settings modal UI utilities for SHARP GUI.

Provides functions to create and manage the settings modal dialog.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui, reactive
from ruamel.yaml import YAML

from src.core.config.settings import Settings


def create_settings_modal() -> ui.modal:
    """
    Create the settings modal dialog with all configurable settings.

    Returns:
        Shiny modal UI element
    """
    settings = Settings()

    return ui.modal(
        ui.tags.h3("Settings", style="margin-top: 0;"),

        # Theme setting
        ui.input_select(
            "settings_theme",
            "Theme",
            choices={
                "bootstrap": "Bootstrap",
                "cerulean": "Cerulean",
                "cosmo": "Cosmo",
                "cyborg": "Cyborg",
                "darkly": "Darkly",
                "flatly": "Flatly",
                "journal": "Journal",
                "litera": "Litera",
                "lumen": "Lumen",
                "lux": "Lux",
                "materia": "Materia",
                "minty": "Minty",
                "morph": "Morph",
                "pulse": "Pulse",
                "quartz": "Quartz",
                "sandstone": "Sandstone",
                "simplex": "Simplex",
                "sketchy": "Sketchy",
                "slate": "Slate",
                "solar": "Solar",
                "spacelab": "Spacelab",
                "superhero": "Superhero",
                "united": "United",
                "vapor": "Vapor",
                "yeti": "Yeti",
                "zephyr": "Zephyr",
            },
            selected=settings.get("gui.theme", "spacelab"),
        ),

        # Recent experiments count
        ui.input_numeric(
            "settings_recent_count",
            "Number of Recent Experiments to Display",
            value=settings.get("gui.overview.recent_runs_count", 25),
            min=1,
            max=100,
        ),

        # Distribution plot colors row
        ui.tags.h5("Distribution Plot Colors", class_="mt-3 mb-2"),
        ui.row(
            ui.column(
                3,
                ui.input_text(
                    "settings_divider_color",
                    "Cutoff Color",
                    value=settings.get("gui.distribution.divider_color", "#1f77b4"),
                ),
                ui.tags.script(f"""
                    $(document).ready(function() {{
                        $('#settings_divider_color').attr('type', 'color');
                        $('#settings_divider_color').addClass('form-control-color');
                    }});
                """),
            ),
            ui.column(
                3,
                ui.input_text(
                    "settings_fast_color",
                    "Fast Color",
                    value=settings.get("gui.distribution.fast_color", "#2ca02c"),
                ),
                ui.tags.script(f"""
                    $(document).ready(function() {{
                        $('#settings_fast_color').attr('type', 'color');
                        $('#settings_fast_color').addClass('form-control-color');
                    }});
                """),
            ),
            ui.column(
                3,
                ui.input_text(
                    "settings_slow_color",
                    "Slow Color",
                    value=settings.get("gui.distribution.slow_color", "#ff7f0e"),
                ),
                ui.tags.script(f"""
                    $(document).ready(function() {{
                        $('#settings_slow_color').attr('type', 'color');
                        $('#settings_slow_color').addClass('form-control-color');
                    }});
                """),
            ),
            ui.column(
                3,
                ui.input_select(
                    "settings_palette",
                    "Palette",
                    choices={
                        "tab10": "Tab10",
                        "deep": "Deep",
                        "muted": "Muted",
                        "pastel": "Pastel",
                        "bright": "Bright",
                        "dark": "Dark",
                        "colorblind": "Colorblind",
                        "viridis": "Viridis",
                        "Set2": "Set2",
                        "Set3": "Set3",
                    },
                    selected=settings.get("gui.distribution.palette", "dark"),
                ),
            ),
        ),

        # Transparency and max scatter points row
        ui.tags.h5("Visualization Settings", class_="mt-3 mb-2"),
        ui.row(
            ui.column(
                6,
                ui.input_numeric(
                    "settings_alpha",
                    "Transparency (0-1)",
                    value=settings.get("gui.distribution.alpha", 0.4),
                    min=0,
                    max=1,
                    step=0.05,
                ),
            ),
            ui.column(
                6,
                ui.input_numeric(
                    "settings_max_scatter_points",
                    "Max Scatter Points",
                    value=settings.get("gui.explore.max_scatter_points", 2000),
                    min=100,
                    max=50000,
                    step=100,
                ),
            ),
        ),

        # Profiling parameters row
        ui.tags.h5("Profiling Parameters", class_="mt-3 mb-2"),
        ui.row(
            ui.column(
                4,
                ui.input_numeric(
                    "settings_max_predictors",
                    "Max Predictors",
                    value=settings.get("profiling.max_predictors", 100),
                    min=10,
                    max=1000,
                ),
            ),
            ui.column(
                4,
                ui.input_numeric(
                    "settings_max_correlation",
                    "Max Correlation",
                    value=settings.get("profiling.max_correlation", 0.99),
                    min=0.5,
                    max=1,
                    step=0.01,
                ),
            ),
            ui.column(
                4,
                ui.input_numeric(
                    "settings_max_search",
                    "Max Search",
                    value=settings.get("profiling.max_search", 100),
                    min=10,
                    max=1000,
                ),
            ),
        ),

        # Buttons
        ui.tags.div(
            ui.input_action_button("settings_cancel", "Cancel", class_="btn btn-secondary"),
            ui.input_action_button("settings_accept", "Accept", class_="btn btn-primary"),
            style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px;",
        ),
        easy_close=True,
        footer=None,
    )


def save_settings(input, settings_path) -> None:
    """
    Save settings from input values to settings.yaml.

    Args:
        input: Shiny input object with settings values
        settings_path: Path to settings.yaml file
    """
    try:
        # Debug: print input values
        print(f"Saving settings to: {settings_path}")
        print(f"Theme: {input.settings_theme()}")
        print(f"Recent count: {input.settings_recent_count()}")
        print(f"Divider color: {input.settings_divider_color()}")
        print(f"Fast color: {input.settings_fast_color()}")
        print(f"Slow color: {input.settings_slow_color()}")
        print(f"Palette: {input.settings_palette()}")
        print(f"Alpha: {input.settings_alpha()}")
        print(f"Max scatter: {input.settings_max_scatter_points()}")
        print(f"Max predictors: {input.settings_max_predictors()}")
        print(f"Max correlation: {input.settings_max_correlation()}")
        print(f"Max search: {input.settings_max_search()}")

        # Load YAML with ruamel.yaml to preserve comments
        yaml_handler = YAML()
        yaml_handler.preserve_quotes = True
        yaml_handler.default_flow_style = False
        with open(settings_path, 'r') as f:
            config = yaml_handler.load(f) or {}

        # Ensure nested structure exists
        if 'gui' not in config:
            config['gui'] = {}
        if 'overview' not in config['gui']:
            config['gui']['overview'] = {}
        if 'distribution' not in config['gui']:
            config['gui']['distribution'] = {}
        if 'explore' not in config['gui']:
            config['gui']['explore'] = {}
        if 'profiling' not in config:
            config['profiling'] = {}

        # Update values
        config['gui']['theme'] = input.settings_theme()
        config['gui']['overview']['recent_runs_count'] = input.settings_recent_count()
        config['gui']['distribution']['divider_color'] = input.settings_divider_color()
        config['gui']['distribution']['fast_color'] = input.settings_fast_color()
        config['gui']['distribution']['slow_color'] = input.settings_slow_color()
        config['gui']['distribution']['palette'] = input.settings_palette()
        config['gui']['distribution']['alpha'] = input.settings_alpha()
        config['gui']['explore']['max_scatter_points'] = input.settings_max_scatter_points()
        config['profiling']['max_predictors'] = input.settings_max_predictors()
        config['profiling']['max_correlation'] = input.settings_max_correlation()
        config['profiling']['max_search'] = input.settings_max_search()

        # Write back to YAML (preserves comments and formatting)
        with open(settings_path, 'w') as f:
            yaml_handler.dump(config, f)

        print("Settings saved successfully!")
    except Exception as e:
        print(f"Error in save_settings: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def register_settings_handlers(input, output, session, shiny_ui) -> None:
    """
    Register reactive handlers for settings modal.

    Args:
        input: Shiny input object
        output: Shiny output object
        session: Shiny session object
        shiny_ui: Shiny UI module
    """

    # Show settings modal when gear icon is clicked
    @reactive.effect
    def _show_settings_modal() -> None:
        trigger = input.show_settings_modal()
        if trigger is not None and trigger > 0:
            modal = create_settings_modal()
            shiny_ui.modal_show(modal)

    # Handle settings cancel button
    @reactive.effect
    @reactive.event(input.settings_cancel)
    def _on_settings_cancel() -> None:
        shiny_ui.modal_remove()

    # Handle settings accept button
    @reactive.effect
    @reactive.event(input.settings_accept)
    def _on_settings_accept() -> None:
        try:
            settings = Settings()
            save_settings(input, settings.config_path)

            # Close modal first
            shiny_ui.modal_remove()

            # Show notification
            shiny_ui.notification_show("Settings saved. Reloading...", type="message", duration=2)

            # Reload page after a brief delay
            shiny_ui.insert_ui(
                ui.tags.script("setTimeout(function() { window.location.reload(); }, 500);"),
                selector="body",
                where="beforeEnd",
            )
        except Exception as e:
            shiny_ui.notification_show(f"Error saving settings: {str(e)}", type="error", duration=5)

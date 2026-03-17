"""
SHARP GUI application.

Python Shiny application for launching, analyzing, and comparing benchmarks.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from pathlib import Path
from shiny import App, ui, reactive, Inputs, Outputs, Session
import shinyswatch
from ruamel.yaml import YAML

from ..core.config.settings import Settings

# Import tab modules (will be created in subsequent tasks)
from .modules.summary import summary_ui, summary_server
from .modules.measure import measure_ui, measure_server
from .modules.profile import profile_ui, profile_server
from .modules.explore import explore_ui, explore_server
from .modules.compare import compare_ui, compare_server

# Get the directory containing this file
app_dir = Path(__file__).parent
www_dir = app_dir / "www"

theme_name = Settings().get("gui.theme", "spacelab")
theme = getattr(shinyswatch.theme, theme_name, shinyswatch.theme.spacelab)

theme_name = Settings().get("gui.theme", "spacelab")
theme = getattr(shinyswatch.theme, theme_name, shinyswatch.theme.spacelab)

# SVG spinner path
spinner_path = www_dir / "stopwatch-spinner.svg"

# UI definition with busy indicator
app_ui = ui.page_navbar(
    summary_ui(),
    measure_ui(),
    explore_ui(),
    compare_ui(),
    profile_ui(),
    ui.nav_spacer(),
    ui.nav_control(
        ui.tags.a(
            ui.tags.i(class_="bi bi-gear"),
            href="#",
            id="settings_btn",
            style="font-size: 1.25rem; cursor: pointer; padding: 8px;",
            title="Settings",
        ),
    ),
    title=ui.tags.img(src="sharp.png", height="30", width="90"),
    id="main_nav",
    theme=theme,  # Loaded from settings.yaml (gui.theme)
    fillable=True,
    header=ui.tags.head(
        ui.tags.link(rel="icon", href="sharp.png"),
        ui.tags.link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css"
        ),
        # Fix scrolling issues in tabs with multiple plot rows
        ui.tags.style("""
            /* Profile tab: ensure content can scroll when it exceeds viewport */
            .tab-pane[data-value="Profile"] {
                overflow-y: auto !important;
                max-height: none !important;
            }
            /* Explore tab: same fix for correlation plots */
            .tab-pane[data-value="Explore"] {
                overflow-y: auto !important;
                max-height: none !important;
            }
            /* Compare tab: same fix */
            .tab-pane[data-value="Compare"] {
                overflow-y: auto !important;
                max-height: none !important;
            }
        """),
        ui.tags.script("""
        document.addEventListener('DOMContentLoaded', function() {
            // Show settings modal when gear icon is clicked
            const settingsBtn = document.getElementById('settings_btn');
            if (settingsBtn) {
                settingsBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    Shiny.setInputValue('show_settings_modal', Math.random());
                });
            }
        });

        // Handle populate explore form from overview/measure tabs
        Shiny.addCustomMessageHandler('populate_explore_form', function(config) {
            // Send config as JSON string to an input value in explore tab
            Shiny.setInputValue('explore_preload_config', JSON.stringify(config), {priority: 'event'});
        });

        // Handle page reload message from server
        Shiny.addCustomMessageHandler('reload_page', function(message) {
            window.location.reload();
        });

        // Handle populate measure form from overview tab rerun
        Shiny.addCustomMessageHandler('populate_measure_form', function(config) {
            // Send config as JSON string to an input value in measure tab
            Shiny.setInputValue('rerun_config_data', JSON.stringify(config), {priority: 'event'});
        });

        // Global click handler for rerun buttons
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a[id^="rerun_"]');
            if (link) {
                e.preventDefault();
                const id = link.getAttribute('id');
                const index = parseInt(id.replace('rerun_', ''));
                Shiny.setInputValue('rerun_click', index, {priority: 'event'});
            }
        }, true);

        // Global click handler for explore buttons in overview table
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a[id^="explore_"]');
            if (link) {
                e.preventDefault();
                const id = link.getAttribute('id');
                const index = parseInt(id.replace('explore_', ''));
                Shiny.setInputValue('explore_click', index, {priority: 'event'});
            }
        }, true);

        // Click handler for explore link in measure completion status bar
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a[id="explore_completed_run"]');
            if (link) {
                e.preventDefault();
                Shiny.setInputValue('explore_completed_run_click', Math.random(), {priority: 'event'});
            }
        }, true);
        """),
    ),
    window_title="SHARP",  # Browser tab title (matches R GUI windowTitle)
    footer=ui.busy_indicators.options(
        spinner_type=spinner_path,
        spinner_color="#0d6efd",
        spinner_size="60px",
        spinner_delay="0ms",
    ),
)

# Wrap app_ui (don't include modal in initial UI)
final_ui = app_ui


def server(input: Inputs, output: Outputs, session: Session) -> None:
    """
    Server logic for SHARP GUI.

    Args:
        input: Shiny input object
        output: Shiny output object
        session: Shiny session object
    """
    from shiny import ui as shiny_ui

    # Show settings modal when gear icon is clicked
    @reactive.effect
    def _show_settings_modal() -> None:
        trigger = input.show_settings_modal()
        if trigger is not None and trigger > 0:
            # Create and show modal
            m = shiny_ui.modal(
                ui.tags.h3("Settings", style="margin-top: 0;"),
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
                    selected=Settings().get("gui.theme", "spacelab"),
                ),
                ui.input_numeric(
                    "settings_recent_count",
                    "Number of Recent Experiments to Display",
                    value=Settings().get("gui.overview.recent_runs_count", 10),
                    min=1,
                    max=100,
                ),
                ui.tags.div(
                    ui.input_action_button("settings_cancel", "Cancel", class_="btn btn-secondary"),
                    ui.input_action_button("settings_accept", "Accept", class_="btn btn-primary"),
                    style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px;",
                ),
                easy_close=True,
                footer=None,
            )
            shiny_ui.modal_show(m)

    # Handle settings cancel button
    @reactive.effect
    def _on_settings_cancel() -> None:
        if input.settings_cancel():
            shiny_ui.modal_remove()

    # Handle settings accept button
    @reactive.effect
    def _on_settings_accept() -> None:
        if input.settings_accept():
            new_theme = input.settings_theme()
            new_recent_count = input.settings_recent_count()

            # Read current settings
            settings = Settings()
            settings_path = settings.config_path

            # Load YAML with ruamel.yaml to preserve comments
            yaml_handler = YAML()
            yaml_handler.preserve_quotes = True
            yaml_handler.default_flow_style = False
            with open(settings_path, 'r') as f:
                config = yaml_handler.load(f) or {}

            # Update values
            if 'gui' not in config:
                config['gui'] = {}
            if 'overview' not in config['gui']:
                config['gui']['overview'] = {}

            config['gui']['theme'] = new_theme
            config['gui']['overview']['recent_runs_count'] = new_recent_count

            # Write back to YAML (preserves comments and formatting)
            with open(settings_path, 'w') as f:
                yaml_handler.dump(config, f)

            # Reload page immediately via JavaScript
            shiny_ui.insert_ui(
                ui.tags.script("window.location.reload();"),
                selector="body",
                where="beforeEnd",
            )

    # Server logic for tabs
    # Create shared reactive value for triggering overview refresh
    refresh_overview_trigger = reactive.value(0)

    summary_server(input, output, session, refresh_trigger=refresh_overview_trigger)
    measure_server(input, output, session, refresh_trigger=refresh_overview_trigger)
    profile_server(input, output, session)
    explore_server(input, output, session)
    compare_server(input, output, session)


# Create app
app = App(final_ui, server, static_assets=www_dir)

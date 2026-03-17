"""
Profile tab modal builders.

Clean modal builders that work with the state machine architecture.
Each modal knows how to build itself but delegates state transitions
to the state machine.

© Copyright 2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui
from pathlib import Path
from typing import Optional

from src.gui.utils.profile.files import (
    extract_run_time_from_md,
    extract_backends_from_md,
    extract_repeater_max_from_md
)
from src.core.config import discover_backends


def build_choose_source_modal(prof_csv: str | None = None) -> ui.Tag:
    """
    Build modal for choosing profiling data source or action.

    Always shows two options:
    - Use Existing: Load the selected CSV/MD (with or without -prof data)
    - Profile/Reprofile Task: Open configure modal to add profiling backends

    Args:
        prof_csv: Optional profiling CSV filename if it exists (e.g., 'inc-prof.csv')

    Returns:
        Shiny modal object
    """
    # Build message based on prof file availability
    has_prof_data = prof_csv is not None

    if prof_csv:
        file_display = Path(prof_csv).name

        message = ui.tags.div(
            ui.tags.p("✓ Profiling data found for this task."),
            ui.tags.p(
                ui.tags.code(file_display, style="color: #666;"),
                style="margin: 10px 0;"
            ),
            ui.p("What would you like to do?")
        )
        title = "Profiling Data Found"
        profile_button_label = "Reprofile Task"
    else:
        message = ui.tags.div(
            ui.p("No profiling data found for this task."),
            ui.p("You can use the existing data or add profiling.", style="margin-top: 10px;")
        )
        title = "Profile Options"
        profile_button_label = "Profile Task"

    return ui.modal(
        message,
        title=title,
        footer=ui.TagList(
            ui.input_action_button(
                "modal_cancel",
                "Cancel",
                class_="btn-secondary"
            ),
            ui.input_action_button(
                "modal_use_existing",
                "Use Existing",
                class_="btn-primary",
                icon=ui.tags.span(
                    ui.tags.i(class_="bi bi-check-circle"),
                    "\u00A0"
                )
            ),
            ui.input_action_button(
                "modal_run_profiling",
                profile_button_label,
                class_="btn-success",
                icon=ui.tags.span(
                    ui.tags.i(class_="bi bi-play-circle"),
                    "\u00A0"
                )
            )
        ),
        easy_close=True
    )


def build_configure_modal(prof_md: str | None = None) -> ui.Tag:
    """
    Build modal for configuring a profiling run.

    Shows when user wants to profile (either new or with existing data).
    If prof_md is provided, displays original run info and pre-populates backends.

    Args:
        prof_md: Optional path to existing profiling markdown (for context/pre-population)

    Returns:
        Shiny modal object
    """
    # Get profiling backends
    profiling_backends = discover_backends(profiling=True)
    backend_choices = {name: name for name in sorted(profiling_backends.keys())}

    # Build modal content
    content_parts = []

    # If we have existing prof_md, show context info
    suggested_task_name = ""
    if prof_md and Path(prof_md).exists():
        original_time = extract_run_time_from_md(prof_md)
        time_display = f"{original_time:.1f} seconds" if original_time else "unknown duration"

        original_iterations = extract_repeater_max_from_md(prof_md)
        iterations_display = f"{original_iterations if original_iterations else 'unknown'} rows"

        original_backends = extract_backends_from_md(prof_md)
        backends_info = ", ".join(original_backends) if original_backends else "none"

        # Suggest a task name based on the prof_md filename
        prof_md_path = Path(prof_md)
        # Remove -prof suffix if present to get base name
        base_name = prof_md_path.stem.replace("-prof", "")
        suggested_task_name = f"{base_name}-prof"

        # Add context about original run
        content_parts.append(
            ui.tags.p(
                ui.tags.strong("Previous run: "),
                f"{time_display}, {iterations_display}, backends: {backends_info}",
                style="margin-bottom: 15px; color: #666; font-size: 0.9em; padding: 10px; background: #f5f5f5; border-radius: 4px;"
            )
        )

    # Add task name input
    content_parts.append(
        ui.input_text(
            "profile_task_name",
            "Task name for profiling output:",
            value=suggested_task_name,
            placeholder="e.g., mytask-prof"
        )
    )

    content_parts.append(
        ui.tags.p(
            "Select profiling backends (in order):",
            style="margin-bottom: 10px; margin-top: 15px;"
        )
    )

    content_parts.append(
        ui.input_selectize(
            "profile_backends_selector",
            None,
            choices=backend_choices,
            selected=[],
            multiple=True,
            options={"plugins": ["remove_button"]}
        )
    )

    content_parts.append(
        ui.tags.p(
            "Note: Selected backends will be added to the original backend chain.",
            style="margin-top: 10px; font-size: 0.85em; color: #666; font-style: italic;"
        )
    )

    return ui.modal(
        ui.tags.div(*content_parts),
        title="⚙️ Configure Profiling",
        footer=ui.TagList(
            ui.input_action_button(
                "modal_cancel",
                "Cancel",
                class_="btn-secondary"
            ),
            ui.input_action_button(
                "modal_start_profiling",
                "Start Profiling",
                class_="btn-success",
                icon=ui.tags.span(
                    ui.tags.i(class_="bi bi-play-circle"),
                    "\u00A0"
                )
            )
        ),
        easy_close=True
    )


def build_invalid_backend_modal(error_msg: str) -> ui.Tag:
    """
    Build modal for invalid backend configuration error.

    Args:
        error_msg: Error message describing the problem

    Returns:
        Shiny modal object
    """
    return ui.modal(
        ui.tags.div(
            ui.tags.p(error_msg),
            ui.tags.p(
                "Non-composable backends (like mpip) must be alone or leftmost in the chain.",
                style="margin-top: 10px; color: #666;"
            )
        ),
        title="❌ Invalid Backend Configuration",
        footer=ui.input_action_button(
            "modal_error_ok",
            "OK",
            class_="btn-primary"
        ),
        easy_close=True
    )


def build_profiling_error_modal(error_msg: str) -> ui.TagChild:
    """
    Build modal for profiling execution error.

    Args:
        error_msg: Error message

    Returns:
        Shiny modal object
    """
    return ui.modal(
        ui.tags.div(
            ui.tags.p(
                "❌ Profiling failed with an error:",
                style="color: #dc3545; font-weight: 500; margin-bottom: 10px;"
            ),
            ui.tags.pre(
                error_msg,
                style="background-color: #f8f9fa; padding: 10px; border-radius: 4px; overflow-x: auto;"
            )
        ),
        title="Profiling Error",
        footer=ui.input_action_button(
            "modal_error_ok",
            "OK",
            class_="btn-primary"
        ),
        easy_close=True
    )


def build_try_mitigation_modal(mitigation_exists: bool, is_automated: bool) -> ui.Tag:
    """
    Build modal for attempting mitigation.

    Args:
        mitigation_exists: Whether mitigation data file already exists
        is_automated: Whether mitigation can be automated (has backend_options)

    Returns:
        Shiny modal object
    """
    if mitigation_exists:
        return ui.modal(
            ui.p("A file with mitigation data exists. Do you want to use it or rerun it?"),
            title="Mitigation data exists",
            footer=ui.tags.div(
                ui.input_action_button("profile_cancel_mitigation", "Cancel", class_="btn-secondary"),
                ui.input_action_button("profile_use_mitigation_data", "Use data", class_="btn-primary"),
                ui.input_action_button("profile_run_mitigation", "Rerun it", class_="btn-success"),
            ),
            easy_close=True
        )
    else:
        if is_automated:
            msg = "Are you sure you want to rerun benchmark? This could take a while."
        else:
            msg = (
                "This mitigation cannot be automated. "
                "To run it manually, back up your current setup and application and apply the mitigation yourself. "
                "(If recompiling the application, make sure to use the same path and binary name as before.) "
                "When ready, click 'Run it!' to get the new data. This could take a while. "
                "Remember to restore system state to normal after the run if needed."
            )

        return ui.modal(
            ui.p(msg),
            title="Attempt mitigation on program",
            footer=ui.tags.div(
                ui.input_action_button("profile_cancel_mitigation", "Cancel", class_="btn-secondary"),
                ui.input_action_button("profile_run_mitigation", "Run it!", class_="btn-success"),
            ),
            easy_close=True
        )

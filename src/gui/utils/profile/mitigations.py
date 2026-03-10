"""
Mitigation rendering utilities for profile tab.

Handles rendering of mitigation selector and info cards.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from shiny import ui

from src.core.metrics.factors import get_factor_info, get_mitigation_info


def render_mitigation_selector(factor_name: str):
    """
    Render dropdown selector for mitigations related to selected factor.

    Args:
        factor_name: Name of the selected factor

    Returns:
        Shiny UI element with mitigation dropdown or placeholder message
    """
    if not factor_name:
        return ui.p(
            'Select a factor to view mitigations',
            style='color: #999; padding: 10px; text-align: center; font-size: 0.9em;'
        )

    # Get factor info to find mitigations
    factor_info = get_factor_info(factor_name)
    if not factor_info:
        return ui.p(
            f'No information found for factor "{factor_name}"',
            style='color: #999; padding: 10px;'
        )

    mitigations = factor_info.get('mitigations', [])
    if not mitigations:
        return ui.p(
            f'No mitigations suggested for {factor_name}',
            style='color: #999; padding: 10px;'
        )

    # Create choices dict and select first mitigation by default
    choices = {name: name for name in mitigations}

    # Render the selector and a "Try it" button to its right in a single row.
    return ui.div(
        ui.tags.div(
            ui.input_selectize(
                "profile_selected_mitigation",
                "Choose mitigation:",
                choices=choices,
                selected=mitigations[0],  # Select first mitigation by default
                options={
                    'placeholder': 'Select a mitigation...',
                }
            ),
            style="display: inline-block; width: 70%;"
        ),
        ui.tags.div(
            ui.input_action_button(
                "profile_try_mitigation",
                ui.tags.span(
                    ui.tags.i(class_="fa fa-play", style="margin-right: 5px;"),
                    "Try it!"
                ),
                class_="btn-success"
            ),
            style="display: inline-block; width: 28%; padding-left: 8px; vertical-align: middle;"
        )
    )


def render_mitigation_info_card(mitigation_name: str):
    """
    Render mitigation information card with description, references, and Try it button.

    Args:
        mitigation_name: Name of the selected mitigation

    Returns:
        Shiny UI card with mitigation details or placeholder message
    """
    if not mitigation_name or not mitigation_name.strip():
        return ui.p(
            'Select a mitigation to view details',
            style='color: #999; padding: 20px; text-align: center; font-style: italic;'
        )

    # Get mitigation info
    mit_info = get_mitigation_info(mitigation_name)
    if not mit_info:
        return ui.p(
            f'No information found for mitigation "{mitigation_name}"',
            style='color: #999; padding: 10px;'
        )

    description = mit_info.get('description', 'No description available')
    references = mit_info.get('references', {})

    # Build references HTML
    ref_links = []
    for name, url in references.items():
        ref_links.append(ui.tags.a(name, href=url, target='_blank'))

    if ref_links:
        refs_content = ui.tags.span(*[
            item for pair in zip(ref_links, [ui.tags.span(' | ')] * len(ref_links))
            for item in pair
        ][:-1])
    else:
        refs_content = ui.tags.span('No references available', style='color: #999;')

    return ui.card(
        ui.tags.div(
            ui.markdown(description),
            style='margin-bottom: 6px;'
        ),
        ui.tags.div(
            ui.tags.strong('References: '),
            refs_content,
            style='margin-bottom: 4px; font-size: 0.88em;'
        )
    )

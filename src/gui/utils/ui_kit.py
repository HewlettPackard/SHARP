"""
UI toolkit for SHARP GUI.

Provides HTML-generating utilities for the FastAPI/HTMX-based GUI.
Replaces the Shiny ui.* API with dominate-based helpers that produce
server-rendered HTML fragments suitable for HTMX delivery.

Categories:
- Tags/elements: div, p, card, hr, HTML, markdown, row, column, TagList
- Form inputs: input_selectize, input_slider, input_checkbox,
               input_numeric, input_text, input_action_button
- Modal system: modal, modal_button, modal_show, modal_remove
- Session updates: update_slider, update_selectize, update_select,
                   update_checkbox, insert_ui  (HTMX-based, stubbed)
- Progress: Progress context manager

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

from __future__ import annotations

from typing import Any

import dominate.tags as dtags
import dominate.util as dutil
import markdown as md_lib


# ---------------------------------------------------------------------------
# Type aliases (replacing Shiny's ui.Tag / ui.TagChild / ui.TagList)
# ---------------------------------------------------------------------------
Tag = Any
TagChild = Any
TagList = list


# ---------------------------------------------------------------------------
# Basic HTML elements
# ---------------------------------------------------------------------------

class tags:
    """Namespace mirroring Shiny's ui.tags.* for HTML element creation."""

    @staticmethod
    def div(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.div, children, attrs)

    @staticmethod
    def p(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.p, children, attrs)

    @staticmethod
    def span(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.span, children, attrs)

    @staticmethod
    def strong(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.strong, children, attrs)

    @staticmethod
    def em(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.em, children, attrs)

    @staticmethod
    def a(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.a, children, attrs)

    @staticmethod
    def i(**attrs: Any) -> Tag:
        return _tag(dtags.i, (), attrs)

    @staticmethod
    def ul(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.ul, children, attrs)

    @staticmethod
    def li(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.li, children, attrs)

    @staticmethod
    def table(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.table, children, attrs)

    @staticmethod
    def thead(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.thead, children, attrs)

    @staticmethod
    def tbody(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.tbody, children, attrs)

    @staticmethod
    def tr(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.tr, children, attrs)

    @staticmethod
    def th(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.th, children, attrs)

    @staticmethod
    def td(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.td, children, attrs)

    @staticmethod
    def pre(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.pre, children, attrs)

    @staticmethod
    def code(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.code, children, attrs)

    @staticmethod
    def script(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.script, children, attrs)

    @staticmethod
    def hr(**attrs: Any) -> Tag:
        return _tag(dtags.hr, (), attrs)

    @staticmethod
    def img(**attrs: Any) -> Tag:
        return _tag(dtags.img, (), attrs)

    @staticmethod
    def label(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.label, children, attrs)

    @staticmethod
    def br() -> Tag:
        return dtags.br()

    @staticmethod
    def h3(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.h3, children, attrs)

    @staticmethod
    def h4(*children: Any, **attrs: Any) -> Tag:
        return _tag(dtags.h4, children, attrs)


def div(*children: Any, **attrs: Any) -> Tag:
    return _tag(dtags.div, children, attrs)


def p(*children: Any, **attrs: Any) -> Tag:
    return _tag(dtags.p, children, attrs)


def hr(**attrs: Any) -> Tag:
    return _tag(dtags.hr, (), attrs)


def card(*children: Any, **attrs: Any) -> Tag:
    """Bootstrap card wrapper."""
    attrs.setdefault("class_", "card")
    outer = _tag(dtags.div, (), attrs)
    body = dtags.div(cls="card-body")
    for child in children:
        body.add(child)
    outer.add(body)
    return outer


def card_header(*children: Any, **attrs: Any) -> Tag:
    attrs.setdefault("class_", "card-header")
    return _tag(dtags.div, children, attrs)


def HTML(text: str) -> Tag:  # noqa: N802
    """Inject raw HTML (like Shiny's ui.HTML)."""
    return dutil.raw(text)


def markdown(text: str) -> Tag:
    """Render markdown string to HTML."""
    html_str = md_lib.markdown(text, extensions=["tables", "fenced_code"])
    return dutil.raw(html_str)


# ---------------------------------------------------------------------------
# Layout helpers (Bootstrap grid)
# ---------------------------------------------------------------------------

def row(*children: Any, **attrs: Any) -> Tag:
    attrs.setdefault("class_", "row")
    return _tag(dtags.div, children, attrs)


def column(width: int, *children: Any, **attrs: Any) -> Tag:
    cls = f"col-md-{width}"
    existing = attrs.pop("class_", "")
    attrs["class_"] = f"{cls} {existing}".strip() if existing else cls
    return _tag(dtags.div, children, attrs)


# ---------------------------------------------------------------------------
# Form inputs (server-rendered HTML)
# ---------------------------------------------------------------------------

def input_action_button(
    id: str,
    label: Any,
    *,
    icon: Any = None,
    class_: str = "btn btn-default",
    **attrs: Any,
) -> Tag:
    """Render an action button."""
    btn = dtags.button(id=id, type="button", cls=class_, **_clean_attrs(attrs))
    if icon:
        btn.add(icon)
    btn.add(label)
    return btn


def input_selectize(
    id: str,
    label: Any,
    choices: dict[str, str] | list[str] | None = None,
    *,
    selected: str | list[str] | None = None,
    multiple: bool = False,
    options: dict[str, Any] | None = None,
    **attrs: Any,
) -> Tag:
    """Render a selectize (enhanced select) input."""
    wrapper = dtags.div(cls="form-group")
    if label:
        wrapper.add(_label_for(label, id))
    sel = dtags.select(id=id, cls="form-control selectize", **_clean_attrs(attrs))
    if multiple:
        sel["multiple"] = "multiple"
    choices_dict = _normalize_choices(choices)
    selected_set = set(selected) if isinstance(selected, list) else ({selected} if selected else set())
    for value, text in choices_dict.items():
        opt = dtags.option(text, value=value)
        if value in selected_set:
            opt["selected"] = "selected"
        sel.add(opt)
    wrapper.add(sel)
    return wrapper


def input_slider(
    id: str,
    label: str,
    *,
    min: float = 0,
    max: float = 1,
    value: float | list[float] | None = None,
    step: float | None = None,
    **attrs: Any,
) -> Tag:
    """Render a range slider input."""
    wrapper = dtags.div(cls="form-group")
    wrapper.add(_label_for(label, id))
    inp_attrs: dict[str, Any] = {"type": "range", "id": id, "min": str(min), "max": str(max)}
    if step is not None:
        inp_attrs["step"] = str(step)
    if value is not None:
        inp_attrs["value"] = str(value[0] if isinstance(value, list) else value)
    wrapper.add(dtags.input_(**inp_attrs, cls="form-range", **_clean_attrs(attrs)))
    return wrapper


def input_checkbox(
    id: str,
    label: Any,
    value: bool = False,
    **attrs: Any,
) -> Tag:
    """Render a checkbox input."""
    wrapper = dtags.div(cls="form-check")
    inp = dtags.input_(id=id, type="checkbox", cls="form-check-input", **_clean_attrs(attrs))
    if value:
        inp["checked"] = "checked"
    wrapper.add(inp)
    if label:
        wrapper.add(_label_for(label, id, cls="form-check-label"))
    return wrapper


def input_numeric(
    id: str,
    label: str,
    value: int | float = 0,
    *,
    min: int | float | None = None,
    max: int | float | None = None,
    step: int | float | None = None,
    **attrs: Any,
) -> Tag:
    """Render a numeric input."""
    wrapper = dtags.div(cls="form-group")
    wrapper.add(_label_for(label, id))
    inp_attrs: dict[str, Any] = {"type": "number", "id": id, "value": str(value)}
    if min is not None:
        inp_attrs["min"] = str(min)
    if max is not None:
        inp_attrs["max"] = str(max)
    if step is not None:
        inp_attrs["step"] = str(step)
    wrapper.add(dtags.input_(cls="form-control", **inp_attrs, **_clean_attrs(attrs)))
    return wrapper


def input_text(
    id: str,
    label: str,
    value: str = "",
    *,
    placeholder: str = "",
    **attrs: Any,
) -> Tag:
    """Render a text input."""
    wrapper = dtags.div(cls="form-group")
    wrapper.add(_label_for(label, id))
    wrapper.add(dtags.input_(
        id=id, type="text", value=value, placeholder=placeholder,
        cls="form-control", **_clean_attrs(attrs)
    ))
    return wrapper


def input_select(
    id: str,
    label: str,
    choices: dict[str, str] | list[str] | None = None,
    *,
    selected: str | None = None,
    **attrs: Any,
) -> Tag:
    """Render a standard select input."""
    wrapper = dtags.div(cls="form-group")
    wrapper.add(_label_for(label, id))
    sel = dtags.select(id=id, cls="form-control", **_clean_attrs(attrs))
    choices_dict = _normalize_choices(choices)
    for value, text in choices_dict.items():
        opt = dtags.option(text, value=value)
        if value == selected:
            opt["selected"] = "selected"
        sel.add(opt)
    wrapper.add(sel)
    return wrapper


# ---------------------------------------------------------------------------
# Modal system
# ---------------------------------------------------------------------------

def modal(
    *body: Any,
    title: str = "",
    footer: Any = None,
    easy_close: bool = True,
    size: str = "m",
    **attrs: Any,
) -> Tag:
    """Build a Bootstrap modal HTML fragment."""
    size_class = {"s": "modal-sm", "m": "", "l": "modal-lg", "xl": "modal-xl"}.get(size, "")

    modal_div = dtags.div(
        cls="modal fade", id="sharp-modal", tabindex="-1",
        role="dialog", **_clean_attrs(attrs)
    )
    if easy_close:
        modal_div["data-bs-backdrop"] = "true"
        modal_div["data-bs-keyboard"] = "true"

    dialog = dtags.div(cls=f"modal-dialog {size_class}".strip())
    content = dtags.div(cls="modal-content")

    # Header
    header = dtags.div(cls="modal-header")
    header.add(dtags.h5(title, cls="modal-title"))
    header.add(dtags.button(
        type="button", cls="btn-close", **{"data-bs-dismiss": "modal"}
    ))
    content.add(header)

    # Body
    modal_body = dtags.div(cls="modal-body")
    for child in body:
        modal_body.add(child)
    content.add(modal_body)

    # Footer
    if footer is not None:
        modal_footer = dtags.div(cls="modal-footer")
        if isinstance(footer, (list, TagList)):
            for item in footer:
                modal_footer.add(item)
        else:
            modal_footer.add(footer)
        content.add(modal_footer)

    dialog.add(content)
    modal_div.add(dialog)
    return modal_div


def modal_button(label: str, **attrs: Any) -> Tag:
    """A button that dismisses the modal."""
    attrs.setdefault("class_", "btn btn-secondary")
    btn = dtags.button(label, type="button", **_clean_attrs(attrs))
    btn["data-bs-dismiss"] = "modal"
    return btn


def output_ui(id: str, **kwargs: Any) -> Tag:
    """Placeholder for dynamic server-rendered output."""
    return dtags.div(id=id, cls="ui-output-placeholder")


# ---------------------------------------------------------------------------
# Nav / Tab helpers
# ---------------------------------------------------------------------------

def nav_panel(title: str, *children: Any, value: str | None = None, **attrs: Any) -> Tag:
    panel = dtags.div(cls="tab-pane", id=value or title.lower().replace(" ", "-"))
    for child in children:
        panel.add(child)
    return panel


def navset_tab(*panels: Any, id: str = "", **attrs: Any) -> Tag:
    wrapper = dtags.div(id=id, cls="nav-tabs-container")
    for panel in panels:
        wrapper.add(panel)
    return wrapper


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _label_for(text: Any, for_id: str, **attrs: Any) -> Tag:
    """Create a <label> with a proper 'for' attribute."""
    lbl = dtags.label(text, **attrs)
    lbl["for"] = for_id
    return lbl


def _tag(tag_fn: Any, children: tuple, attrs: dict[str, Any]) -> Tag:
    """Create a dominate tag, handling class_ -> cls renaming."""
    cleaned = _clean_attrs(attrs)
    for_value = cleaned.pop("__for", None)
    el = tag_fn(**cleaned)
    if for_value is not None:
        el["for"] = for_value
    for child in children:
        if child is not None:
            el.add(child)
    return el


def _clean_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Convert Shiny-style attributes to dominate-compatible ones."""
    result = {}
    for key, value in attrs.items():
        if key == "class_":
            result["cls"] = value
        elif key == "for_":
            # Use bracket assignment after creation; pass as __for marker
            result["__for"] = value
        elif key.startswith("data_"):
            result[key.replace("_", "-")] = value
        else:
            result[key] = value
    return result


def _normalize_choices(choices: dict[str, str] | list[str] | None) -> dict[str, str]:
    """Normalize choices to {value: label} dict."""
    if choices is None:
        return {}
    if isinstance(choices, list):
        return {c: c for c in choices}
    return choices

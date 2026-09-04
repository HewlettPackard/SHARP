"""Regression tests for dynamic input value race conditions.

These tests encode structural rules for Shiny render helpers used in the GUI:
inputs created inside dynamically re-rendered functions should not bind their
initial ``value=`` directly to mutable reactive-derived state, because doing so
can recreate/reset the DOM control and clobber in-progress user interaction.
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_module(relative_path: str) -> ast.Module:
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    return ast.parse(source)


def _find_function(node: ast.AST, function_name: str) -> ast.FunctionDef:
    for child in ast.walk(node):
        if isinstance(child, ast.FunctionDef) and child.name == function_name:
            return child
    raise AssertionError(f"Function {function_name!r} not found")


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
        return ".".join(reversed(parts))
    return None


def _constant_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _find_matching_calls(function_node: ast.FunctionDef, dotted_name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function_node)
        if isinstance(node, ast.Call) and _call_name(node) == dotted_name
    ]


def _has_keyword(call: ast.Call, keyword_name: str) -> bool:
    return any(keyword.arg == keyword_name for keyword in call.keywords if keyword.arg is not None)


def _keyword_is_constant(call: ast.Call, keyword_name: str) -> bool:
    """Return True if the keyword exists and its value is a static literal."""
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return isinstance(keyword.value, ast.Constant)
    return False


def _is_reactive_isolate_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "reactive"
        and node.func.attr == "isolate"
    )


def _call_matches_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) == name


def _is_resolved_not_none_test(node: ast.AST) -> bool:
    """Return True for `resolved is not None` compare expressions."""
    return (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "resolved"
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.IsNot)
        and len(node.comparators) == 1
        and isinstance(node.comparators[0], ast.Constant)
        and node.comparators[0].value is None
    )


def _if_contains_call(if_node: ast.If, dotted_name: str) -> bool:
    """Return True if the if-body contains a call to `dotted_name`."""
    for node in ast.walk(if_node):
        if _call_matches_name(node, dotted_name):
            return True
    return False


class TestReactiveInputValueRegressions:
    """Tests for known dynamic-input race condition patterns."""

    def test_measure_bench_selector_should_not_bind_input_text_value(self):
        """Dynamic bench selector should not recreate the bench input with value=."""
        module = _parse_module("src/gui/modules/measure.py")
        bench_selector = _find_function(module, "bench_selector")
        input_calls = _find_matching_calls(bench_selector, "ui.input_text")

        bench_calls = [
            call for call in input_calls
            if call.args and _constant_str(call.args[0]) == "bench"
        ]

        assert bench_calls, "Expected bench_selector to define the bench input"
        assert all(
            not _has_keyword(call, "value") for call in bench_calls
        ), "bench_selector recreates the bench input with value=, which can overwrite user edits"

    def test_profile_num_perf_groups_uses_shiny_numeric_binding(self):
        """num_perf_groups must use ui.input_numeric so ui.update_numeric can restore values."""
        module = _parse_module("src/gui/utils/profile/factor_ui.py")
        selector = _find_function(module, "profile_factor_selector")
        numeric_calls = _find_matching_calls(selector, "ui.input_numeric")

        perf_group_calls = [
            call for call in numeric_calls
            if call.args and _constant_str(call.args[0]) == "num_perf_groups"
        ]

        assert perf_group_calls, "Expected profile_factor_selector to define num_perf_groups"
        # value= is OK only if it's a static literal (e.g. "2"), not a variable
        for call in perf_group_calls:
            if _has_keyword(call, "value"):
                assert _keyword_is_constant(call, "value"), (
                    "num_perf_groups has a non-constant value= binding — "
                    "use a static default and ui.update_numeric() for state changes"
                )

    def test_profile_num_perf_groups_not_raw_html_number_input(self):
        """Guard against raw HTML number input which bypasses ui.update_numeric restore."""
        module = _parse_module("src/gui/utils/profile/factor_ui.py")
        selector = _find_function(module, "profile_factor_selector")
        input_calls = _find_matching_calls(selector, "ui.tags.input")

        perf_group_calls = []
        for call in input_calls:
            for keyword in call.keywords:
                if keyword.arg == "id" and _constant_str(keyword.value) == "num_perf_groups":
                    perf_group_calls.append(call)

        assert not perf_group_calls, (
            "num_perf_groups should use ui.input_numeric, not ui.tags.input(type='number')"
        )

    def test_profile_factor_selector_has_no_reactive_dependencies(self):
        """profile_factor_selector must have zero reactive dependencies.

        Any reactive read (active_data, input.profile_task, etc) would
        cause the parent to re-render on state changes, recreating source
        inputs and triggering a race with ui.update_* restore calls.
        Task resets must use ui.update_* only, never re-render the parent.
        """
        module = _parse_module("src/gui/utils/profile/factor_ui.py")
        selector = _find_function(module, "profile_factor_selector")

        # Check for any function calls that could be reactive reads
        reactive_reads = []
        for node in ast.walk(selector):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name is None:
                continue
            # Known reactive sources that would cause re-renders
            if name in ("active_data", "input.profile_task",
                        "current_labeler.get", "profile_md_settings"):
                reactive_reads.append(name)

        assert not reactive_reads, (
            f"profile_factor_selector reads reactive sources {reactive_reads}; "
            "this causes re-renders that recreate inputs and race with restores"
        )

    def test_profile_auto_checkbox_no_reactive_value_binding(self):
        """perf_auto_detect checkbox should not have a reactive value= binding."""
        module = _parse_module("src/gui/utils/profile/factor_ui.py")
        selector = _find_function(module, "profile_factor_selector")
        checkbox_calls = _find_matching_calls(selector, "ui.input_checkbox")

        auto_calls = [
            call for call in checkbox_calls
            if call.args and _constant_str(call.args[0]) == "perf_auto_detect"
        ]

        assert auto_calls, "Expected profile_factor_selector to define perf_auto_detect"
        assert all(
            not _has_keyword(call, "value") for call in auto_calls
        ), "perf_auto_detect has a value= binding — omit it and use ui.update_checkbox() for state changes"

    def test_cutoff_actions_does_not_recreate_source_inputs(self):
        """render_cutoff_actions must not create perf_auto_detect or num_perf_groups."""
        module = _parse_module("src/gui/utils/profile/labeler_ui.py")
        actions_fn = _find_function(module, "render_cutoff_actions")

        checkbox_calls = _find_matching_calls(actions_fn, "ui.input_checkbox")
        auto_calls = [
            call for call in checkbox_calls
            if call.args and _constant_str(call.args[0]) == "perf_auto_detect"
        ]
        assert not auto_calls, "render_cutoff_actions must not create perf_auto_detect"

        input_calls = _find_matching_calls(actions_fn, "ui.tags.input")
        group_calls = [
            call for call in input_calls
            for kw in call.keywords
            if kw.arg == "id" and _constant_str(kw.value) == "num_perf_groups"
        ]
        assert not group_calls, "render_cutoff_actions must not create num_perf_groups"

    def test_restore_labeler_uses_base_data_not_active_data(self):
        """Saved cutoffs must be restored from unfiltered base_data()."""
        module = _parse_module("src/gui/modules/profile.py")
        restore_fn = _find_function(module, "_restore_labeler_from_markdown")

        active_calls = [
            node for node in ast.walk(restore_fn)
            if _call_matches_name(node, "active_data")
        ]
        base_calls = [
            node for node in ast.walk(restore_fn)
            if _call_matches_name(node, "base_data")
        ]

        assert not active_calls, (
            "_restore_labeler_from_markdown reads active_data(); stale filters can "
            "clip valid saved cutoffs and force fallback to default group cutoffs"
        )
        assert base_calls, "_restore_labeler_from_markdown should read base_data()"

    def test_profile_predictor_rows_bind_checkbox_value_from_exclusions(self):
        """Predictor rows must bind checkbox value from computed exclusions.

        Without a value binding on row creation, the first modal paint can show
        unchecked boxes when ui.update_checkbox races before inputs are mounted.
        """
        module = _parse_module("src/gui/utils/profile/exclusions.py")
        build_rows = _find_function(module, "_build_predictor_table_rows")
        checkbox_calls = _find_matching_calls(build_rows, "ui.input_checkbox")

        assert checkbox_calls, "Expected _build_predictor_table_rows to define predictor checkboxes"
        assert all(
            _has_keyword(call, "value") for call in checkbox_calls
        ), "_build_predictor_table_rows must pass value= so initial modal render reflects exclusions"

    def test_handle_num_groups_change_guards_on_pending_restore(self):
        """_handle_num_groups_change must check pending_labeler_restore before rebuilding.

        When a markdown restore is pending, a delayed browser round-trip from
        ui.update_numeric("num_perf_groups", 2) would otherwise arrive and
        overwrite the just-restored labeler (e.g. a 4-group ManualLabeler with
        saved cutoffs would be replaced by a default 2-group labeler).
        """
        module = _parse_module("src/gui/utils/profile/labeler_ui.py")
        fn = _find_function(module, "_handle_num_groups_change")

        restore_reads = [
            node for node in ast.walk(fn)
            if (_call_matches_name(node, "pending_labeler_restore.needs")
                or _call_matches_name(node, "pending_labeler_restore.get"))
        ]

        assert restore_reads, (
            "_handle_num_groups_change does not guard on pending_labeler_restore; "
            "a delayed ui.update_numeric round-trip will overwrite the restored labeler"
        )

    def test_restore_labeler_reads_pending_restore(self):
        """_restore_labeler_from_markdown must read pending_restore.get().

        Reading profile_md_settings() lazily creates a race: by the time the
        effect fires the reactive calc may already reflect a different task.
        """
        module = _parse_module("src/gui/modules/profile.py")
        restore_fn = _find_function(module, "_restore_labeler_from_markdown")

        pending_reads = [
            node for node in ast.walk(restore_fn)
            if _call_matches_name(node, "pending_restore.get")
        ]

        assert pending_reads, (
            "_restore_labeler_from_markdown does not read pending_restore.get(); "
            "reading profile_md_settings() lazily is a race that loses saved cutoffs on task switch"
        )

    def test_initialize_labeler_reads_restore_flag_via_isolate(self):
        """_initialize_labeler must read pending_labeler_restore inside reactive.isolate().

        Reading via isolate prevents the clearing of pending_restore from
        re-triggering _initialize_labeler.
        """
        module = _parse_module("src/gui/utils/profile/labeler_ui.py")
        fn = _find_function(module, "_initialize_labeler")

        restore_reads = [
            node for node in ast.walk(fn)
            if _call_matches_name(node, "pending_labeler_restore.get")
        ]
        assert restore_reads, (
            "_initialize_labeler does not check pending_labeler_restore"
        )

        # Verify all restore reads are inside a reactive.isolate() context
        for with_node in ast.walk(fn):
            if not isinstance(with_node, ast.With):
                continue
            for item in with_node.items:
                if _is_reactive_isolate_call(item.context_expr):
                    for inner_node in ast.walk(with_node):
                        if _call_matches_name(inner_node, "pending_labeler_restore.get"):
                            return  # Found it inside isolate — test passes

        raise AssertionError(
            "_initialize_labeler reads pending_labeler_restore outside "
            "reactive.isolate(); clearing the flag after restore will re-trigger "
            "the effect and overwrite the restored labeler with stale num_groups"
        )

    def test_check_prof_file_does_not_update_num_perf_groups(self):
        """_check_prof_file must not call ui.update_numeric("num_perf_groups", ...).

        Sending ui.update_numeric("num_perf_groups", 2) from _check_prof_file
        generates a delayed browser round-trip.  By the time the browser sends
        the change event back, _restore_labeler_from_markdown has already set
        the correct restored labeler.  _handle_num_groups_change then fires
        with the stale num_groups=2 and overwrites the restored labeler.

        The num_perf_groups update is now handled exclusively by
        _restore_labeler_from_markdown (either to the restored group count
        or to the default 2 when nothing to restore).
        """
        module = _parse_module("src/gui/modules/profile.py")
        fn = _find_function(module, "_check_prof_file")

        update_calls = _find_matching_calls(fn, "ui.update_numeric")
        num_group_updates = [
            call for call in update_calls
            if call.args and _constant_str(call.args[0]) == "num_perf_groups"
        ]

        assert not num_group_updates, (
            "_check_prof_file calls ui.update_numeric('num_perf_groups', ...); "
            "this generates a stale browser round-trip that overwrites the "
            "restored labeler — move the update to _restore_labeler_from_markdown"
        )

    def test_resolve_filter_metric_selection_uses_md_settings_fallback_on_task_change(self):
        """On task switch, resolve_filter_metric_selection must read md_settings for fallback.

        When pending_restore is None (execution-order edge case: snapshot not set yet),
        the task-change path must consult md_settings as a fallback.  Without it the
        filter metric is reset to PLACEHOLDER even though the task has a saved filter.

        The logic lives in the pure helper restore.resolve_filter_metric_selection so
        it can be tested without Shiny reactive machinery.
        """
        module = _parse_module("src/gui/utils/profile/restore.py")
        fn = _find_function(module, "resolve_filter_metric_selection")

        def _is_task_changed_if(node: ast.AST) -> bool:
            return (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "task_changed"
            )

        task_changed_block = None
        for node in ast.walk(fn):
            if _is_task_changed_if(node):
                task_changed_block = node
                break

        assert task_changed_block is not None, (
            "resolve_filter_metric_selection has no `if task_changed:` block; "
            "the task-change path must be separated from the same-task path"
        )

        md_attrs = [
            node for node in ast.walk(task_changed_block)
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "default_filter_metric"
                and isinstance(node.value, ast.Name)
                and node.value.id == "md_settings"
            )
        ]
        assert md_attrs, (
            "The `if task_changed:` block does not access md_settings.default_filter_metric; "
            "if pending_restore has not been set yet the saved filter metric is never restored"
        )

    def test_resolve_filter_metric_selection_checks_snapshot_before_input_on_same_task_change(self):
        """On same-task metric change, resolve_filter_metric_selection checks snapshot first.

        The A→B→A round-trip failure: after switching back to A the browser emits
        ``profile_metric`` before ``profile_filter_metric`` arrives, so
        ``current_filter`` still holds task B's stale column.  The pending-restore
        snapshot is still live at that point and contains task A's correct filter.
        The helper must check ``snapshot`` before falling back to ``current_filter``.

        resolve_filter_metric_selection uses early-return in the ``if task_changed:``
        block, so the same-task logic is the code that comes *after* that block
        in the function body (not an else branch).
        """
        module = _parse_module("src/gui/utils/profile/restore.py")
        fn = _find_function(module, "resolve_filter_metric_selection")

        def _is_task_changed_if(node: ast.AST) -> bool:
            return (
                isinstance(node, ast.If)
                and isinstance(node.test, ast.Name)
                and node.test.id == "task_changed"
            )

        # Find the position of `if task_changed:` in the function body.
        tc_idx: int | None = None
        for i, stmt in enumerate(fn.body):
            if _is_task_changed_if(stmt):
                tc_idx = i
                break

        assert tc_idx is not None, "resolve_filter_metric_selection has no `if task_changed:` block"

        # The same-task path is the statements that follow the early-return block.
        same_task_stmts = fn.body[tc_idx + 1:]
        assert same_task_stmts, (
            "resolve_filter_metric_selection has no code after `if task_changed:` "
            "(same-task branch is missing)"
        )

        # snapshot.default_filter_metric must be accessed in the same-task block.
        snapshot_attrs = [
            node
            for stmt in same_task_stmts
            for node in ast.walk(stmt)
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "default_filter_metric"
                and isinstance(node.value, ast.Name)
                and node.value.id == "snapshot"
            )
        ]
        assert snapshot_attrs, (
            "The same-task section of resolve_filter_metric_selection does not access "
            "snapshot.default_filter_metric; the stale-input race is not guarded against"
        )

        # current_filter must also be accessed in the same-task block.
        current_filter_refs = [
            node
            for stmt in same_task_stmts
            for node in ast.walk(stmt)
            if isinstance(node, ast.Name) and node.id == "current_filter"
        ]
        assert current_filter_refs, (
            "The same-task section of resolve_filter_metric_selection does not access "
            "current_filter at all"
        )

    def test_update_filter_choices_guards_filter_preservation_on_task_change(self):
        """_update_filter_choices must only read input.profile_filter_metric() on same-task changes.

        The fix uses a ``_last_filter_task`` tracker so the guard can distinguish a
        task switch from a same-task metric change.  ``input.profile_filter_metric()``
        must be guarded by ``not task_changed`` (either an ``if`` statement or an
        inline ternary expression).
        """
        module = _parse_module("src/gui/modules/profile.py")
        fn = _find_function(module, "_update_filter_choices")

        # 1. Verify the task-change tracker is referenced inside the function.
        task_tracker_refs = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Name) and node.id == "_last_filter_task"
        ]
        assert task_tracker_refs, (
            "_update_filter_choices does not track the last task (_last_filter_task); "
            "it cannot distinguish a task switch from a same-task metric change"
        )

        # 2. Verify that every call to input.profile_filter_metric() is guarded by
        #    `not task_changed`, either as an `if`-statement condition or as the
        #    test of a ternary (IfExp) expression.
        def _is_not_task_changed_test(test: ast.AST) -> bool:
            return (
                isinstance(test, ast.UnaryOp)
                and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Name)
                and test.operand.id == "task_changed"
            )

        def _contains_filter_metric_call(node: ast.AST) -> bool:
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "profile_filter_metric"
                    and isinstance(inner.func.value, ast.Name)
                    and inner.func.value.id == "input"
                ):
                    return True
            return False

        guarded_access = False
        for node in ast.walk(fn):
            # Accept `if not task_changed:` block
            if isinstance(node, ast.If) and _is_not_task_changed_test(node.test):
                if _contains_filter_metric_call(node):
                    guarded_access = True
                    break
            # Accept `... if not task_changed else ...` ternary
            if isinstance(node, ast.IfExp) and _is_not_task_changed_test(node.test):
                if _contains_filter_metric_call(node.body):
                    guarded_access = True
                    break

        assert guarded_access, (
            "_update_filter_choices reads input.profile_filter_metric() without a "
            "`not task_changed` guard; on task switch the old filter metric is "
            "preserved instead of being reset to the placeholder"
        )

    def test_update_filter_choices_reacts_to_task_changes(self):
        """_update_filter_choices must fire on profile_task changes, not only profile_metric.

        When only ``input.profile_metric`` is in ``@reactive.event()``,
        switching to a task that shares the same outcome metric never fires the
        effect.  The filter-metric selector is never reset, so the previous
        task's saved filter (e.g. ``node_misses``) bleeds into the new task.
        """
        module = _parse_module("src/gui/modules/profile.py")
        fn = _find_function(module, "_update_filter_choices")

        event_args: list[str] = []
        for decorator in fn.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if _call_name(decorator) != "reactive.event":
                continue
            for arg in decorator.args:
                if isinstance(arg, ast.Attribute):
                    event_args.append(arg.attr)

        assert "profile_task" in event_args, (
            "_update_filter_choices @reactive.event does not include input.profile_task; "
            "switching tasks without changing the outcome metric never fires the "
            "effect and leaves the old task's filter metric selected"
        )

    def test_profile_filter_visibility_clears_pending_restore_after_applying_preset(self):
        """profile_filter_visibility must mark filter preset as applied.

        Without the guard flag, later user-driven filter-metric changes can
        keep trying to apply stale restored values from a different metric
        instead of using the new metric's default full range.  The function
        should set ``_filter_preset_applied`` rather than clearing
        ``pending_restore`` so the labeler restore can still read the snapshot.
        """
        module = _parse_module("src/gui/modules/profile.py")
        fn = _find_function(module, "profile_filter_visibility")

        set_calls = [
            node for node in ast.walk(fn)
            if _call_matches_name(node, "_filter_preset_applied.set")
        ]
        assert set_calls, (
            "profile_filter_visibility does not set _filter_preset_applied; "
            "stale restored filter values can leak into later manual metric changes"
        )

        resolved_guarded_set = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            if _is_resolved_not_none_test(node.test) and _if_contains_call(node, "_filter_preset_applied.set"):
                resolved_guarded_set = True
                break

        assert resolved_guarded_set, (
            "profile_filter_visibility must set _filter_preset_applied inside "
            "the `if resolved is not None` branch so it only applies once"
        )

    def test_profile_filter_visibility_reads_pending_filter_preset(self):
        """profile_filter_visibility must read _pending_filter_preset, not pending_restore.

        pending_restore is consumed (set to None) by _restore_labeler_from_markdown
        before profile_filter_visibility fires.  A dedicated _pending_filter_preset
        reactive value survives independently so the filter slider value can be
        restored regardless of execution order.
        """
        module = _parse_module("src/gui/modules/profile.py")
        fn = _find_function(module, "profile_filter_visibility")

        reads_dedicated = [
            node for node in ast.walk(fn)
            if _call_matches_name(node, "_pending_filter_preset.get")
        ]
        assert reads_dedicated, (
            "profile_filter_visibility does not read _pending_filter_preset.get(); "
            "if it reads pending_restore instead, the filter value will be lost when "
            "_restore_labeler_from_markdown runs first and clears pending_restore"
        )

    def test_profile_filter_visibility_uses_keep_current_on_rerender(self):
        """profile_filter_visibility must pass KEEP_CURRENT to prevent slider reset.

        When the filter preset has already been applied, subsequent re-renders
        of profile_filter_visibility must NOT reset the slider to full range.
        It should pass KEEP_CURRENT to update_filter_widget so the slider
        retains the user's (or restored) value.
        """
        module = _parse_module("src/gui/modules/profile.py")
        fn = _find_function(module, "profile_filter_visibility")

        has_keep_current = False
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id == "KEEP_CURRENT":
                has_keep_current = True
                break

        assert has_keep_current, (
            "profile_filter_visibility does not reference KEEP_CURRENT; "
            "without it, subsequent re-renders reset the slider to full range "
            "and clobber the restored filter value"
        )

    def test_sync_checkbox_states_skips_updates_when_exclusions_unchanged(self):
        """_sync_checkbox_states must early-return when exclusions are unchanged.

        Re-pushing ui.update_checkbox on every modal input change can clobber
        in-progress user checkbox interactions and cause checked items to flip
        back immediately.
        """
        module = _parse_module("src/gui/utils/profile/exclusions.py")
        fn = _find_function(module, "_sync_checkbox_states")

        has_last_assignment = False
        has_unchanged_guard_return = False
        has_last_update = False

        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "last":
                        has_last_assignment = True
                    if isinstance(target, ast.Subscript):
                        if isinstance(target.value, ast.Name) and target.value.id == "_last_synced_exclusions":
                            has_last_update = True

            if isinstance(node, ast.If):
                # Look for: if last is not None and last == exclusions: return
                has_last_not_none = any(
                    isinstance(inner, ast.Compare)
                    and isinstance(inner.left, ast.Name)
                    and inner.left.id == "last"
                    and len(inner.ops) == 1
                    and isinstance(inner.ops[0], ast.IsNot)
                    and len(inner.comparators) == 1
                    and isinstance(inner.comparators[0], ast.Constant)
                    and inner.comparators[0].value is None
                    for inner in ast.walk(node.test)
                )
                has_last_eq_exclusions = any(
                    isinstance(inner, ast.Compare)
                    and isinstance(inner.left, ast.Name)
                    and inner.left.id == "last"
                    and len(inner.ops) == 1
                    and isinstance(inner.ops[0], ast.Eq)
                    and len(inner.comparators) == 1
                    and isinstance(inner.comparators[0], ast.Name)
                    and inner.comparators[0].id == "exclusions"
                    for inner in ast.walk(node.test)
                )
                has_return = any(isinstance(body_node, ast.Return) for body_node in node.body)

                if has_last_not_none and has_last_eq_exclusions and has_return:
                    has_unchanged_guard_return = True

        assert has_last_assignment, (
            "_sync_checkbox_states should read the previously synced exclusions "
            "before deciding whether to push checkbox updates"
        )
        assert has_unchanged_guard_return, (
            "_sync_checkbox_states must early-return when exclusions are unchanged; "
            "otherwise checkbox clicks can be overwritten by re-sync updates"
        )
        assert has_last_update, (
            "_sync_checkbox_states should update _last_synced_exclusions after "
            "detecting a changed exclusion set"
        )

    def test_sync_checkbox_states_always_syncs_on_modal_reopen(self):
        """_sync_checkbox_states must force a sync when the modal is freshly opened.

        Regression test for: checkboxes show unchecked even though excluded_predictors
        has entries.  Root cause: the _last_synced_exclusions early-return was hit on
        every modal reopen when the excluded set hadn't changed since the last open.

        The fix tracks filter-dict identity: build_predictor_exclusion_modal always
        creates a fresh dict object, so `filters is not _last_known_filters["value"]`
        detects a new modal open and forces a sync regardless of whether exclusions
        are the same.

        This test checks that:
        1. A `_last_known_filters` closure variable is declared in
           create_predictor_exclusion_ui.
        2. _sync_checkbox_states performs an identity (`is not`) comparison on
           the filters dict.
        3. The early-return guard includes `not modal_opened` (or equivalent) so
           the identity check can override the exclusions-unchanged short-circuit.
        """
        module = _parse_module("src/gui/utils/profile/exclusions.py")
        outer_fn = _find_function(module, "create_predictor_exclusion_ui")
        fn = _find_function(module, "_sync_checkbox_states")

        # 1. _last_known_filters must be declared in the outer closure.
        has_last_known_filters = False
        for node in ast.walk(outer_fn):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name) and "last_known_filters" in t.id:
                        has_last_known_filters = True
                        break
        assert has_last_known_filters, (
            "create_predictor_exclusion_ui does not declare a _last_known_filters "
            "closure variable; reopening the modal with the same exclusions will "
            "skip the sync and leave all checkboxes unchecked"
        )

        # 2. _sync_checkbox_states must use an `is not` identity comparison on filters.
        has_is_not_filters = False
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare):
                if (
                    len(node.ops) == 1
                    and isinstance(node.ops[0], ast.IsNot)
                    and (
                        (isinstance(node.left, ast.Name) and node.left.id == "filters")
                        or any(
                            isinstance(c, ast.Name) and c.id == "filters"
                            for c in node.comparators
                        )
                    )
                ):
                    has_is_not_filters = True
                    break
        assert has_is_not_filters, (
            "_sync_checkbox_states does not compare `filters` by identity (`is not`); "
            "reopening the modal cannot be distinguished from a spurious re-fire"
        )

        # 3. The early-return guard must also check `not modal_opened` so a new modal
        #    open forces the sync even when the exclusion set is unchanged.
        has_modal_opened_guard = False
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                for inner in ast.walk(node.test):
                    if isinstance(inner, ast.Name) and "modal_opened" in inner.id:
                        if any(isinstance(stmt, ast.Return) for stmt in node.body):
                            has_modal_opened_guard = True
                            break
        assert has_modal_opened_guard, (
            "_sync_checkbox_states early-return guard does not check modal_opened; "
            "reopening with unchanged exclusions will skip the sync"
        )

    def test_initialize_labeler_reads_auto_detect_before_isolate(self):
        """input.perf_auto_detect() must be read before any reactive.isolate() block.

        If perf_auto_detect is read AFTER an early-return inside a
        reactive.isolate() block (e.g. the pending_labeler_restore guard),
        the reactive dependency is never established when the early-return
        fires.  Then clicking "Auto groups" has no effect because the effect
        doesn't know to re-run.
        """
        module = _parse_module("src/gui/utils/profile/labeler_ui.py")
        inner = _find_function(module, "_initialize_labeler")

        # Walk the body in order; find line of first reactive.isolate() With
        # and line of input.perf_auto_detect() call.
        first_isolate_line = None
        auto_detect_line = None
        for node in ast.walk(inner):
            if isinstance(node, ast.With):
                for item in node.items:
                    if _is_reactive_isolate_call(item.context_expr):
                        if first_isolate_line is None or node.lineno < first_isolate_line:
                            first_isolate_line = node.lineno
                        break
            if isinstance(node, ast.Call) and _call_name(node) == "input.perf_auto_detect":
                if auto_detect_line is None or node.lineno < auto_detect_line:
                    auto_detect_line = node.lineno

        assert auto_detect_line is not None, (
            "_initialize_labeler does not read input.perf_auto_detect()"
        )
        assert first_isolate_line is not None, (
            "_initialize_labeler has no reactive.isolate() block"
        )
        assert auto_detect_line < first_isolate_line, (
            "input.perf_auto_detect() is read AFTER reactive.isolate(); "
            "if the isolate block returns early, the dependency is never "
            "established and clicking 'Auto groups' has no effect"
        )

    def test_initialize_labeler_reinitializes_on_metric_change(self):
        """_initialize_labeler must reinitialize when the outcome metric changes.

        Without per-metric tracking, _should_preserve_existing_labeler may return
        True when old cutoffs happen to fall within the new column's value range,
        leaving a stale labeler from the previous metric.  The effect must track
        the last initialized metric name and bypass the range check whenever the
        metric changes.
        """
        module = _parse_module("src/gui/utils/profile/labeler_ui.py")
        fn = _find_function(module, "initialize_labeler_effect")

        has_last_metric = False
        for node in ast.walk(fn):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name) and "last" in t.id and "metric" in t.id.lower():
                        has_last_metric = True
                        break
        assert has_last_metric, (
            "initialize_labeler_effect does not declare a last-metric tracking variable; "
            "without it, changing the outcome metric may preserve stale cutoffs from "
            "the previous column when value ranges happen to overlap"
        )

        inner = _find_function(module, "_initialize_labeler")
        uses_metric_changed_guard = False
        for node in ast.walk(inner):
            if isinstance(node, ast.Name) and "metric_changed" in node.id:
                uses_metric_changed_guard = True
                break
        assert uses_metric_changed_guard, (
            "_initialize_labeler does not use a metric_changed guard; "
            "stale cutoffs from a previous metric column will be preserved "
            "when the new column's value range overlaps"
        )

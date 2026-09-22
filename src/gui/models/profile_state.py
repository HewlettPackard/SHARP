# © Copyright 2026--2026 Hewlett Packard Enterprise Development LP
"""Typed state container for the Profile page.

ProfileState centralises all URL parameter parsing, saved-settings restoration,
cross-field validation, and canonical URL construction for the Profile tab.  It
replaces the previous pattern of reading ~20 raw query params individually inside
get_profile and reconstructing the URL independently in _current_url().

Usage
-----
Route handler (parsing)::

    state = ProfileState.from_request(request)

After loading the ProfileSettings from the runlog markdown::

    state.apply_defaults(settings, available_analyzers=choices)

URL reconstruction — single source of truth::

    url = state.to_url()

Component rendering (_current_url in profile.py)::

    url = ProfileState.from_dict(data).to_url()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

if TYPE_CHECKING:
    from fastapi import Request
    from src.gui.utils.profile.restore import ProfileSettings


@dataclass
class ProfileState:
    """All typed state for a single profile page render, derived from URL params."""

    # Core identifiers
    experiment: str = ""
    task: str = ""              # primary (first) selected task label
    extra_tasks: list[str] = field(default_factory=list)  # additional tasks
    csv_path: str = ""
    metric: str = ""

    # Distribution controls
    lower_is_better: bool = True
    num_groups: int = 2
    auto_detect: bool = False
    cutoff_values: list[float] = field(default_factory=list)

    # Filter controls
    filter_metric: str = ""
    filter_min: str = ""
    filter_max: str = ""
    filter_values: list[str] = field(default_factory=list)

    # Analysis controls
    analyzer: str = ""

    # Factor / mitigation detail
    factor: str = ""
    mitigation: str = ""
    mitigation_metric: str = ""
    mitigation_csv: str = ""
    show_mitigation_modal: bool = False

    # UI navigation state
    source: str = ""
    show_profile_config: bool = False
    excluded_state: str = ""

    # Transient messages (carried through the URL, not persisted)
    notice: str | None = None
    error: str | None = None

    # Which URL param keys were explicitly present (not defaulted).
    # Used by apply_defaults() to skip restoration for already-explicit fields.
    _explicit: frozenset[str] = field(
        default_factory=frozenset, repr=False, compare=False
    )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @property
    def all_tasks(self) -> list[str]:
        """All selected task labels (primary + extra), filtering empty strings."""
        result = [self.task] if self.task else []
        result.extend(self.extra_tasks)
        return result

    @classmethod
    def from_request(cls, request: "Request") -> "ProfileState":
        """Parse all URL query params into a typed ProfileState.

        Tracks which param keys were explicitly present so that
        apply_defaults() can skip restoration for fields already provided
        by the client.
        """
        qp = request.query_params
        explicit: set[str] = set()

        def _str(key: str, default: str = "") -> str:
            if key in qp:
                explicit.add(key)
            return qp.get(key, default)

        def _bool_flag(key: str, *, default: bool) -> bool:
            if key in qp:
                explicit.add(key)
                return qp[key] != "0"
            return default

        experiment = _str("experiment")
        # Support multiple task= params for multi-task merging
        task_list = [t for t in qp.getlist("task") if t]
        if task_list:
            explicit.add("task")
        task = task_list[0] if task_list else ""
        extra_tasks = task_list[1:]
        csv_path = _str("csv_path")
        metric = _str("metric")

        lower_is_better = _bool_flag("lower_is_better", default=True)
        auto_detect = _bool_flag("auto_detect", default=False)

        num_groups = 2
        if "num_groups" in qp:
            explicit.add("num_groups")
            try:
                num_groups = max(1, min(10, int(qp["num_groups"])))
            except ValueError:
                num_groups = 2

        # Accept "cutoff_value" (canonical singular) and "cutoff_values" (plural)
        raw_cutoffs = qp.getlist("cutoff_value") or qp.getlist("cutoff_values")
        cutoff_values: list[float] = []
        for raw in raw_cutoffs:
            try:
                cutoff_values.append(float(raw))
            except (TypeError, ValueError):
                continue
        if raw_cutoffs:
            explicit.add("cutoff_value")

        analyzer = _str("analyzer")
        filter_metric = _str("filter_metric")
        filter_min = _str("filter_min")
        filter_max = _str("filter_max")
        filter_values = [v for v in qp.getlist("filter_values") if v]
        if filter_values:
            explicit.add("filter_values")

        factor = _str("factor")
        mitigation = _str("mitigation")
        mitigation_metric = _str("mitigation_metric")
        mitigation_csv = _str("mitigation_csv")
        show_mitigation_modal = qp.get("show_mitigation_modal", "0") == "1"
        source = _str("source")
        show_profile_config = qp.get("show_profile_config", "0") == "1"
        excluded_state = _str("excluded_state")
        notice = qp.get("notice") or None
        error = qp.get("error") or None

        obj = cls(
            experiment=experiment,
            task=task,
            extra_tasks=extra_tasks,
            csv_path=csv_path,
            metric=metric,
            lower_is_better=lower_is_better,
            num_groups=num_groups,
            auto_detect=auto_detect,
            cutoff_values=cutoff_values,
            filter_metric=filter_metric,
            filter_min=filter_min,
            filter_max=filter_max,
            filter_values=filter_values,
            analyzer=analyzer,
            factor=factor,
            mitigation=mitigation,
            mitigation_metric=mitigation_metric,
            mitigation_csv=mitigation_csv,
            show_mitigation_modal=show_mitigation_modal,
            source=source,
            show_profile_config=show_profile_config,
            excluded_state=excluded_state,
            notice=notice,
            error=error,
            _explicit=frozenset(explicit),
        )
        obj._validate_cutoff_count()
        return obj

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileState":
        """Build a ProfileState from the template data dict used by rendering.

        Used by _current_url() in profile.py components, where the original
        Request is not available.  _explicit is not populated because this
        path only calls to_url().
        """
        return cls(
            experiment=str(data.get("experiment") or ""),
            task=str(data.get("task") or ""),
            extra_tasks=list(data.get("extra_tasks") or []),
            csv_path=str(data.get("csv_path") or ""),
            metric=str(data.get("metric") or ""),
            lower_is_better=bool(data.get("lower_is_better", True)),
            num_groups=int(data.get("num_groups", 2)),
            auto_detect=bool(data.get("auto_detect", False)),
            cutoff_values=list(data.get("cutoff_values") or []),
            filter_metric=str(data.get("filter_metric") or ""),
            filter_min=str(data.get("filter_min") or ""),
            filter_max=str(data.get("filter_max") or ""),
            filter_values=list(data.get("filter_values") or []),
            analyzer=str(data.get("analyzer") or ""),
            factor=str(data.get("factor") or ""),
            mitigation=str(data.get("mitigation") or ""),
            mitigation_metric=str(data.get("mitigation_metric") or ""),
            mitigation_csv=str(data.get("mitigation_csv") or ""),
            show_mitigation_modal=bool(data.get("show_mitigation_modal", False)),
            source=str(data.get("source") or ""),
            show_profile_config=bool(data.get("show_profile_config", False)),
            excluded_state=str(data.get("excluded_state") or ""),
            notice=data.get("notice") or None,
            error=data.get("error") or None,
        )

    # ------------------------------------------------------------------
    # Defaults and validation
    # ------------------------------------------------------------------

    def is_explicit(self, field_name: str) -> bool:
        """Return True if field_name was present as a URL query param."""
        return field_name in self._explicit

    def apply_defaults(
        self,
        settings: "ProfileSettings | None",
        *,
        available_analyzers: dict | None = None,
    ) -> None:
        """Apply saved ProfileSettings to fields not explicitly set in the URL.

        Only touches fields where the caller's URL did not carry an explicit
        value — so user-driven navigation always wins over persisted defaults.

        Args:
            settings: Parsed ProfileSettings from the runlog markdown, or None.
            available_analyzers: Dict of {key: label} of currently available
                analyzers.  Used to guard the analyzer restoration so a saved
                value that no longer exists is not applied.
        """
        if settings is None:
            return

        # filter_metric
        if settings.default_filter_metric and "filter_metric" not in self._explicit:
            self.filter_metric = settings.default_filter_metric

        # num_groups / auto_detect
        if (
            settings.default_num_perf_groups is not None
            and "num_groups" not in self._explicit
        ):
            restored = settings.default_num_perf_groups
            if restored == 0:
                self.auto_detect = True
            else:
                self.num_groups = max(1, restored)

        # analyzer
        if settings.default_influence_analyzer and "analyzer" not in self._explicit:
            candidate = settings.default_influence_analyzer
            if available_analyzers is None or candidate in available_analyzers:
                self.analyzer = candidate

        # cutoff_values — skip when:
        #  - URL already carried explicit cutoffs
        #  - auto_detect is explicitly on (auto mode ignores manual cutoffs)
        #  - saved count clashes with an explicit num_groups value
        if (
            settings.default_cutoff_values
            and "cutoff_value" not in self._explicit
            and "auto_detect" not in self._explicit
        ):
            saved_count = len(settings.default_cutoff_values)
            num_groups_in_url = "num_groups" in self._explicit
            count_matches = (
                not num_groups_in_url
                or saved_count == 0
                or self.num_groups == saved_count + 1
            )
            if count_matches:
                self.cutoff_values = list(settings.default_cutoff_values)

    def _validate_cutoff_count(self) -> None:
        """Clear cutoff_values when their count is inconsistent with explicit num_groups."""
        if (
            self.cutoff_values
            and self.num_groups > 1
            and "num_groups" in self._explicit
            and len(self.cutoff_values) != self.num_groups - 1
        ):
            self.cutoff_values = []

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_url(self) -> str:
        """Return the canonical /ui/profile URL representing this state.

        Single authoritative URL-building implementation.  All places that
        previously reconstructed the profile URL independently now call this
        method, eliminating the reconstruction divergence that caused the
        cutoff save/restore regression.
        """
        params: list[tuple[str, str]] = []

        for key in (
            "experiment",
            "csv_path",
            "metric",
            "filter_metric",
            "filter_min",
            "filter_max",
            "analyzer",
            "factor",
            "mitigation",
            "mitigation_metric",
            "mitigation_csv",
            "source",
        ):
            val: str = getattr(self, key, "")
            if val:
                params.append((key, val))

        # Emit all selected tasks as separate task= params
        for t in self.all_tasks:
            params.append(("task", t))

        params.append(("lower_is_better", "1" if self.lower_is_better else "0"))
        params.append(("num_groups", str(self.num_groups)))
        params.append(("auto_detect", "1" if self.auto_detect else "0"))

        if self.excluded_state:
            params.append(("excluded_state", self.excluded_state))
        for v in self.filter_values:
            params.append(("filter_values", v))
        for cutoff in self.cutoff_values:
            params.append(("cutoff_value", str(cutoff)))

        return "/ui/profile?" + urlencode(params)

    def to_template_data(self) -> dict[str, Any]:
        """Return a flat dict of all state fields for the profile_page() template."""
        return {
            "experiment": self.experiment,
            "task": self.task,
            "extra_tasks": self.extra_tasks,
            "all_tasks": self.all_tasks,
            "csv_path": self.csv_path,
            "metric": self.metric,
            "lower_is_better": self.lower_is_better,
            "num_groups": self.num_groups,
            "auto_detect": self.auto_detect,
            "cutoff_values": self.cutoff_values,
            "filter_metric": self.filter_metric,
            "filter_min": self.filter_min,
            "filter_max": self.filter_max,
            "filter_values": self.filter_values,
            "analyzer": self.analyzer,
            "factor": self.factor,
            "mitigation": self.mitigation,
            "mitigation_metric": self.mitigation_metric,
            "mitigation_csv": self.mitigation_csv,
            "show_mitigation_modal": self.show_mitigation_modal,
            "source": self.source,
            "show_profile_config": self.show_profile_config,
            "excluded_state": self.excluded_state,
            "notice": self.notice,
            "error": self.error,
        }

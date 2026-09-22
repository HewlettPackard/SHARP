document.addEventListener("DOMContentLoaded", () => {
    document.body.dataset.gui2 = "ready";

    function navigateGetFormWithOverrides(form, overrides) {
        try {
            const actionUrl = new URL(form.getAttribute("action") || window.location.pathname, window.location.origin);
            const params = new URLSearchParams();
            const formData = new FormData(form);

            // Collect all form values, supporting multi-value fields
            const collected = {};
            formData.forEach((value, key) => {
                if (!(key in collected)) {
                    collected[key] = [];
                }
                collected[key].push(String(value));
            });

            // Apply overrides (replace existing values for those keys)
            Object.entries(overrides).forEach(([key, value]) => {
                if (Array.isArray(value)) {
                    collected[key] = value.map(String);
                } else {
                    collected[key] = [String(value)];
                }
            });

            // Build params
            Object.entries(collected).forEach(([key, values]) => {
                values.forEach((v) => params.append(key, v));
            });

            window.location.assign(`${actionUrl.pathname}?${params.toString()}`);
        } catch (_) {
            form.submit();
        }
    }

    function hmsToSeconds(value) {
        const text = String(value || "").trim();
        const parts = text.split(":");
        if (parts.length < 2 || parts.length > 3) return NaN;
        const hours = Number(parts[0]);
        const minutes = Number(parts[1]);
        const seconds = Number(parts.length === 3 ? parts[2] : 0);
        if (![hours, minutes, seconds].every(Number.isFinite)) return NaN;
        return hours * 3600 + minutes * 60 + seconds;
    }

    function sliderNumber(value, kind) {
        const numeric = Number(value);
        if (Number.isFinite(numeric)) return numeric;
        if (kind === "time") return hmsToSeconds(value);
        return numeric;
    }

    function createRemoteSingleSelect(selectEl, baseOptions, config) {
        const searchUrl = selectEl.dataset.searchUrl || config.searchUrl;
        const csvPath = selectEl.dataset.csvPath || "";
        return new TomSelect(selectEl, {
            ...baseOptions,
            valueField: "value",
            labelField: "text",
            plugins: ["clear_button"],
            searchField: ["text", "value"],
            preload: "focus",
            loadThrottle: 200,
            openOnFocus: true,
            hideSelected: false,
            placeholder: config.placeholder || "Type to search...",
            shouldLoad() {
                return Boolean(searchUrl) && Boolean(csvPath);
            },
            load(query, callback) {
                const url = new URL(searchUrl, window.location.origin);
                url.searchParams.set("csv_path", csvPath);
                url.searchParams.set("q", query || "");
                url.searchParams.set("limit", String(config.limit || 150));
                fetch(url.toString(), { headers: { Accept: "application/json" } })
                    .then((resp) => (resp.ok ? resp.json() : { items: [] }))
                    .then((payload) => callback(Array.isArray(payload.items) ? payload.items : []))
                    .catch(() => callback());
            },
            onChange(value) {
                if (!value) return;
                // Ensure native select is synchronized after remote selection
                selectEl.value = value;
                if (typeof config.onSelect === "function") {
                    config.onSelect(value);
                }
            },
        });
    }

    // Explore: experiment selection should refresh task choices for that
    // experiment only, and clear stale task/metric/filter selections.
    const exploreForm = document.querySelector("form.explore-form");
    if (exploreForm) {
        const exploreExperiment = exploreForm.querySelector("#experiment");
        const exploreTask = exploreForm.querySelector("#csv_path");

        if (exploreExperiment) {
            exploreExperiment.addEventListener("change", () => {
                navigateGetFormWithOverrides(exploreForm, {
                    experiment: exploreExperiment.value || "",
                    csv_path: "",
                    task: "",
                    metric: "",
                    filter_metric: "",
                    filter_value: "",
                });
            });
        }

        if (exploreTask) {
            exploreTask.addEventListener("change", () => {
                navigateGetFormWithOverrides(exploreForm, {
                    csv_path: exploreTask.value || "",
                    task: "",
                    metric: "",
                    filter_metric: "",
                    filter_value: "",
                    filter_min: "",
                    filter_max: "",
                    filter_values: [],
                    compare_metrics: [],
                });
            });
        }

        // ── Tom Select: searchable selectors ─────────────────────────────────
        const tomSelectOpts = {
            maxOptions: 150,
            closeAfterSelect: true,
            allowEmptyOption: true,
        };

        // Metric to visualize (server-side selectize-style search)
        const metricEl = exploreForm.querySelector("#metric");
        if (metricEl && typeof TomSelect !== "undefined") {
            createRemoteSingleSelect(metricEl, tomSelectOpts, {
                searchUrl: "/ui/explore/metrics",
                placeholder: "Type to search metrics...",
                onSelect() {
                    navigateGetFormWithOverrides(exploreForm, {});
                },
            });
        }

        // Metric to Filter (server-side selectize-style search)
        const filterMetricEl = exploreForm.querySelector("#filter_metric");
        if (filterMetricEl && typeof TomSelect !== "undefined") {
            createRemoteSingleSelect(filterMetricEl, tomSelectOpts, {
                searchUrl: "/ui/profile/filter-metrics",
                placeholder: "Type to search or leave empty...",
                onSelect(value) {
                    navigateGetFormWithOverrides(exploreForm, {
                        filter_metric: value,
                        filter_value: "",
                        filter_min: "",
                        filter_max: "",
                        filter_values: [],
                    });
                },
            });
        }

        // Filter values (categorical multi-select, auto-submit on change)
        const filterValuesEl = exploreForm.querySelector("#filter_values_select");
        if (filterValuesEl && typeof TomSelect !== "undefined") {
            const tsFilterVals = new TomSelect(filterValuesEl, {
                maxOptions: 200,
                plugins: ["remove_button"],
                placeholder: "Select values...",
                closeAfterSelect: false,
                onChange() {
                    navigateGetFormWithOverrides(exploreForm, {});
                },
            });
        }

        // Metrics to compare (multi-select, debounced auto-submit)
        const compareEl = exploreForm.querySelector("#compare_metrics");
        if (compareEl && typeof TomSelect !== "undefined") {
            let compareDebounce = null;
            const tsCompare = new TomSelect(compareEl, {
                maxOptions: 150,
                plugins: ["remove_button"],
                placeholder: "Type to search metrics...",
                closeAfterSelect: false,
                onChange() {
                    clearTimeout(compareDebounce);
                    compareDebounce = setTimeout(() => {
                        navigateGetFormWithOverrides(exploreForm, {});
                    }, 500);
                },
            });
        }

        // ── noUiSlider: dual-handle range slider ─────────────────────────────
        const sliderTarget = exploreForm.querySelector("#filter-noui-slider");
        if (sliderTarget && typeof noUiSlider !== "undefined") {
            const kind = sliderTarget.dataset.kind || "numeric";
            const sMin = sliderNumber(sliderTarget.dataset.min, kind);
            const sMax = sliderNumber(sliderTarget.dataset.max, kind);
            const startMin = sliderNumber(sliderTarget.dataset.startMin, kind);
            const startMax = sliderNumber(sliderTarget.dataset.startMax, kind);
            const isInteger = sliderTarget.dataset.isInteger === "1";
            const isTimestamp = sliderTarget.dataset.isTimestamp === "1";

            const minHidden = exploreForm.querySelector("#filter_min");
            const maxHidden = exploreForm.querySelector("#filter_max");
            const minDisplay = exploreForm.querySelector("#filter_min_display");
            const maxDisplay = exploreForm.querySelector("#filter_max_display");

            const pad2 = (n) => String(n).padStart(2, "0");
            const toHms = (seconds) => {
                const s = Math.max(0, Math.round(Number(seconds)));
                const h = Math.floor(s / 3600);
                const m = Math.floor((s % 3600) / 60);
                const sec = s % 60;
                return `${pad2(h)}:${pad2(m)}:${pad2(sec)}`;
            };
            const toIsoLike = (raw) => {
                const n = Number(raw);
                if (!Number.isFinite(n)) return String(raw);
                const millis = n > 1e12 ? n : n * 1000;
                const d = new Date(millis);
                if (Number.isNaN(d.getTime())) return String(raw);
                const yyyy = d.getFullYear();
                const mm = pad2(d.getMonth() + 1);
                const dd = pad2(d.getDate());
                const hh = pad2(d.getHours());
                const mi = pad2(d.getMinutes());
                const ss = pad2(d.getSeconds());
                const ms = String(d.getMilliseconds()).padStart(3, "0");
                return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}.${ms} (local)`;
            };
            const formatVal = (raw) => {
                const n = Number(raw);
                if (kind === "time") return toHms(n);
                if (isTimestamp) return toIsoLike(n);
                if (!Number.isFinite(n)) return String(raw);
                if (isInteger) return String(Math.round(n));
                return n.toFixed(3);
            };

            let step = isInteger || kind === "time" ? 1 : Math.max(1e-9, (sMax - sMin) / 500);

            noUiSlider.create(sliderTarget, {
                start: [startMin, startMax],
                connect: true,
                range: { min: sMin, max: sMax },
                step: step,
                behaviour: "drag-tap",
                format: { to: (v) => String(v), from: (v) => Number(v) },
            });

            // Sync labels and hidden inputs on slide
            sliderTarget.noUiSlider.on("update", (values) => {
                const lo = Number(values[0]);
                const hi = Number(values[1]);
                if (minDisplay) minDisplay.textContent = formatVal(lo);
                if (maxDisplay) maxDisplay.textContent = formatVal(hi);
                if (minHidden) {
                    minHidden.value = kind === "time" ? toHms(lo) : String(lo);
                }
                if (maxHidden) {
                    maxHidden.value = kind === "time" ? toHms(hi) : String(hi);
                }
            });

            // Auto-submit when user finishes dragging
            sliderTarget.noUiSlider.on("change", (values) => {
                const lo = Number(values[0]);
                const hi = Number(values[1]);
                navigateGetFormWithOverrides(exploreForm, {
                    filter_min: kind === "time" ? toHms(lo) : String(lo),
                    filter_max: kind === "time" ? toHms(hi) : String(hi),
                });
            });
        }
    }

    // ── Pairwise plot: preserve natural plot aspect so axis labels are visible ──
    const pairImg = document.querySelector(".explore-pairwise-image");
    if (pairImg) {
        pairImg.style.height = "auto";
        pairImg.style.objectFit = "contain";
    }

    // Compare: full interactivity — experiment syncing, Tom Select, filter, auto-submit
    const compareForm = document.querySelector("form.compare-form");
    if (compareForm) {
        const baselineExperiment = compareForm.querySelector("#baseline_experiment");
        const treatmentExperiment = compareForm.querySelector("#treatment_experiment");

        // Baseline experiment change: sync treatment experiment, clear tasks + metric
        if (baselineExperiment) {
            baselineExperiment.addEventListener("change", () => {
                const exp = baselineExperiment.value || "";
                navigateGetFormWithOverrides(compareForm, {
                    baseline_experiment: exp,
                    treatment_experiment: exp,
                    baseline_csv: "",
                    treatment_csv: "",
                    metric: "",
                    filter_metric: "",
                    filter_min: "",
                    filter_max: "",
                    filter_values: [],
                });
            });
        }

        // Treatment experiment change: only clears treatment task + metric
        if (treatmentExperiment) {
            treatmentExperiment.addEventListener("change", () => {
                navigateGetFormWithOverrides(compareForm, {
                    treatment_experiment: treatmentExperiment.value || "",
                    treatment_csv: "",
                    metric: "",
                    filter_metric: "",
                    filter_min: "",
                    filter_max: "",
                    filter_values: [],
                });
            });
        }

        const compareTomOpts = {
            maxOptions: 150,
            closeAfterSelect: true,
            allowEmptyOption: true,
        };

        // Baseline task (Tom Select, auto-submit clears metric + filter)
        const baselineCsvEl = compareForm.querySelector("#baseline_csv");
        if (baselineCsvEl && typeof TomSelect !== "undefined") {
            new TomSelect(baselineCsvEl, {
                ...compareTomOpts,
                placeholder: "Type to search tasks...",
                onChange() {
                    navigateGetFormWithOverrides(compareForm, {
                        baseline_csv: baselineCsvEl.value || "",
                        metric: "",
                        filter_metric: "",
                        filter_min: "",
                        filter_max: "",
                        filter_values: [],
                    });
                },
            });
        }

        // Treatment task (Tom Select, auto-submit clears metric + filter)
        const treatmentCsvEl = compareForm.querySelector("#treatment_csv");
        if (treatmentCsvEl && typeof TomSelect !== "undefined") {
            new TomSelect(treatmentCsvEl, {
                ...compareTomOpts,
                placeholder: "Type to search tasks...",
                onChange() {
                    navigateGetFormWithOverrides(compareForm, {
                        treatment_csv: treatmentCsvEl.value || "",
                        metric: "",
                        filter_metric: "",
                        filter_min: "",
                        filter_max: "",
                        filter_values: [],
                    });
                },
            });
        }

        // Metric selector (server-side selectize-style search)
        const compareMetricEl = compareForm.querySelector("#metric");
        if (compareMetricEl && typeof TomSelect !== "undefined") {
            createRemoteSingleSelect(compareMetricEl, compareTomOpts, {
                searchUrl: "/ui/explore/metrics",
                placeholder: "Type to search metrics...",
                onSelect() {
                    navigateGetFormWithOverrides(compareForm, {});
                },
            });
        }

        // Filter metric (server-side selectize-style search)
        const compareFilterMetricEl = compareForm.querySelector("#filter_metric");
        if (compareFilterMetricEl && typeof TomSelect !== "undefined") {
            createRemoteSingleSelect(compareFilterMetricEl, compareTomOpts, {
                searchUrl: "/ui/profile/filter-metrics",
                placeholder: "Type to search or leave empty...",
                onSelect(value) {
                    navigateGetFormWithOverrides(compareForm, {
                        filter_metric: value,
                        filter_min: "",
                        filter_max: "",
                        filter_values: [],
                    });
                },
            });
        }

        // Filter values (categorical multi-select)
        const compareFilterValuesEl = compareForm.querySelector("#filter_values_select");
        if (compareFilterValuesEl && typeof TomSelect !== "undefined") {
            new TomSelect(compareFilterValuesEl, {
                maxOptions: 200,
                plugins: ["remove_button"],
                placeholder: "Select values...",
                closeAfterSelect: false,
                onChange() {
                    navigateGetFormWithOverrides(compareForm, {});
                },
            });
        }

        // noUiSlider for numeric/time filter
        const compareSlider = compareForm.querySelector("#filter-noui-slider");
        if (compareSlider && typeof noUiSlider !== "undefined") {
            const kind = compareSlider.dataset.kind || "numeric";
            const sMin = sliderNumber(compareSlider.dataset.min, kind);
            const sMax = sliderNumber(compareSlider.dataset.max, kind);
            const startMin = sliderNumber(compareSlider.dataset.startMin, kind);
            const startMax = sliderNumber(compareSlider.dataset.startMax, kind);
            const isInteger = compareSlider.dataset.isInteger === "1";
            const isTimestamp = compareSlider.dataset.isTimestamp === "1";

            const minHidden = compareForm.querySelector("#filter_min");
            const maxHidden = compareForm.querySelector("#filter_max");
            const minDisplay = compareForm.querySelector("#filter_min_display");
            const maxDisplay = compareForm.querySelector("#filter_max_display");

            const pad2 = (n) => String(n).padStart(2, "0");
            const toHms = (seconds) => {
                const s = Math.max(0, Math.round(Number(seconds)));
                const h = Math.floor(s / 3600);
                const m = Math.floor((s % 3600) / 60);
                const sec = s % 60;
                return `${pad2(h)}:${pad2(m)}:${pad2(sec)}`;
            };
            const toIsoLike = (raw) => {
                const n = Number(raw);
                if (!Number.isFinite(n)) return String(raw);
                const millis = n > 1e12 ? n : n * 1000;
                const d = new Date(millis);
                if (Number.isNaN(d.getTime())) return String(raw);
                const yyyy = d.getFullYear();
                const mm = pad2(d.getMonth() + 1);
                const dd = pad2(d.getDate());
                const hh = pad2(d.getHours());
                const mi = pad2(d.getMinutes());
                const ss = pad2(d.getSeconds());
                const ms = String(d.getMilliseconds()).padStart(3, "0");
                return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}.${ms} (local)`;
            };
            const formatVal = (raw) => {
                const n = Number(raw);
                if (kind === "time") return toHms(n);
                if (isTimestamp) return toIsoLike(n);
                if (!Number.isFinite(n)) return String(raw);
                if (isInteger) return String(Math.round(n));
                return n.toFixed(3);
            };

            const step = isInteger || kind === "time" ? 1 : Math.max(1e-9, (sMax - sMin) / 500);
            noUiSlider.create(compareSlider, {
                start: [startMin, startMax],
                connect: true,
                range: { min: sMin, max: sMax },
                step: step,
                behaviour: "drag-tap",
                format: { to: (v) => String(v), from: (v) => Number(v) },
            });

            compareSlider.noUiSlider.on("update", (values) => {
                const lo = Number(values[0]);
                const hi = Number(values[1]);
                if (minDisplay) minDisplay.textContent = formatVal(lo);
                if (maxDisplay) maxDisplay.textContent = formatVal(hi);
                if (minHidden) minHidden.value = kind === "time" ? toHms(lo) : String(lo);
                if (maxHidden) maxHidden.value = kind === "time" ? toHms(hi) : String(hi);
            });

            compareSlider.noUiSlider.on("change", (values) => {
                const lo = Number(values[0]);
                const hi = Number(values[1]);
                navigateGetFormWithOverrides(compareForm, {
                    filter_min: kind === "time" ? toHms(lo) : String(lo),
                    filter_max: kind === "time" ? toHms(hi) : String(hi),
                });
            });
        }

        // Direction auto-submits
        const directionEl = compareForm.querySelector("#lower_is_better");
        if (directionEl) {
            directionEl.addEventListener("change", () => {
                navigateGetFormWithOverrides(compareForm, {});
            });
        }
    }



    function openModal(id) {
        const el = document.getElementById(id);
        if (el) {
            el.classList.remove("is-hidden");
        }
    }

    function closeModal(id) {
        const el = document.getElementById(id);
        if (el) {
            el.classList.add("is-hidden");
        }
    }

    // ── Summary page modals ──────────────────────────────────────────────────

    const uploadTrigger = document.getElementById("upload_experiment_btn");
    const uploadCancel = document.getElementById("upload_cancel");
    const newExperimentBtn = document.getElementById("new_experiment_btn");
    const newExperimentCancel = document.getElementById("new_experiment_cancel");

    if (uploadTrigger) {
        uploadTrigger.addEventListener("click", (e) => {
            e.preventDefault();
            openModal("upload-experiment-modal");
        });
    }
    if (uploadCancel) {
        uploadCancel.addEventListener("click", (e) => {
            e.preventDefault();
            closeModal("upload-experiment-modal");
        });
    }
    if (newExperimentBtn) {
        newExperimentBtn.addEventListener("click", (e) => {
            e.preventDefault();
            closeModal("upload-experiment-modal");
            openModal("new-experiment-modal");
        });
    }
    if (newExperimentCancel) {
        newExperimentCancel.addEventListener("click", (e) => {
            e.preventDefault();
            closeModal("new-experiment-modal");
            openModal("upload-experiment-modal");
        });
    }

    // ── Measure error modal (auto-open when error markup is present) ─────────

    if (document.getElementById("measure-error-modal")) {
        openModal("measure-error-modal");
    }
    const measureErrorClose = document.getElementById("measure_error_close");
    if (measureErrorClose) {
        measureErrorClose.addEventListener("click", (e) => {
            e.preventDefault();
            closeModal("measure-error-modal");
        });
    }

    // ── Settings gear button ──────────────────────────────────────────────────
    // The gear link has hx-get / hx-target attributes so HTMX fetches the
    // settings <dialog> fragment and swaps it into #settings-modal-root.
    // After the swap we open the dialog via showModal() and wire up the
    // theme picker cards for live visual selection.
    document.addEventListener("htmx:afterSwap", (e) => {
        if (e.detail.target && e.detail.target.id === "settings-modal-root") {
            const dlg = document.getElementById("settings-modal");
            if (dlg && typeof dlg.showModal === "function") {
                dlg.showModal();
            }
            // Theme card interactivity: clicking a card selects its radio
            dlg && dlg.querySelectorAll(".settings-theme-card").forEach((card) => {
                card.addEventListener("click", () => {
                    dlg.querySelectorAll(".settings-theme-card").forEach(
                        (c) => c.classList.remove("is-selected")
                    );
                    card.classList.add("is-selected");
                    const radio = card.querySelector(".settings-theme-radio");
                    if (radio) radio.checked = true;
                });
            });
        }
    });

    // Dismiss any modal on backdrop click or Escape key
    document.querySelectorAll(".modal-shell").forEach((modal) => {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                modal.classList.add("is-hidden");
            }
        });
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            document.querySelectorAll(".modal-shell").forEach((m) => m.classList.add("is-hidden"));
        }
    });

    // ── Auto-dismiss notice banners after a few seconds ──────────────────────
    document.querySelectorAll(".notice-banner").forEach((banner) => {
        setTimeout(() => {
            banner.style.transition = "opacity 0.3s ease-out";
            banner.style.opacity = "0";
            setTimeout(() => {
                banner.style.display = "none";
            }, 300);
        }, 3500);
    });

    // ── Measure form: field persistence across tab navigation ───────────────
    //
    // We save form state to sessionStorage on every change. On page load we
    // restore it UNLESS the server already provided prefill values via URL
    // params (e.g., after a completed run the URL carries bench/task/notice).

    const MEASURE_KEY = "gui2.measure.form";

    function saveMeasureState(form) {
        const obj = {};
        new FormData(form).forEach((val, key) => {
            if (key in obj) {
                // Accumulate multi-select values into an array
                obj[key] = [].concat(obj[key], String(val));
            } else {
                obj[key] = String(val);
            }
        });
        try {
            sessionStorage.setItem(MEASURE_KEY, JSON.stringify(obj));
        } catch (_) {}
    }

    function restoreMeasureState(form) {
        // Skip if the server already sent prefill values via URL params so that
        // a completed-run redirect is not overwritten by stale sessionStorage.
        const sp = new URLSearchParams(window.location.search);
        if (sp.has("bench") || sp.has("notice") || sp.has("csv_path") || sp.has("rerun_experiment")) {
            return;
        }

        let saved;
        try {
            saved = JSON.parse(sessionStorage.getItem(MEASURE_KEY));
        } catch (_) {
            return;
        }
        if (!saved || typeof saved !== "object") {
            return;
        }

        Object.entries(saved).forEach(([name, value]) => {
            // Use attribute selector directly; field names are simple ASCII
            form.querySelectorAll(`[name="${name}"]`).forEach((field) => {
                if (field.tagName === "SELECT" && field.multiple) {
                    const vals = new Set([].concat(value).map(String));
                    Array.from(field.options).forEach((opt) => {
                        opt.selected = vals.has(opt.value);
                    });
                } else if (field.type !== "submit" && field.type !== "button") {
                    field.value = String(value);
                }
            });
        });
    }

    // ── Measure form: progress display helpers ───────────────────────────────

    function setIndeterminate(strip, copy, track, message) {
        strip.classList.add("is-running");
        copy.textContent = message;
        track.dataset.mode = "indeterminate";
    }

    function updateProgress(strip, copy, track, fill, current, total) {
        // Text: "3 / 10" for COUNT, "3 iterations" for adaptive
        if (total !== null && total > 0) {
            copy.textContent = `${current} / ${total} iterations...`;
        } else {
            copy.textContent = `${current} iteration${current !== 1 ? "s" : ""}...`;
        }

        // Bar: keep animated indeterminate until the first iteration completes;
        // then switch to a determinate fill (minimum 5 % so it's always visible).
        if (current === 0 || total === null) {
            track.dataset.mode = "indeterminate";
        } else {
            const pct = Math.max(5, Math.min(100, (current / total) * 100));
            track.dataset.mode = "determinate";
            fill.style.width = `${pct.toFixed(1)}%`;
        }
    }

    // ── Measure form: run submission ─────────────────────────────────────────

    const measureForm = document.getElementById("measure-run-form");
    if (measureForm) {
        // Restore previous field values when navigating back to this page
        restoreMeasureState(measureForm);

        // Keep sessionStorage in sync whenever any field changes
        measureForm.addEventListener("change", () => saveMeasureState(measureForm));
        measureForm.addEventListener("input", () => saveMeasureState(measureForm));

        const strip = document.getElementById("measure-status-strip");
        const copy = document.getElementById("measure-status-copy");
        const track = document.getElementById("measure-status-progress");
        const fill = document.getElementById("measure-status-progress-fill");
        const runBtn = document.getElementById("run_button");

        measureForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            // Disable the Run button and show immediate feedback
            if (runBtn) {
                runBtn.disabled = true;
                runBtn.classList.add("is-running");
            }
            if (strip && copy && track) {
                setIndeterminate(strip, copy, track, "Starting benchmark run...");
            }

            // Persist current form state before navigation
            saveMeasureState(measureForm);

            // Ask the server to start the benchmark in a background thread
            let runId;
            try {
                const res = await fetch("/ui/measure/start", {
                    method: "POST",
                    body: new FormData(measureForm),
                });
                if (!res.ok) {
                    throw new Error(`HTTP ${res.status}`);
                }
                const json = await res.json();
                runId = String(json.run_id || "").trim();
                if (!runId) {
                    throw new Error("empty run_id");
                }
            } catch (_err) {
                // Async path failed – fall back to a plain synchronous POST.
                // The form already has action="/ui/measure/run" in the HTML so
                // calling submit() here is safe and will complete the run.
                if (copy) {
                    copy.textContent = "Running… (no live progress in fallback mode)";
                }
                measureForm.submit();
                return;
            }

            // Open an SSE connection to receive iteration-count events
            const sse = new EventSource(`/ui/measure/stream?run_id=${encodeURIComponent(runId)}`);

            sse.onmessage = (ev) => {
                let data;
                try {
                    data = JSON.parse(ev.data);
                } catch (_) {
                    return;
                }

                const current = Number(data.current ?? 0);
                const total = data.total != null ? Number(data.total) : null;

                if (strip && copy && track && fill) {
                    strip.classList.add("is-running");
                    updateProgress(strip, copy, track, fill, current, total);
                }

                if (data.redirect_url) {
                    sse.close();
                    window.location.assign(String(data.redirect_url));
                } else if (data.error_url) {
                    sse.close();
                    window.location.assign(String(data.error_url));
                }
            };

            sse.onerror = () => {
                sse.close();
                if (copy) {
                    copy.textContent = "Connection lost. The run may still be completing.";
                }
                if (runBtn) {
                    runBtn.disabled = false;
                    runBtn.classList.remove("is-running");
                }
            };
        });
    }

    // ── Measure results table: filter and sort ───────────────────────────────

    const resultsFilter = document.getElementById("measure-results-filter");
    const resultsTable = document.getElementById("measure-results-table");

    if (resultsFilter && resultsTable) {
        const bodyRows = () => Array.from(resultsTable.querySelectorAll("tbody tr"));

        resultsFilter.addEventListener("input", () => {
            const needle = resultsFilter.value.trim().toLowerCase();
            bodyRows().forEach((row) => {
                row.style.display = needle && !row.textContent.toLowerCase().includes(needle) ? "none" : "";
            });
        });

        Array.from(resultsTable.querySelectorAll("thead th[data-sortable]")).forEach((header, index) => {
            let ascending = true;
            header.classList.add("is-sortable");
            header.addEventListener("click", () => {
                const rows = bodyRows();
                rows.sort((a, b) => {
                    const av = (a.children[index]?.textContent || "").trim();
                    const bv = (b.children[index]?.textContent || "").trim();
                    const an = Number(av);
                    const bn = Number(bv);
                    if (!Number.isNaN(an) && !Number.isNaN(bn)) {
                        return ascending ? an - bn : bn - an;
                    }
                    return ascending ? av.localeCompare(bv) : bv.localeCompare(av);
                });
                const tbody = resultsTable.querySelector("tbody");
                if (tbody) {
                    rows.forEach((row) => tbody.appendChild(row));
                }
                ascending = !ascending;
            });
        });
    }

    // ── Profile tab ──────────────────────────────────────────────────────────

    const profileForm = document.querySelector("form.profile-form");
    if (profileForm) {
        const profileTomOpts = {
            maxOptions: 150,
            closeAfterSelect: true,
            allowEmptyOption: true,
        };

        // Experiment selector (plain select, clears task + downstream)
        const profileExperiment = profileForm.querySelector("#experiment");
        if (profileExperiment) {
            profileExperiment.addEventListener("change", () => {
                navigateGetFormWithOverrides(profileForm, {
                    experiment: profileExperiment.value || "",
                    task: "",
                    csv_path: "",
                    source: "",
                    excluded_state: "",
                    metric: "",
                    filter_metric: "",
                    filter_min: "",
                    filter_max: "",
                    filter_values: [],
                    factor: "",
                    mitigation: "",
                    mitigation_metric: "",
                    mitigation_csv: "",
                });
            });
        }

        // Task selector (TomSelect multi-select; resets downstream state on change)
        const profileTaskEl = profileForm.querySelector("#task");
        if (profileTaskEl && typeof TomSelect !== "undefined") {
            new TomSelect(profileTaskEl, {
                maxOptions: 150,
                plugins: ["remove_button"],
                placeholder: "Type to search tasks...",
                closeAfterSelect: false,
                onChange() {
                    // Don't override "task" — FormData collects all selected values
                    // from the multi-select; only reset dependent downstream state.
                    navigateGetFormWithOverrides(profileForm, {
                        csv_path: "",
                        source: "",
                        excluded_state: "",
                        metric: "",
                        filter_metric: "",
                        filter_min: "",
                        filter_max: "",
                        filter_values: [],
                        factor: "",
                        mitigation: "",
                        mitigation_metric: "",
                        mitigation_csv: "",
                    });
                },
            });
        }

        // Metric selector (server-side selectize-style search)
        const profileMetricEl = profileForm.querySelector("#metric");
        if (profileMetricEl && typeof TomSelect !== "undefined") {
            createRemoteSingleSelect(profileMetricEl, profileTomOpts, {
                searchUrl: "/ui/profile/metrics",
                placeholder: "Type to search metrics...",
                onSelect() {
                    navigateGetFormWithOverrides(profileForm, {
                        factor: "",
                        mitigation: "",
                        mitigation_metric: "",
                        mitigation_csv: "",
                    });
                },
            });
        }

        // Lower is better checkbox auto-submit
        const profileLowerIsBetter = profileForm.querySelector("#lower_is_better");
        if (profileLowerIsBetter) {
            profileLowerIsBetter.addEventListener("change", () => {
                navigateGetFormWithOverrides(profileForm, {
                    lower_is_better: profileLowerIsBetter.checked ? "1" : "0",
                });
            });
        }

        // Filter metric (server-side selectize-style search)
        const profileFilterMetricEl = profileForm.querySelector("#filter_metric");
        if (profileFilterMetricEl && typeof TomSelect !== "undefined") {
            createRemoteSingleSelect(profileFilterMetricEl, profileTomOpts, {
                searchUrl: "/ui/profile/filter-metrics",
                placeholder: "Type to search or leave empty...",
                onSelect(value) {
                    navigateGetFormWithOverrides(profileForm, {
                        filter_metric: value,
                        filter_min: "",
                        filter_max: "",
                        filter_values: [],
                    });
                },
            });
        }

        // Filter values (categorical multi-select)
        const profileFilterValuesEl = profileForm.querySelector("#filter_values");
        if (profileFilterValuesEl && profileFilterValuesEl.multiple && typeof TomSelect !== "undefined") {
            new TomSelect(profileFilterValuesEl, {
                maxOptions: 200,
                plugins: ["remove_button"],
                placeholder: "Select values...",
                closeAfterSelect: false,
                onChange() {
                    navigateGetFormWithOverrides(profileForm, {});
                },
            });
        }

        // noUiSlider for numeric/time filter
        const profileSlider = document.getElementById("profile-noui-slider");
        if (profileSlider && typeof noUiSlider !== "undefined") {
            const kind = profileSlider.dataset.kind || "numeric";
            const sMin = sliderNumber(profileSlider.dataset.min, kind);
            const sMax = sliderNumber(profileSlider.dataset.max, kind);
            const startMin = sliderNumber(profileSlider.dataset.startMin, kind);
            const startMax = sliderNumber(profileSlider.dataset.startMax, kind);
            const isInteger = profileSlider.dataset.isInteger === "true";
            const isTimestamp = profileSlider.dataset.isTimestamp === "true";

            const minHidden = document.getElementById("filter_min");
            const maxHidden = document.getElementById("filter_max");
            const minDisplay = document.getElementById("profile-noui-label-min");
            const maxDisplay = document.getElementById("profile-noui-label-max");

            const pad2 = (n) => String(n).padStart(2, "0");
            const toHms = (seconds) => {
                const s = Math.max(0, Math.round(Number(seconds)));
                const h = Math.floor(s / 3600);
                const m = Math.floor((s % 3600) / 60);
                const sec = s % 60;
                return `${pad2(h)}:${pad2(m)}:${pad2(sec)}`;
            };
            const formatVal = (raw) => {
                const n = Number(raw);
                if (kind === "time") return toHms(n);
                if (isTimestamp) {
                    const millis = n > 1e12 ? n : n * 1000;
                    const d = new Date(millis);
                    if (!Number.isNaN(d.getTime())) {
                        return d.toLocaleString();
                    }
                }
                if (!Number.isFinite(n)) return String(raw);
                if (isInteger) return String(Math.round(n));
                return n.toFixed(3);
            };

            const step = isInteger || kind === "time" ? 1 : Math.max(1e-9, (sMax - sMin) / 500);
            noUiSlider.create(profileSlider, {
                start: [startMin, startMax],
                connect: true,
                range: { min: sMin, max: sMax },
                step: step,
                behaviour: "drag-tap",
                format: { to: (v) => String(v), from: (v) => Number(v) },
            });

            profileSlider.noUiSlider.on("update", (values) => {
                const lo = Number(values[0]);
                const hi = Number(values[1]);
                if (minDisplay) minDisplay.textContent = formatVal(lo);
                if (maxDisplay) maxDisplay.textContent = formatVal(hi);
                if (minHidden) minHidden.value = kind === "time" ? toHms(lo) : String(lo);
                if (maxHidden) maxHidden.value = kind === "time" ? toHms(hi) : String(hi);
            });

            profileSlider.noUiSlider.on("change", (values) => {
                const lo = Number(values[0]);
                const hi = Number(values[1]);
                navigateGetFormWithOverrides(profileForm, {
                    filter_min: kind === "time" ? toHms(lo) : String(lo),
                    filter_max: kind === "time" ? toHms(hi) : String(hi),
                });
            });
        }

        // Analyzer selector (Tom Select, auto-submit with tooltips)
        // Read titles from DOM <option> elements BEFORE TomSelect processes them,
        // since TomSelect does not propagate the title attribute automatically.
        const profileAnalyzerEl = document.querySelector("#analyzer");
        if (profileAnalyzerEl && typeof TomSelect !== "undefined") {
            const analyzerOptions = Array.from(profileAnalyzerEl.options).map((opt) => ({
                value: opt.value,
                text: opt.textContent.trim(),
                title: opt.title || "",
            }));
            const analyzerSelected = profileAnalyzerEl.value;
            new TomSelect(profileAnalyzerEl, {
                ...profileTomOpts,
                options: analyzerOptions,
                items: [analyzerSelected],
                render: {
                    option(data, escape) {
                        const tip = data.title ? ` title="${escape(data.title)}"` : "";
                        return `<div${tip}>${escape(data.text)}</div>`;
                    },
                    item(data, escape) {
                        const tip = data.title ? ` title="${escape(data.title)}"` : "";
                        return `<div${tip}>${escape(data.text)}</div>`;
                    },
                },
                onChange() {
                    navigateGetFormWithOverrides(profileForm, { factor: "" });
                },
            });
        }

        // Auto-detect checkbox auto-submit + disable/enable group count input
        const profileAutoDetect = document.getElementById("auto_detect");
        const profileNumGroups = document.getElementById("num_groups");
        const syncProfileGroupControls = () => {
            if (profileAutoDetect && profileNumGroups) {
                profileNumGroups.disabled = profileAutoDetect.checked;
            }
        };
        syncProfileGroupControls();
        if (profileAutoDetect) {
            profileAutoDetect.addEventListener("change", () => {
                syncProfileGroupControls();
                navigateGetFormWithOverrides(profileForm, {
                    auto_detect: profileAutoDetect.checked ? "1" : "0",
                    num_groups: profileNumGroups ? (profileNumGroups.value || "2") : "2",
                    cutoff_value: [],
                });
            });
        }

        // Num groups number input auto-submit on change
        if (profileNumGroups) {
            profileNumGroups.addEventListener("change", () => {
                navigateGetFormWithOverrides(profileForm, { cutoff_value: [] });
            });
        }

        // Factor selector (Tom Select, auto-submit)
        const profileFactorEl = document.querySelector("#factor");
        if (profileFactorEl && typeof TomSelect !== "undefined") {
            new TomSelect(profileFactorEl, {
                ...profileTomOpts,
                placeholder: "Select a factor...",
                onChange() {
                    navigateGetFormWithOverrides(profileForm, {
                        mitigation_metric: "",
                    });
                },
            });
        }

        // Mitigation selector (Tom Select, auto-submit)
        const profileMitigationEl = document.querySelector("#mitigation");
        if (profileMitigationEl && typeof TomSelect !== "undefined") {
            new TomSelect(profileMitigationEl, {
                ...profileTomOpts,
                placeholder: "Select mitigation...",
                onChange() {
                    navigateGetFormWithOverrides(profileForm, {
                        mitigation_metric: "",
                        mitigation_csv: "",
                    });
                },
            });
        }

        // Mitigation comparison metric selector
        const profileMitigationMetricEl = document.querySelector("#mitigation_metric");
        if (profileMitigationMetricEl && typeof TomSelect !== "undefined") {
            new TomSelect(profileMitigationMetricEl, {
                ...profileTomOpts,
                placeholder: "Metric to compare...",
                onChange() {
                    navigateGetFormWithOverrides(profileForm, {});
                },
            });
        }

        const profilingBackendsEl = document.querySelector("#profiling_backends");
        if (profilingBackendsEl && profilingBackendsEl.multiple && typeof TomSelect !== "undefined") {
            new TomSelect(profilingBackendsEl, {
                maxOptions: 100,
                plugins: ["remove_button"],
                placeholder: "Select profiling backends...",
                closeAfterSelect: false,
            });
        }

        const profileConfigForm = document.getElementById("profile-config-form");
        if (profileConfigForm) {
            profileConfigForm.addEventListener("submit", async (event) => {
                event.preventDefault();

                const startBtn = document.getElementById("profile_start_button");
                const statusStrip = document.getElementById("profile-config-status-strip");
                const statusCopy = document.getElementById("profile-config-status-copy");
                const track = document.getElementById("profile-config-status-progress");
                const fill = document.getElementById("profile-config-status-progress-fill");

                if (startBtn) {
                    startBtn.disabled = true;
                    startBtn.classList.add("is-running");
                    startBtn.textContent = "Starting...";
                }

                if (statusStrip) {
                    statusStrip.hidden = false;
                    statusStrip.classList.add("is-running");
                }
                if (track) {
                    track.dataset.mode = "indeterminate";
                }
                if (statusCopy) {
                    statusCopy.textContent = "Starting profiling...";
                }

                try {
                    const startRes = await fetch("/ui/profile/start-profiling", {
                        method: "POST",
                        body: new FormData(profileConfigForm),
                    });

                    if (!startRes.ok) {
                        throw new Error(`Failed to start profiling (HTTP ${startRes.status})`);
                    }

                    const startPayload = await startRes.json();
                    const runId = startPayload && startPayload.run_id;
                    if (!runId) {
                        throw new Error("Missing run id for profiling stream");
                    }

                    const sse = new EventSource(`/ui/profile/stream?run_id=${encodeURIComponent(runId)}`);
                    sse.onmessage = (evt) => {
                        let payload = {};
                        try {
                            payload = JSON.parse(evt.data || "{}");
                        } catch (_) {
                            return;
                        }

                        const status = String(payload.status || "");
                        const current = Number(payload.current || 0);
                        const totalRaw = payload.total;
                        const total = Number.isFinite(Number(totalRaw)) ? Number(totalRaw) : null;

                        if (statusStrip) {
                            statusStrip.hidden = false;
                            statusStrip.classList.add("is-running");
                        }

                        if (status === "running") {
                            if (statusStrip && statusCopy && track && fill) {
                                updateProgress(statusStrip, statusCopy, track, fill, current, total);
                            }
                        }

                        if (statusCopy && payload.message) {
                            statusCopy.textContent = String(payload.message);
                        }

                        if (status === "completed") {
                            sse.close();
                            const redirect = payload.redirect_url;
                            if (redirect) {
                                window.location.assign(String(redirect));
                            } else {
                                window.location.reload();
                            }
                            return;
                        }

                        if (status === "failed") {
                            sse.close();
                            const errorUrl = payload.error_url;
                            if (errorUrl) {
                                window.location.assign(String(errorUrl));
                            } else {
                                if (statusCopy) {
                                    statusCopy.textContent = "Profiling failed.";
                                }
                                if (startBtn) {
                                    startBtn.disabled = false;
                                    startBtn.classList.remove("is-running");
                                    startBtn.textContent = "Start Profiling";
                                }
                            }
                        }
                    };

                    sse.onerror = () => {
                        sse.close();
                        if (statusCopy) {
                            statusCopy.textContent = "Lost progress connection. Please retry.";
                        }
                        if (startBtn) {
                            startBtn.disabled = false;
                            startBtn.classList.remove("is-running");
                            startBtn.textContent = "Start Profiling";
                        }
                    };
                } catch (err) {
                    if (statusCopy) {
                        statusCopy.textContent = `Unable to start profiling: ${err instanceof Error ? err.message : "unknown error"}`;
                    }
                    if (startBtn) {
                        startBtn.disabled = false;
                        startBtn.classList.remove("is-running");
                        startBtn.textContent = "Start Profiling";
                    }
                }
            });
        }
    }

    // ── Profile factor tab switching (event delegation for HTMX content) ─────
    document.addEventListener("click", (e) => {
        const tab = e.target.closest(".profile-tab");
        if (!tab) return;
        const panelId = tab.dataset.tab;
        if (!panelId) return;

        // Deactivate sibling tabs
        const nav = tab.parentElement;
        nav.querySelectorAll(".profile-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");

        // Show target panel, hide siblings
        const panels = nav.parentElement.querySelector(".profile-tab-panels");
        if (panels) {
            panels.querySelectorAll(".profile-tab-panel").forEach((p) => p.classList.remove("active"));
            const target = panels.querySelector(`#${panelId}`);
            if (target) target.classList.add("active");
        }
    });

    // ── Profile search button handler (event delegation) ───────────────────
    document.addEventListener("click", (e) => {
        if (!e.target.closest("#search_cutoff_btn")) return;
        e.preventDefault();
        const modal = document.getElementById("search-cutoff-modal");
        if (modal) modal.showModal();
    });

    // ── Profile exclude predictors button handler (event delegation) ────────
    function reloadPredictorsModalToCommittedState() {
        const list = document.getElementById("exclude-predictors-list");
        if (!list) return;

        const initialUrl = list.dataset.initialUrl || list.getAttribute("hx-get") || "";
        if (!initialUrl) return;

        list.innerHTML = '<p class="muted">Loading predictors...</p>';
        if (window.htmx && typeof window.htmx.ajax === "function") {
            window.htmx.ajax("GET", initialUrl, {
                target: "#exclude-predictors-list",
                swap: "innerHTML",
            });
        }
    }

    document.addEventListener("click", (e) => {
        if (!e.target.closest("#exclude_predictors_btn")) return;
        e.preventDefault();
        const modal = document.getElementById("exclude-predictors-modal");
        if (modal) {
            reloadPredictorsModalToCommittedState();
            modal.showModal();
        }
    });

    // ── Modal close handlers ────────────────────────────────────────────────
    document.addEventListener("click", (e) => {
        const closeBtn = e.target.closest("[data-close-modal]");
        if (!closeBtn) return;
        const modalId = closeBtn.dataset.closeModal;
        const modal = document.getElementById(modalId);
        if (modal) modal.close();
    });

    // ── Distribution plot: hover nearest-point tooltip + click-to-move-cutoff

    /**
     * Format a number for the tooltip (up to 6 significant figures).
     */
    function fmtDataCoord(v) {
        const n = Number(v);
        if (!Number.isFinite(n)) return String(v);
        return parseFloat(n.toPrecision(6)).toString();
    }

    /**
     * Convert a mouse event position (relative to an <img>) to data coordinates.
     * Uses the xmin/xmax stored on the parent .profile-dist-wrapper element.
     */
    function imgPixelToData(img, clientX) {
        const wrapper = img.closest(".profile-dist-wrapper");
        if (!wrapper) return null;
        const rect = img.getBoundingClientRect();
        const xmin = parseFloat(wrapper.dataset.xmin);
        const xmax = parseFloat(wrapper.dataset.xmax);
        const plotLeft = parseFloat(wrapper.dataset.plotLeft || "0");
        const plotRight = parseFloat(wrapper.dataset.plotRight || "1");
        if (!Number.isFinite(xmin) || !Number.isFinite(xmax) || xmax <= xmin) return null;
        const clampedLeft = Number.isFinite(plotLeft) ? Math.max(0, Math.min(1, plotLeft)) : 0;
        const clampedRight = Number.isFinite(plotRight) ? Math.max(clampedLeft + 1e-6, Math.min(1, plotRight)) : 1;
        const borderLeft = parseFloat(getComputedStyle(img).borderLeftWidth || "0") || 0;
        const borderRight = parseFloat(getComputedStyle(img).borderRightWidth || "0") || 0;
        const innerLeft = rect.left + borderLeft;
        const innerRight = rect.right - borderRight;
        const usableLeft = innerLeft + (innerRight - innerLeft) * clampedLeft;
        const usableRight = innerLeft + (innerRight - innerLeft) * clampedRight;
        const usableWidth = usableRight - usableLeft;
        if (usableWidth <= 0) return null;
        const xRatio = (clientX - usableLeft) / usableWidth;
        if (xRatio < 0 || xRatio > 1) return null;
        return xmin + xRatio * (xmax - xmin);
    }

    function closestFromEventTarget(target, selector) {
        if (target instanceof Element) return target.closest(selector);
        if (target instanceof Node && target.parentElement) {
            return target.parentElement.closest(selector);
        }
        return null;
    }

    // Hover: show nearest-point pill tooltip
    document.addEventListener("mousemove", (e) => {
        const img = closestFromEventTarget(e.target, ".profile-dist-img");
        if (!img) {
            // Mouse left the plot — hide any visible tooltip
            const tt = document.getElementById("dist-tooltip");
            if (tt) tt.style.display = "none";
            return;
        }

        const wrapper = img.closest(".profile-dist-wrapper");
        if (!wrapper) return;

        const dataX = imgPixelToData(img, e.clientX);
        if (dataX === null) return;

        const tt = document.getElementById("dist-tooltip");
        if (!tt) return;
        tt.textContent = fmtDataCoord(dataX);
        tt.style.display = "inline-block";
    });

    // Hide tooltip when mouse leaves a distribution wrapper entirely
    document.addEventListener("mouseleave", (e) => {
        const wrapper = closestFromEventTarget(e.target, ".profile-dist-wrapper");
        if (!wrapper) return;
        const tt = document.getElementById("dist-tooltip");
        if (tt) tt.style.display = "none";
    }, true);

    // Click: move nearest cutoff to click position (only when mutable).
    // Uses fetch() + partial DOM update to avoid a full page reload:
    //   1. POST to /ui/profile/move-cutoff → server redirects to full-page URL
    //      with updated cutoff_value params
    //   2. Extract the new cutoff_value list from response.url
    //   3. Update the distribution <img> src and tree <iframe> src in-place
    //   4. Re-load the analysis-results fragment via htmx.ajax
    //   5. Push the new URL to browser history (no navigation)
    document.addEventListener("click", (e) => {
        const img = closestFromEventTarget(e.target, ".profile-dist-img");
        if (!img) return;

        const wrapper = img.closest(".profile-dist-wrapper");
        if (!wrapper) return;
        if (wrapper.dataset.mutable !== "1") return;

        const dataX = imgPixelToData(img, e.clientX);
        if (dataX === null) return;

        e.preventDefault();

        const csvPath = wrapper.dataset.csvPath || "";
        const metric = wrapper.dataset.metric || "";
        const lowerIsBetter = wrapper.dataset.lowerIsBetter || "1";
        const numGroups = wrapper.dataset.numGroups || "2";
        const autoDetect = wrapper.dataset.autoDetect || "0";
        const filterMetric = wrapper.dataset.filterMetric || "";
        const filterMin = wrapper.dataset.filterMin || "";
        const filterMax = wrapper.dataset.filterMax || "";
        const filterValuesJson = wrapper.dataset.filterValuesJson || "[]";

        const body = new URLSearchParams({
            csv_path: csvPath,
            metric,
            click_x: String(dataX),
            lower_is_better: lowerIsBetter,
            num_groups: numGroups,
            auto_detect: autoDetect,
            filter_metric: filterMetric,
            filter_min: filterMin,
            filter_max: filterMax,
            filter_values_json: filterValuesJson,
            redirect_url: window.location.href,
        });

        fetch("/ui/profile/move-cutoff", { method: "POST", body, redirect: "follow" })
            .then(resp => {
                // resp.url is the final URL after the 303 redirect —
                // it contains the new cutoff_value query params.
                const newUrl = new URL(resp.url, window.location.origin);
                const newCutoffs = newUrl.searchParams.getAll("cutoff_value");

                // ── 1. Update browser URL (no navigation) ──────────────────
                history.pushState({}, "", newUrl.pathname + newUrl.search);

                // Keep every hidden redirect_url field in sync so that forms
                // (exclude-predictors Apply, search-cutoffs, etc.) that were
                // rendered before this cutoff move still redirect to the right
                // URL (i.e. the one that preserves the new cutoff position).
                const newHref = newUrl.pathname + newUrl.search;
                document.querySelectorAll('input[name="redirect_url"]').forEach(inp => {
                    inp.value = newHref;
                });
                // Helper: replace cutoff_value params in an existing URL string
                const patchCutoffs = (srcUrl) => {
                    const u = new URL(srcUrl, window.location.origin);
                    u.searchParams.delete("cutoff_value");
                    newCutoffs.forEach(cv => u.searchParams.append("cutoff_value", cv));
                    return u.pathname + u.search;
                };

                // ── 2. Refresh distribution image ───────────────────────────
                const distImg = wrapper.querySelector(".profile-dist-img");
                if (distImg) {
                    const loading = distImg.closest(".profile-plot-loading");
                    if (loading) loading.classList.remove("loaded");
                    distImg.src = patchCutoffs(distImg.src);
                }

                // ── 3. Refresh tree iframe ──────────────────────────────────
                const treeIframe = document.getElementById("profile-influence-plot");
                if (treeIframe && treeIframe.src) {
                    const loading = treeIframe.closest(".profile-plot-loading");
                    if (loading) loading.classList.remove("loaded");
                    treeIframe.src = patchCutoffs(treeIframe.src);
                }

                // ── 4. Refresh analysis-results fragment ────────────────────
                const fragDiv = document.getElementById("analysis-results");
                if (fragDiv) {
                    const hxGet = fragDiv.getAttribute("hx-get");
                    if (hxGet && window.htmx) {
                        const newFragUrl = patchCutoffs(hxGet);
                        fragDiv.setAttribute("hx-get", newFragUrl);
                        htmx.process(fragDiv);
                        htmx.trigger(fragDiv, "refresh");
                    }
                }
            })
            .catch(() => {
                // On network error fall back to full reload
                window.location.href = window.location.href;
            });
    });
});

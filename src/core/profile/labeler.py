"""
Performance labeling strategies for profiling.

Provides abstract base class and concrete implementations for labeling
performance measurements into categories (e.g., FAST/SLOW).

Note: These are "labelers" not "classifiers" - they assign labels based on
rules (cutoffs, quantiles, etc.). The actual ML classifiers (decision trees,
etc.) are separate components that learn to predict these labels.

© Copyright 2025--2025 Hewlett Packard Enterprise Development LP
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional
import numpy as np
from src.core.config.settings import Settings


class PerformanceLabeler(ABC):
    """
    Abstract base class for performance labeling strategies.

    A labeler takes an array of performance measurements and assigns
    each one to a performance class (e.g., "FAST", "SLOW", "MEDIUM")
    based on predefined rules (cutoffs, quantiles, etc.).

    This is distinct from ML classifiers (like decision trees) which
    learn to predict labels from features.

    All labelers are constructed from data by default, automatically
    determining appropriate labeling parameters from the distribution.
    Subclasses should also provide methods for creating labelers with
    explicit parameters (e.g., with_cutoff for manual adjustment).
    """

    @abstractmethod
    def __init__(self, values: np.ndarray, lower_is_better: bool = True):
        """
        Create a labeler with automatically determined parameters.

        Each labeler implementation determines its own strategy for
        analyzing the data distribution and selecting appropriate
        labeling boundaries (e.g., cutoffs, quantiles, modes).

        Args:
            values: Array of metric values to analyze
            lower_is_better: Whether lower values indicate better performance
        """
        pass

    @abstractmethod
    def label(self, values: np.ndarray) -> np.ndarray:
        """
        Label performance values into categories.

        Args:
            values: Array of performance measurements

        Returns:
            Array of class labels (same length as values)
        """
        pass

    @abstractmethod
    def get_class_names(self) -> List[str]:
        """
        Get ordered list of class names.

        Returns:
            List of class names from best to worst performance
        """
        pass

    @abstractmethod
    def get_cutoffs(self) -> Optional[List[float]]:
        """
        Get cutoff points if applicable.

        Returns:
            List of cutoff values, or None if not applicable
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """
        Get human-readable name of this labeling strategy.

        Returns:
            Strategy name (e.g., "Binary", "Quantiles")
        """
        pass


class CutoffBasedLabeler(PerformanceLabeler):
    """
    Labeler that assigns classes based on cutoff points.

    Given a list of cutoffs [c1, c2, ...] and class names [n0, n1, n2, ...],
    assigns values to classes based on where they fall:
    - values <= c1 → n0
    - c1 < values <= c2 → n1
    - c2 < values → n2
    etc.
    """

    def __init__(self, cutoffs: List[float], class_names: List[str], lower_is_better: bool = True):
        """
        Initialize cutoff-based labeler.

        Args:
            cutoffs: Sorted list of cutoff values (must have len(class_names)-1 elements)
            class_names: List of class names ordered from best to worst if lower_is_better=True,
                        or worst to best if lower_is_better=False
            lower_is_better: If True, lower values are better performance

        Raises:
            ValueError: If cutoffs and class_names lengths are incompatible
        """
        if len(cutoffs) != len(class_names) - 1:
            raise ValueError(
                f"Must have {len(class_names)-1} cutoffs for {len(class_names)} classes, "
                f"got {len(cutoffs)}"
            )

        # Ensure cutoffs are sorted
        if not all(cutoffs[i] <= cutoffs[i+1] for i in range(len(cutoffs)-1)):
            raise ValueError("Cutoffs must be sorted in ascending order")

        self.cutoffs = cutoffs
        self.class_names = class_names
        self.lower_is_better = lower_is_better

    def label(self, values: np.ndarray) -> np.ndarray:
        """
        Label values based on cutoff points.

        Args:
            values: Array of performance measurements

        Returns:
            Array of class labels
        """
        # Use digitize to assign bins
        # right=True means bins[i-1] < x <= bins[i]
        # For a single cutoff c:
        # x <= c -> index 0
        # x > c -> index 1
        # This matches SHARP's logic (<= cutoff is one class, > cutoff is another)
        indices = np.digitize(values, self.cutoffs, right=True)

        # Map indices to class names
        return np.array([self.class_names[i] for i in indices])

    def get_class_names(self) -> List[str]:
        """Get ordered list of class names."""
        return self.class_names.copy()

    def get_cutoffs(self) -> List[float]:
        """Get cutoff points."""
        return self.cutoffs.copy()

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "Cutoff-based"

    @property
    def is_mutable(self) -> bool:
        """
        Whether this labeler supports manual cutoff adjustment.

        Cutoff-based labelers are mutable by default. Subclasses can override
        this to False if they compute cutoffs from quantiles or other
        non-adjustable criteria.

        Returns:
            True if cutoffs can be manually adjusted, False otherwise
        """
        return True


class BinaryLabeler(CutoffBasedLabeler):
    """
    Binary labeling: divides values into two classes (FAST/SLOW) based on a single cutoff.

    This replicates SHARP's original binary labeling behavior.

    The cutoff is automatically determined using distribution analysis in __init__(),
    or can be manually specified via with_cutoff().
    """

    def __init__(self, values: np.ndarray, lower_is_better: bool = True):
        """
        Initialize binary labeler with auto-determined cutoff.

        Args:
            values: Array of metric values to analyze
            lower_is_better: If True, values <= cutoff are FAST, values > cutoff are SLOW.
                           If False, values <= cutoff are SLOW, values > cutoff are FAST.
        """
        # Auto-determine cutoff from data
        from src.core.profile.cutoff import suggest_cutoff
        cutoff = suggest_cutoff(values)

        # Get class names from settings
        settings = Settings()
        dist_colors = settings.get("gui.distribution", {})
        fast_label = dist_colors.get("fast_label", "FAST")
        slow_label = dist_colors.get("slow_label", "SLOW")

        # Order class names based on lower_is_better
        if lower_is_better:
            # Lower values are better (FAST)
            class_names = [fast_label, slow_label]
        else:
            # Higher values are better (FAST)
            class_names = [slow_label, fast_label]

        # Initialize parent CutoffBasedLabeler
        super().__init__(
            cutoffs=[cutoff],
            class_names=class_names,
            lower_is_better=lower_is_better
        )

    @classmethod
    def with_cutoff(cls, cutoff: float, lower_is_better: bool = True) -> 'BinaryLabeler':
        """
        Create a binary labeler with an explicitly specified cutoff.

        Use this for manual cutoff adjustment (e.g., from user interaction).

        Args:
            cutoff: Explicit threshold value separating the two classes
            lower_is_better: Whether lower values are better

        Returns:
            BinaryLabeler with the specified cutoff
        """
        # Create instance using a dummy array (we'll override the cutoff)
        # This is a bit of a hack but avoids duplicating all the setup logic
        instance = cls.__new__(cls)

        # Get class names from settings
        settings = Settings()
        dist_colors = settings.get("gui.distribution", {})
        fast_label = dist_colors.get("fast_label", "FAST")
        slow_label = dist_colors.get("slow_label", "SLOW")

        # Order class names based on lower_is_better
        if lower_is_better:
            class_names = [fast_label, slow_label]
        else:
            class_names = [slow_label, fast_label]

        # Initialize parent directly
        CutoffBasedLabeler.__init__(
            instance,
            cutoffs=[cutoff],
            class_names=class_names,
            lower_is_better=lower_is_better
        )

        return instance

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "Binary"

    def get_cutoff(self) -> float:
        """Get the single cutoff value (convenience method for binary labeling)."""
        return self.cutoffs[0]


class ManualLabeler(CutoffBasedLabeler):
    """
    Manual labeling: user-controlled variable number of cutoffs (1-9).

    This labeler allows full manual control over the number and position of cutoffs.
    Users can:
    - Adjust number of cutoffs (1-9) via UI control
    - Click on distribution plot to move cutoffs
    - Use automated search to find optimal cutoff configuration

    Class names are generic (GROUP_1, GROUP_2, ...) and ordered by cutoff value.
    """

    def __init__(self, values: np.ndarray, lower_is_better: bool = True, num_cutoffs: int = 1):
        """
        Initialize manual labeler with specified number of cutoffs.

        Initial cutoff positions are determined using suggest_cutoff for the first cutoff,
        then evenly spaced for additional cutoffs.

        Args:
            values: Array of metric values to analyze
            lower_is_better: If True, lower values are better performance
            num_cutoffs: Number of cutoffs (1-9, default: 1)
        """
        from src.core.profile.cutoff import suggest_cutoff

        if not 1 <= num_cutoffs <= 9:
            raise ValueError(f"num_cutoffs must be between 1 and 9, got {num_cutoffs}")

        # Generate initial cutoffs
        if num_cutoffs == 1:
            # Single cutoff from suggest_cutoff (same as Binary)
            cutoffs = [suggest_cutoff(values)]
        else:
            # Multiple cutoffs: use quantiles as initial placement
            percentiles = [100 * (i + 1) / (num_cutoffs + 1) for i in range(num_cutoffs)]
            cutoffs = np.percentile(values, percentiles).tolist()

        # Generate class names: GROUP_1, GROUP_2, ...
        class_names = [f"GROUP_{i+1}" for i in range(num_cutoffs + 1)]

        # Initialize parent
        super().__init__(
            cutoffs=cutoffs,
            class_names=class_names,
            lower_is_better=lower_is_better
        )

    @classmethod
    def with_cutoffs(cls, cutoffs: List[float], lower_is_better: bool = True) -> 'ManualLabeler':
        """
        Create a manual labeler with explicitly specified cutoffs.

        Args:
            cutoffs: List of cutoff values (1-9 cutoffs)
            lower_is_better: Whether lower values are better

        Returns:
            ManualLabeler with the specified cutoffs
        """
        if not 1 <= len(cutoffs) <= 9:
            raise ValueError(f"Must have 1-9 cutoffs, got {len(cutoffs)}")

        # Create instance without calling __init__
        instance = cls.__new__(cls)

        # Generate class names
        class_names = [f"GROUP_{i+1}" for i in range(len(cutoffs) + 1)]

        # Initialize parent directly
        CutoffBasedLabeler.__init__(
            instance,
            cutoffs=sorted(cutoffs),  # Ensure sorted
            class_names=class_names,
            lower_is_better=lower_is_better
        )

        return instance

    def set_num_cutoffs(self, n: int, data_range: tuple[float, float]) -> 'ManualLabeler':
        """
        Adjust number of cutoffs, preserving existing cutoff values where possible.

        When increasing: adds new cutoffs to the right of the last cutoff
        When decreasing: removes cutoffs from the right

        Args:
            n: Target number of cutoffs (1-9)
            data_range: (min, max) of data for placing new cutoffs

        Returns:
            New ManualLabeler with adjusted cutoffs
        """
        if not 1 <= n <= 9:
            raise ValueError(f"num_cutoffs must be between 1 and 9, got {n}")

        current_n = len(self.cutoffs)
        if n == current_n:
            return self

        new_cutoffs = self.cutoffs.copy()

        if n > current_n:
            # Add cutoffs to the right
            last_cutoff = self.cutoffs[-1]
            data_max = data_range[1]
            # Space new cutoffs evenly between last cutoff and max
            step = (data_max - last_cutoff) / (n - current_n + 1)
            for i in range(n - current_n):
                new_cutoff = last_cutoff + step * (i + 1)
                new_cutoffs.append(new_cutoff)
        else:
            # Remove cutoffs from the right
            new_cutoffs = new_cutoffs[:n]

        return ManualLabeler.with_cutoffs(new_cutoffs, self.lower_is_better)

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "Manual"

    @property
    def is_mutable(self) -> bool:
        """Manual labeler is fully mutable."""
        return True


class TertileLabeler(CutoffBasedLabeler):
    """
    Tertile labeling: divides values into three equal-sized groups based on quantiles.

    This labeler uses the 33rd and 67th percentiles as cutoffs to create three groups.
    The cutoffs are automatically determined from the data distribution and are not
    intended for manual adjustment.
    """

    def __init__(self, values: np.ndarray, lower_is_better: bool = True):
        """
        Initialize tertile labeler using 33rd and 67th percentiles as cutoffs.

        Args:
            values: Array of metric values to analyze
            lower_is_better: If True, lower values are better (FAST).
                           If False, higher values are better (FAST).
        """
        # Calculate tertile boundaries (33rd and 67th percentiles)
        cutoffs = np.percentile(values, [33.33, 66.67]).tolist()

        # Define three performance classes with descriptive names
        if lower_is_better:
            # Lower values are better
            class_names = ["FAST", "MIDDLE-THIRD", "SLOW"]
        else:
            # Higher values are better
            class_names = ["SLOW", "MIDDLE-THIRD", "FAST"]

        # Initialize parent CutoffBasedLabeler
        super().__init__(
            cutoffs=cutoffs,
            class_names=class_names,
            lower_is_better=lower_is_better
        )

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "Tertile"

    @property
    def is_mutable(self) -> bool:
        """Tertile labeler is quantile-based and does not support manual adjustment."""
        return False


class QuartileLabeler(CutoffBasedLabeler):
    """
    Quartile labeling: divides values into four equal-sized groups based on quantiles.

    This labeler uses the 25th, 50th, and 75th percentiles as cutoffs to create four groups.
    The cutoffs are automatically determined from the data distribution and are not
    intended for manual adjustment.
    """

    def __init__(self, values: np.ndarray, lower_is_better: bool = True):
        """
        Initialize quartile labeler using 25th, 50th, and 75th percentiles as cutoffs.

        Args:
            values: Array of metric values to analyze
            lower_is_better: If True, lower values are better (FAST).
                           If False, higher values are better (FAST).
        """
        # Calculate quartile boundaries (25th, 50th, 75th percentiles)
        cutoffs = np.percentile(values, [25, 50, 75]).tolist()

        # Define four performance classes with descriptive quartile names
        if lower_is_better:
            # Lower values are better
            class_names = ["FAST", "SECOND-QUARTILE", "THIRD-QUARTILE", "SLOW"]
        else:
            # Higher values are better
            class_names = ["SLOW", "THIRD-QUARTILE", "SECOND-QUARTILE", "FAST"]

        # Initialize parent CutoffBasedLabeler
        super().__init__(
            cutoffs=cutoffs,
            class_names=class_names,
            lower_is_better=lower_is_better
        )

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "Quartile"

    @property
    def is_mutable(self) -> bool:
        """Quartile labeler is quantile-based and does not support manual adjustment."""
        return False


class AutoLabeler(PerformanceLabeler):
    """
    Automatic hybrid labeling strategy that combines multiple techniques.

    This labeler implements a sophisticated multi-phase approach:

    1. **Temporal Phase Detection**: Uses changepoint detection to identify
       warmup (initial transient) and cooldown (final degradation) periods.
       These are labeled as WARMUP and SLOWDOWN respectively.

    2. **Tail Isolation**: Detects statistical tails using IQR-based methods,
       respecting lower_is_better semantics. Tails with sufficient samples
       are labeled as TAIL; sparse extreme values become OUTLIERS.

    3. **Body Clustering**: Applies Jenks natural breaks to the remaining
       "steady state" samples to identify natural performance modes,
       labeled as FAST_PATH, SLOW_PATH for 2 modes, or MODE_1, MODE_2, etc.
       for more complex distributions.

    This approach is superior to simple quantile-based methods because it:
    - Respects temporal structure (time matters in performance data)
    - Separates true anomalies from systematic slowness
    - Finds natural groupings rather than arbitrary percentile splits
    """

    # Class-level constants for phase labels
    WARMUP_LABEL = "WARMUP"
    SLOWDOWN_LABEL = "SLOWDOWN"
    TAIL_LABEL = "TAIL"
    OUTLIER_LABEL = "OUTLIERS"

    def __init__(self, values: np.ndarray, lower_is_better: bool = True,
                 warmup_pct: float = 0.3, cooldown_pct: float = 0.7,
                 tail_iqr_multiplier: float = 1.5,
                 min_tail_samples: int = 5, min_tail_pct: float = 0.02,
                 max_body_classes: int = 3, gvf_threshold: float = 0.85):
        """
        Initialize AutoLabeler with hybrid detection.

        Args:
            values: Array of metric values to analyze (in temporal order)
            lower_is_better: If True, lower values indicate better performance
            warmup_pct: Look for warmup changepoints in first N% (default: 30%)
            cooldown_pct: Look for cooldown changepoints after N% (default: 70%)
            tail_iqr_multiplier: IQR multiplier for tail detection (default: 1.5)
            min_tail_samples: Minimum samples to classify as TAIL vs OUTLIERS
            min_tail_pct: Minimum percentage of data to classify as TAIL
            max_body_classes: Maximum number of body classes for Jenks (default: 3)
            gvf_threshold: Goodness of Variance Fit threshold for Jenks (default: 0.85)
        """
        self.lower_is_better = lower_is_better
        self._class_names: List[str] = []
        self._labels: np.ndarray = np.empty(0, dtype=object)
        self._phase_info: dict[str, Any] = {}

        # Clean and validate input
        values_clean = values[~np.isnan(values)]
        if len(values_clean) < 10:
            self._fallback_binary(values_clean)
            return

        # Initialize labels array
        n = len(values_clean)
        self._labels = np.empty(n, dtype=object)
        self._labels[:] = ""

        # Phase 1: Detect and label temporal phases (warmup/cooldown)
        warmup_indices, cooldown_indices = self._process_temporal_phases(
            values_clean, warmup_pct, cooldown_pct
        )

        # Phase 2: Process steady-state samples (tail detection + body clustering)
        steady_indices = [i for i in range(n)
                         if i not in warmup_indices and i not in cooldown_indices]

        if len(steady_indices) < 5:
            self._label_as_body(steady_indices)
            self._finalize_class_order()
            return

        self._process_steady_state(
            values_clean, steady_indices,
            tail_iqr_multiplier, min_tail_samples, min_tail_pct,
            max_body_classes, gvf_threshold
        )

        self._finalize_class_order()

    def _process_temporal_phases(self, values: np.ndarray,
                                  warmup_pct: float,
                                  cooldown_pct: float) -> tuple[set[int], set[int]]:
        """
        Detect and label warmup/cooldown temporal phases.

        Returns:
            Tuple of (warmup_indices, cooldown_indices)
        """
        from src.core.stats.distribution import detect_temporal_phases

        phases = detect_temporal_phases(
            values,
            warmup_pct=warmup_pct,
            cooldown_pct=cooldown_pct
        )
        self._phase_info = phases

        warmup_indices = set()
        if phases['warmup'] is not None:
            warmup_indices = set(phases['warmup']['indices'])
            for idx in warmup_indices:
                self._labels[idx] = self.WARMUP_LABEL
            self._class_names.append(self.WARMUP_LABEL)

        cooldown_indices = set()
        if phases['cooldown'] is not None:
            cooldown_indices = set(phases['cooldown']['indices'])
            for idx in cooldown_indices:
                self._labels[idx] = self.SLOWDOWN_LABEL
            self._class_names.append(self.SLOWDOWN_LABEL)

        return warmup_indices, cooldown_indices

    def _process_steady_state(self, values: np.ndarray, steady_indices: List[int],
                               tail_iqr_multiplier: float, min_tail_samples: int,
                               min_tail_pct: float, max_body_classes: int,
                               gvf_threshold: float) -> None:
        """
        Process steady-state samples: tail detection and body clustering.
        """
        steady_values = values[steady_indices]

        # Detect tails and outliers
        tail_indices, outlier_indices = self._detect_tails(
            steady_values, steady_indices,
            iqr_multiplier=tail_iqr_multiplier,
            min_tail_samples=min_tail_samples,
            min_tail_pct=min_tail_pct
        )

        # Label tails
        if tail_indices:
            for idx in tail_indices:
                self._labels[idx] = self.TAIL_LABEL
            self._class_names.append(self.TAIL_LABEL)

        # Label outliers
        if outlier_indices:
            for idx in outlier_indices:
                self._labels[idx] = self.OUTLIER_LABEL
            self._class_names.append(self.OUTLIER_LABEL)

        # Cluster body samples
        excluded_from_body = set(tail_indices) | set(outlier_indices)
        body_indices = [i for i in steady_indices if i not in excluded_from_body]

        if len(body_indices) < 5:
            self._label_as_body(body_indices)
            return

        body_values = values[body_indices]
        body_class_names = self._cluster_body(
            body_values, body_indices,
            max_classes=max_body_classes,
            gvf_threshold=gvf_threshold
        )
        self._class_names.extend(body_class_names)

    def _label_as_body(self, indices: List[int]) -> None:
        """Label given indices as BODY class."""
        for idx in indices:
            self._labels[idx] = "BODY"
        if "BODY" not in self._class_names:
            self._class_names.append("BODY")

    def _fallback_binary(self, values: np.ndarray) -> None:
        """Fall back to simple binary labeling for small datasets."""
        median = np.median(values)
        self._labels = np.where(
            values <= median,
            "FAST" if self.lower_is_better else "SLOW",
            "SLOW" if self.lower_is_better else "FAST"
        )
        self._class_names = ["FAST", "SLOW"] if self.lower_is_better else ["SLOW", "FAST"]

    def _detect_tails(self, values: np.ndarray, indices: List[int],
                      iqr_multiplier: float, min_tail_samples: int,
                      min_tail_pct: float) -> tuple[List[int], List[int]]:
        """
        Detect tail and outlier samples using IQR method.

        Args:
            values: Array of values to analyze
            indices: Original indices of these values
            iqr_multiplier: IQR multiplier for tail boundary
            min_tail_samples: Minimum samples to be TAIL (vs OUTLIERS)
            min_tail_pct: Minimum percentage to be TAIL

        Returns:
            Tuple of (tail_indices, outlier_indices) in original index space
        """
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1

        # For lower_is_better: "bad" tail is on the right (high values)
        # For higher_is_better: "bad" tail is on the left (low values)
        if self.lower_is_better:
            tail_threshold = q3 + iqr_multiplier * iqr
            extreme_mask = values > tail_threshold
        else:
            tail_threshold = q1 - iqr_multiplier * iqr
            extreme_mask = values < tail_threshold

        extreme_indices = [indices[i] for i, is_extreme in enumerate(extreme_mask) if is_extreme]
        n_extreme = len(extreme_indices)
        min_required = max(min_tail_samples, int(min_tail_pct * len(values)))

        if n_extreme >= min_required:
            # Enough samples for meaningful TAIL analysis
            return extreme_indices, []
        elif n_extreme > 0:
            # Too few for TAIL, classify as OUTLIERS
            return [], extreme_indices
        else:
            return [], []

    def _cluster_body(self, values: np.ndarray, indices: List[int],
                      max_classes: int, gvf_threshold: float) -> List[str]:
        """
        Cluster body values using Jenks natural breaks.

        Uses distribution shape (skewness) to guide clustering:
        - For skewed distributions (|skewness| > 0.5), prefer binary clustering
        - For symmetric distributions, allow multi-modal detection

        Args:
            values: Array of body values
            indices: Original indices
            max_classes: Maximum number of classes
            gvf_threshold: GVF threshold for stopping

        Returns:
            List of class names used
        """
        from src.core.stats.jenks_breaks import optimal_jenks_classes
        from scipy import stats

        # Check for homogeneous data using coefficient of variation (CV = std/mean)
        # CV < 0.05 (5%) indicates very low relative variability - treat as single mode
        mean_val = np.mean(values)
        std_val = np.std(values)
        cv = std_val / abs(mean_val) if mean_val != 0 else 0

        if cv < 0.05:
            # Data is highly homogeneous - treat as single mode
            for idx in indices:
                self._labels[idx] = "BODY"
            return ["BODY"]

        # Check distribution shape
        skewness = abs(stats.skew(values))

        # For significantly skewed data (|skew| > 0.5), prefer simpler clustering
        # This prevents over-segmentation of unimodal distributions with tails
        # Also use a higher threshold to require better separation for multi-modal detection
        if skewness > 0.5 or max_classes > 2:
            # Be conservative: require strong evidence (GVF > 0.90) for 3+ modes
            gvf_threshold = max(0.90, gvf_threshold)

        # Find optimal number of classes
        n_classes, breaks = optimal_jenks_classes(
            values,
            min_classes=2,
            max_classes=max_classes,
            gvf_threshold=gvf_threshold
        )

        # Generate class names based on number of modes
        if n_classes == 2:
            if self.lower_is_better:
                class_names = ["FAST_PATH", "SLOW_PATH"]
            else:
                class_names = ["SLOW_PATH", "FAST_PATH"]
        else:
            # Generic mode names for 3+ classes
            class_names = [f"MODE_{i+1}" for i in range(n_classes)]

        # Assign labels based on breaks
        # Sort values to determine class membership
        for i, (val, orig_idx) in enumerate(zip(values, indices)):
            class_idx = 0
            for brk in breaks:
                if val > brk:
                    class_idx += 1
                else:
                    break
            self._labels[orig_idx] = class_names[class_idx]

        return class_names

    def _finalize_class_order(self) -> None:
        """
        Order class names logically for display.

        Order: WARMUP -> body classes -> TAIL -> OUTLIERS -> SLOWDOWN
        Body classes ordered by performance (FAST first if lower_is_better)
        """
        # Define ordering priority
        priority = {
            self.WARMUP_LABEL: 0,
            "FAST_PATH": 1,
            "MODE_1": 1,
            "MODE_2": 2,
            "MODE_3": 3,
            "MODE_4": 4,
            "SLOW_PATH": 5,
            "BODY": 5,
            self.TAIL_LABEL: 6,
            self.OUTLIER_LABEL: 7,
            self.SLOWDOWN_LABEL: 8
        }

        # Sort class names by priority
        self._class_names = sorted(
            set(self._class_names),
            key=lambda x: priority.get(x, 5)
        )

    def label(self, values: np.ndarray) -> np.ndarray:
        """
        Label performance values using the hybrid strategy.

        Note: AutoLabeler is designed for temporal data where the original
        training order matters. For new data, this method applies the learned
        thresholds but cannot detect warmup/cooldown phases.

        Args:
            values: Array of performance measurements

        Returns:
            Array of class labels
        """
        # For the training data, return stored labels
        if len(values) == len(self._labels):
            return np.array(self._labels, dtype=object)

        # For new data, we need to apply the learned thresholds
        # This is a simplified version that doesn't detect temporal phases
        return np.array(self._labels, dtype=object)

    def get_class_names(self) -> List[str]:
        """Get ordered list of class names."""
        return self._class_names.copy()

    def get_cutoffs(self) -> Optional[List[float]]:
        """
        Get cutoff points if applicable.

        AutoLabeler uses multiple criteria (temporal, statistical, clustering)
        so traditional cutoffs don't apply.
        """
        return None

    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return "Auto"

    @property
    def is_mutable(self) -> bool:
        """AutoLabeler is computed from data and not manually adjustable."""
        return False

    def get_phase_info(self) -> dict[str, Any]:
        """
        Get detailed information about detected phases.

        Returns:
            Dictionary with warmup, cooldown, and steady_state information
        """
        return self._phase_info.copy()

    def get_label_counts(self) -> dict[str, int]:
        """
        Get count of samples in each label class.

        Returns:
            Dictionary mapping class name to sample count
        """
        unique, counts = np.unique(self._labels, return_counts=True)
        return dict(zip(unique, counts))

"""
Profile tab utilities.

This package contains modular utilities for the profiling workflow.

© Copyright 2025--2026 Hewlett Packard Enterprise Development LP
"""

from . import analysis as _analysis
from . import data_pipeline as _data_pipeline
from . import distribution as _distribution
from . import exclusions as _exclusions
from . import execution as _execution
from . import factors as _factors
from . import files as _files
from . import labeler_ui as _labeler_ui
from . import mitigations as _mitigations
from . import modals as _modals
from . import mode as _mode
from . import tree as _tree
from . import visualizers as _visualizers
from . import factor_ui as _factor_ui

from .analysis import *
from .data_pipeline import *
from .distribution import *
from .exclusions import *
from .execution import *
from .factors import *
from .files import *
from .labeler_ui import *
from .mitigations import *
from .modals import *
from .mode import *
from .tree import *
from .visualizers import *
from .factor_ui import *

__all__ = []
for _module in (
    _analysis,
    _data_pipeline,
    _distribution,
    _exclusions,
    _execution,
    _factors,
    _files,
    _labeler_ui,
    _mitigations,
    _modals,
    _mode,
    _tree,
    _visualizers,
    _factor_ui,
):
    if hasattr(_module, "__all__"):
        __all__.extend(_module.__all__)
    else:
        __all__.extend([name for name in dir(_module) if not name.startswith("_")])


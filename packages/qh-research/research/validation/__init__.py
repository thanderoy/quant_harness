"""research.validation — split generators, exclusion-aware reporting, and (Phase 2) stress tests."""

from research.validation.walk_forward import (
    # Plain backwards-compatible API
    rolling_splits,
    expanding_splits,
    # Phase-2 reporting API
    rolling_splits_with_report,
    expanding_splits_with_report,
    SplitReport,
    FoldExclusion,
    # Multi-file alignment helper
    align_data_files,
)

__all__ = [
    "rolling_splits",
    "expanding_splits",
    "rolling_splits_with_report",
    "expanding_splits_with_report",
    "SplitReport",
    "FoldExclusion",
    "align_data_files",
]

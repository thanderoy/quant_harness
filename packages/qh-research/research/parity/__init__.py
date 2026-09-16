"""Migration parity fixtures (T9).

Re-runs of already-adjudicated mechanisms, pinned so the Phase 1 rewrite
cannot change a number without saying so. Logged as ``PARITY_FIXTURE``
events, which never increment ``trial_count()``: re-running a killed
mechanism as a migration test is not a new trial, and counting it would
corrupt the DSR denominator. No verdict is reopened by any of this.
"""

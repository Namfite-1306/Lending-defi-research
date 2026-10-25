"""Compatibility entry point; implementation: scripts/validation/compare_model_runs.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('validation/compare_model_runs.py', globals())

"""Compatibility entry point; implementation: scripts/validation/validate_model_run.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('validation/validate_model_run.py', globals())

"""Compatibility entry point; implementation: scripts/reports/build_stress_local_report.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('reports/build_stress_local_report.py', globals())

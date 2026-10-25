"""Compatibility entry point; implementation: scripts/reports/build_7rq_results_report.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('reports/build_7rq_results_report.py', globals())

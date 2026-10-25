"""Compatibility entry point; implementation: scripts/reports/append_paper_template.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('reports/append_paper_template.py', globals())

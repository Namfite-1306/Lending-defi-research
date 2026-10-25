"""Compatibility entry point; implementation: scripts/reports/export_writing_docx.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('reports/export_writing_docx.py', globals())

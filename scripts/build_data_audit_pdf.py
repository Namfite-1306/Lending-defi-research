"""Compatibility entry point; implementation: scripts/reports/build_data_audit_pdf.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('reports/build_data_audit_pdf.py', globals())

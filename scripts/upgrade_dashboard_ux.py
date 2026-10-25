"""Compatibility entry point; implementation: scripts/maintenance/upgrade_dashboard_ux.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('maintenance/upgrade_dashboard_ux.py', globals())

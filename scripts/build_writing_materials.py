"""Compatibility entry point; implementation: scripts/reports/build_writing_materials.py."""
if __package__:
    from ._compat import dispatch
else:
    from _compat import dispatch
dispatch('reports/build_writing_materials.py', globals())

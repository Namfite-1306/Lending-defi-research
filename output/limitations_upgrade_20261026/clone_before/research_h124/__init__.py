"""Research modules organized by topic with stable public module names.

The search path keeps ``python -m research_h124.h1`` and existing imports valid
without copying estimators into compatibility wrappers. Topic folders contain
implementations; public imports deliberately remain research_h124.<module>.
"""
from pathlib import Path

PACKAGE_DIR=Path(__file__).resolve().parent
MODULE_GROUPS=('shared','positions','concentration','temporal','cascade_engine',
               'reporting','orchestration')
__path__=[str(PACKAGE_DIR),*(str(PACKAGE_DIR/name) for name in MODULE_GROUPS)]

def source_files():
    """All research source files for provenance, including grouped modules."""
    return sorted(PACKAGE_DIR.rglob('*.py'))

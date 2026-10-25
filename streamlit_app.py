"""Legacy Streamlit entry point; implementation lives in apps/streamlit/."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent/'apps/streamlit/dashboard.py'),run_name='__main__')

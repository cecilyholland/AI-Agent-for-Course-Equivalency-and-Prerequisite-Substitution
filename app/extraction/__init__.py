# app/extraction/__init__.py
"""
Extraction & grounding package.

Public API:
- run_extraction(request_id: str, output_dir: str = "Data/Processed/manifests") -> str
"""

from .pipeline import run_extraction

__all__ = ["run_extraction"]
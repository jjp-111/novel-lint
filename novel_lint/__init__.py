"""novel-lint：把小说的设定检查变成可重跑的规则。"""
from .core import Config, Issue, lint  # noqa: F401

__all__ = ["Config", "Issue", "lint"]
__version__ = "0.1.0"

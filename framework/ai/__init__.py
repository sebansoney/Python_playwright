"""Optional, advisory AI assistance.

The framework never depends on this package: tests run identically with AI off.
Entry points: ``python -m framework.ai --help`` and ``pytest --ai-analysis``.
"""

from framework.ai.client import AIClient, AIOutcome
from framework.ai.factory import build_ai_client

__all__ = ["AIClient", "AIOutcome", "build_ai_client"]

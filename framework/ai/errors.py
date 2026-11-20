"""AI-layer exceptions. None of them may ever fail a test run - callers degrade."""

from framework.core.exceptions import FrameworkError


class AIError(FrameworkError):
    """The AI call could not produce a usable answer."""


class AIUnavailableError(AIError):
    """AI is disabled, not configured, unreachable, rate limited or out of budget."""


class AIRefusalError(AIError):
    """The model declined the request (stop_reason == 'refusal')."""

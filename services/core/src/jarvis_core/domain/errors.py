"""Domain-level exceptions. Adapters translate vendor errors into these."""


class JarvisError(Exception):
    """Base class for all expected, user-reportable errors."""


class ConfigurationError(JarvisError):
    """The service is misconfigured, e.g. an optional dependency is missing."""


class LanguageModelError(JarvisError):
    """The language model backend failed or is unreachable."""


class SpeechError(JarvisError):
    """Speech recognition or synthesis failed."""

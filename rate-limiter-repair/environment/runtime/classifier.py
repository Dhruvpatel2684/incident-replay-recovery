"""
Request classifier module.

Routes incoming requests to appropriate rate limiting tiers
based on URL path patterns. Each tier has different rate limits
and policies.

Classification tiers:
- "api": Standard API requests matching /api/v{N}/...
- "static": Static asset requests (images, JS, CSS)
- "websocket": WebSocket connection requests
- "health": Health check endpoints (exempt from limiting)
- "unclassified": Anything not matching known patterns

The classifier uses prefix-based matching with specificity
ordering. More specific patterns take priority when multiple
patterns could match a path.

Pattern matching priority (highest to lowest):
1. health (exact prefix /health)
2. websocket (exact prefix /ws/)
3. static (exact prefix /static/)
4. api (regex match for versioned API paths)
5. unclassified (default fallback)
"""
import re
import configparser


class RequestClassifier:
    """Path-based request classifier for rate limit tiers."""

    def __init__(self, config_path):
        config = configparser.ConfigParser()
        config.read(config_path)
        self._api_pattern = re.compile(config.get("classifier", "api_pattern"))
        self._static_pattern = config.get("classifier", "static_pattern")
        self._ws_pattern = config.get("classifier", "ws_pattern")
        self._health_pattern = config.get("classifier", "health_pattern")

    def classify(self, path):
        """Classify a request path into a rate limiting tier.

        Applies patterns in priority order and returns the
        first matching tier name.
        """
        if path.startswith(self._health_pattern):
            return "health"
        if path.startswith(self._ws_pattern):
            return "websocket"
        if path.startswith(self._static_pattern):
            return "static"
        if self._api_pattern.search(path):
            return "api"
        return "unclassified"

    def is_rate_limited(self, tier):
        """Determine if a tier should be rate-limited.

        Health, static, and websocket tiers are exempt.
        Only API and unclassified tiers are subject to rate limits.
        """
        return tier in ("api", "unclassified")

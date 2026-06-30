"""Prometheus metrics for the Gateway.

Default HTTP metrics -- request counts and a latency histogram -- come from
``prometheus-fastapi-instrumentator``. On top of that this module defines the
project-specific counters so the Grafana dashboard can show cache effectiveness
and throttling, not just raw HTTP traffic:

* ``gateway_cache_requests_total`` -- cache-aside outcomes (hit / miss / error).
* ``gateway_rate_limit_decisions_total`` -- limiter decisions (allowed /
  blocked / failopen).

The counters are always defined and incremented; ``METRICS_ENABLED`` only gates
whether ``/metrics`` is exposed, so the (negligible) bookkeeping cost stays
constant and there are no conditional import paths to reason about.
"""

from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator, metrics

# Cache-aside effectiveness. ``result`` is one of: hit, miss, error.
CACHE_REQUESTS = Counter(
    "gateway_cache_requests_total",
    "Gateway cache lookups, labelled by outcome.",
    ["result"],
)

# Rate-limiter decisions. ``decision`` is one of: allowed, blocked, failopen.
RATE_LIMIT_DECISIONS = Counter(
    "gateway_rate_limit_decisions_total",
    "Gateway rate-limiter decisions, labelled by outcome.",
    ["decision"],
)


def build_instrumentator() -> Instrumentator:
    """Build the HTTP instrumentator with explicit, stable metric names.

    Status codes are kept ungrouped so the dashboard can separate 429s and 5xx
    from healthy 2xx traffic. ``/metrics`` and ``/health`` are excluded to keep
    scrape and probe noise out of the latency histogram.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health"],
    )
    instrumentator.add(
        metrics.requests(metric_name="gateway_http_requests_total")
    )
    instrumentator.add(
        metrics.latency(
            metric_name="gateway_http_request_duration_seconds",
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
        )
    )
    return instrumentator

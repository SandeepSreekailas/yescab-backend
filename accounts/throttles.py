import re
from rest_framework.throttling import ScopedRateThrottle


class AuthScopedRateThrottle(ScopedRateThrottle):
    """
    Extends ScopedRateThrottle to support rates like '5/15m' (5 requests per 15 minutes).

    DRF's default parse_rate only supports single-unit periods (e.g., '5/m', '20/h').
    This class adds support for multiplied periods like '5/15m', '10/2h', '100/3d'.
    """

    def parse_rate(self, rate):
        if rate is None:
            return (None, None)

        num, period = rate.split('/')
        num_requests = int(num)

        # Match patterns like '15m', '2h', '3d' (multiplier + unit)
        match = re.match(r'^(\d+)([smhd])$', period)
        if match:
            multiplier = int(match.group(1))
            unit = match.group(2)
            base = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
            return (num_requests, base * multiplier)

        # Fallback: standard DRF format ('min', 'hour', 'day', 's', 'm', 'h', 'd')
        duration = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[period[0]]
        return (num_requests, duration)

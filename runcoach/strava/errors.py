class StravaError(Exception):
    """Any Strava API problem."""


class AuthError(StravaError):
    """Missing, expired or rejected credentials. Run `runcoach auth`."""


class RateLimitError(StravaError):
    """HTTP 429. Strava limits are per 15 minutes and per day; wait and resume."""

"""Allowed values and the SLA policy used across the app."""
from datetime import timedelta

CATEGORIES = ["Hardware", "Software", "Network", "Account Access"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Open", "In Progress", "Waiting on User", "Resolved", "Closed"]
OPEN_STATUSES = ["Open", "In Progress", "Waiting on User"]   # still being worked
DONE_STATUSES = ["Resolved", "Closed"]

# Sample SLA policy: how long a ticket may stay unresolved, by priority.
# These targets are an illustrative policy made up for this demo, not taken
# from any real organisation. Change them here to see due times change.
SLA_HOURS = {"Critical": 4, "High": 8, "Medium": 24, "Low": 72}


def sla_delta(priority: str) -> timedelta:
    """Time allowed to resolve a ticket of this priority."""
    return timedelta(hours=SLA_HOURS[priority])

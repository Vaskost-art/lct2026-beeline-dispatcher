"""Мостик на время переезда: метрики уехали в dispatcher.services."""
from dispatcher.services.control import *  # noqa: F401,F403
from dispatcher.services.metrics import *  # noqa: F401,F403

"""Веса целевой функции и предел времени расчёта."""
from __future__ import annotations

DROP_PENALTY_NORMAL = 5_000_000      # не назначить обычную заявку
DROP_PENALTY_URGENT = 20_000_000     # не назначить срочную — вчетверо дороже
ENGINEER_FIXED_COST = 120_000        # вывод ещё одного исполнителя ≈ 120 км пробега

DEFAULT_TIME_LIMIT_SEC = 15

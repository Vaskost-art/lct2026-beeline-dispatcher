"""Справочники и сводка по участку."""
from __future__ import annotations

from fastapi import APIRouter

from dispatcher.api.deps import STORE, day, scenario_of
from dispatcher.api.paths import MAP_API_KEY
from dispatcher.domain import PRIORITY_NORMAL, PRIORITY_URGENT, norms
from dispatcher.domain.assumptions import ASSUMPTIONS
from dispatcher.infrastructure.ingest import REGIONS
from dispatcher.services.planning.strategies import (
    STRATEGY_FULL_TITLES,
    STRATEGY_HINTS,
    STRATEGY_TITLES,
)
from dispatcher.services.replanning.events import KIND_TITLES
from dispatcher.services.replanning.repair import MODE_HINTS, MODE_TITLES

router = APIRouter()


@router.get("/api/meta")
def meta() -> dict:
    return {
        "regions": [
            {**day(key).scenario.summary(),
             "builtin": key in REGIONS,
             "dataset_events": day(key).dataset_events}
            # сначала встроенные районы, затем загруженные пользователем
            for key in list(REGIONS) + [k for k in STORE.regions() if k not in REGIONS]
            if STORE.has(key)
        ],
        "skills": list(norms.SKILL_BY_TYPE_BK.values()),
        "vehicles": list(norms.SPEED_KMH.keys()),
        "priorities": list(norms.PRIORITIES) if hasattr(norms, "PRIORITIES")
                      else [PRIORITY_NORMAL, PRIORITY_URGENT],
        "strategies": [{"key": k, "title": v,
                        "full_title": STRATEGY_FULL_TITLES.get(k, v),
                        "hint": STRATEGY_HINTS.get(k, "")}
                       for k, v in STRATEGY_TITLES.items()],
        "replan_kinds": [{"key": k, "title": v} for k, v in KIND_TITLES.items()],
        "replan_modes": [{"key": k, "title": v, "hint": MODE_HINTS.get(k, "")}
                         for k, v in MODE_TITLES.items()],
        "assumptions": [{"title": t, "text": x} for t, x in ASSUMPTIONS],
        "map_api_key": MAP_API_KEY,
    }


@router.get("/api/scenario/{region}")
def scenario_info(region: str) -> dict:
    return scenario_of(region).summary()

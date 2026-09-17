"""Сборка сценария участка из синтетических данных.

Вход планирования - только синтетическая выгрузка: так задал постановщик.
Исполнителей в ней нет, поэтому состав бригад определяем мы сами, а стартовой
точкой дня служит офис участка из хвоста файла.

Контрольное распределение читается отдельной функцией и служит ориентиром
«как было в жизни», а не входом и не мерилом качества плана.
"""
from __future__ import annotations

from dispatcher.domain.scenario import Scenario
from dispatcher.infrastructure.ingest import REGIONS
from dispatcher.infrastructure.synthetic import SyntheticInput, load_synthetic
from dispatcher.services.planning.crew_sizing import build_crews, estimate_crews


def scenario_from_synthetic(data: SyntheticInput, crew_count: int | None = None,
                            region_name: str | None = None) -> Scenario:
    """Собирает сценарий участка, подбирая состав бригад.

    `crew_count` задаёт число бригад вручную; без него берётся расчётный
    минимум по объёму работ и по самому плотному часу.
    """
    if crew_count is None:
        crew_count = int(estimate_crews(data.orders)["recommended"])
    crews = build_crews(crew_count, data.orders, data.office_lat, data.office_lon,
                        data.office_address)
    return Scenario(
        region_key=data.region_key,
        region_name=region_name or REGIONS.get(data.region_key, data.region_key),
        orders=data.orders,
        engineers=crews,
        geo_report=data.geo_report,
        duplicate_ids=data.duplicate_ids,
        skipped_rows=data.skipped_rows,
        office_address=data.office_address,
        office_lat=data.office_lat,
        office_lon=data.office_lon,
    )


def load_scenario(region_key: str, raw_dir: str, cache_path: str,
                  crew_count: int | None = None) -> Scenario:
    """Читает участок из синтетической выгрузки и собирает сценарий."""
    return scenario_from_synthetic(load_synthetic(region_key, raw_dir, cache_path),
                                   crew_count)


def load_all(raw_dir: str, cache_path: str) -> dict[str, Scenario]:
    """Все участки, готовые к планированию."""
    return {key: load_scenario(key, raw_dir, cache_path) for key in REGIONS}

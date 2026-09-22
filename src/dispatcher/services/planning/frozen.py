"""Начатое при перепланировании: префиксы маршрутов, которые нельзя трогать.

Бригада доделывает начатые визиты в прежнем порядке, а к остальным
выезжает не раньше момента события - о них она узнаёт только тогда.
"""
from __future__ import annotations

from ortools.constraint_solver import pywrapcp

from dispatcher.domain import Engineer, Order


def pin_prefixes(routing: pywrapcp.RoutingModel,
                 manager: pywrapcp.RoutingIndexManager,
                 time_dim: pywrapcp.RoutingDimension,
                 orders: list[Order], engineers: list[Engineer],
                 frozen: dict[str, list[str]]) -> None:
    """Закрепляет начатые визиты за их бригадами в прежнем порядке."""
    order_index = {o.id: i for i, o in enumerate(orders)}
    for engineer_id, prefix in frozen.items():
        found = next((v for v, e in enumerate(engineers) if e.id == engineer_id), None)
        if found is None:
            continue
        vehicle_id = found
        chain = [order_index[oid] for oid in prefix if oid in order_index]
        prev_index = routing.Start(vehicle_id)
        for node in chain:
            index = manager.NodeToIndex(node)
            routing.solver().Add(routing.NextVar(prev_index) == index)
            routing.VehicleVar(index).SetValue(vehicle_id)
            prev_index = index

    hold_until_event(routing, manager, time_dim, orders, engineers, frozen)


def hold_until_event(routing: pywrapcp.RoutingModel,
                     manager: pywrapcp.RoutingIndexManager,
                     time_dim: pywrapcp.RoutingDimension,
                     orders: list[Order], engineers: list[Engineer],
                     frozen: dict[str, list[str]]) -> None:
    """К новому заданию бригада выезжает не раньше события.

    Выезд считается от последнего начатого визита, а если начатого нет - от
    начала маршрута. Исключение - заявка, к которой бригада уже едет по
    прежнему плану. То же правило действует в построителе маршрута, иначе
    решатель и пересчёт разойдутся и маршрут обрежется.
    """
    order_index = {o.id: i for i, o in enumerate(orders)}
    solver = routing.solver()
    for vehicle_id, engineer in enumerate(engineers):
        if not engineer.resume_at:
            continue
        chain = [order_index[oid] for oid in frozen.get(engineer.id, [])
                 if oid in order_index]
        prev_index = (manager.NodeToIndex(chain[-1]) if chain
                      else routing.Start(vehicle_id))
        service = orders[chain[-1]].duration_min if chain else 0
        departure = time_dim.CumulVar(prev_index) + service + time_dim.SlackVar(prev_index)
        heading = order_index.get(engineer.en_route_to)
        if heading is None:
            solver.Add(departure >= engineer.resume_at)
            continue
        # Если следующей осталась та же заявка, бригада просто едет дальше.
        same = solver.IsEqualCstVar(routing.NextVar(prev_index),
                                    manager.NodeToIndex(heading))
        solver.Add(departure >= engineer.resume_at * (1 - same))

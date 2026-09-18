"""Оборудование заявки: что бригада везёт клиенту."""
from dispatcher.domain.equipment import ROUTER, SPEAKER, TV_BOX, equipment_for


def test_type_of_work_names_the_device():
    """Там, где тип работ называет устройство, оно и едет."""
    assert equipment_for("Локальная заявка",
                         "Роутер. Замена техническим специалистом", "1") == [ROUTER]
    assert equipment_for("Локальная заявка",
                         "ТВ. Замена приставки техником", "2") == [TV_BOX]
    assert equipment_for("Локальная заявка",
                         "TVE/ENT. Замена приставки техником", "3") == [TV_BOX]


def test_repair_without_equipment_carries_nothing():
    """Диагностика и ремонт линии оборудования не требуют."""
    assert equipment_for("Локальная заявка", "Нет линка", "4") == []
    assert equipment_for("Глобальная проблема", "Авария", "5") == []


def test_connection_gets_synthetic_set():
    """У подключений набор достраивается: в выгрузке его нет."""
    sets = [equipment_for("Подключение", "Конвергенция абонента", str(i))
            for i in range(200)]
    assert any(ROUTER in s for s in sets)
    assert any(TV_BOX in s for s in sets)
    assert any(SPEAKER in s for s in sets)
    # Не у всех: опцию заказывает не каждый клиент.
    assert any(s == [] for s in sets)


def test_same_order_always_gets_the_same_set():
    """План воспроизводим: одна и та же заявка везёт одно и то же."""
    first = equipment_for("Подключение", "Конвергенция абонента", "74198")
    again = equipment_for("Подключение", "Конвергенция абонента", "74198")
    assert first == again

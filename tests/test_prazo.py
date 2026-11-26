from datetime import date
import pytest
from src.prazo import calcular_prazo

@pytest.mark.parametrize(
    "apresentado_em, esperado",
    [
        (date(2025, 4, 2), date(2026, 12, 31)),
        (date(2025, 4, 3), date(2027, 12, 31)),
        (date(2025, 1, 1), date(2026, 12, 31)),
        (date(2024, 2, 29), date(2025, 12, 31)),
        (date(2025, 12, 31), date(2027, 12, 31)),
        (date(2025, 4, 1), date(2026, 12, 31)),
    ],
)
def test_calcular_prazo(apresentado_em, esperado):
    assert calcular_prazo(apresentado_em) == esperado
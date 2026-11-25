from datetime import date

CORTE_APRESENTACAO = (4, 2)

def calcular_prazo(apresentado_em: date) -> date:
    """Devolve a data-limite de pagamento para a data de apresentação dada."""
    if (apresentado_em.month, apresentado_em.day) <= CORTE_APRESENTACAO:
        return date(apresentado_em.year + 1, 12, 31)

    return date(apresentado_em.year + 2, 12, 31)

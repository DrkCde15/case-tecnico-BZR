
from datetime import datetime
from typing import Any
from src.norm import normalizar_processo, converter_valor, converter_data

def validar_evento(evento: dict[str, Any]) -> tuple[dict | None, list[str]]:
    """
    Valida e normaliza um evento de pagamento.

    Retorna:
        (evento_normalizado, problemas)

    Se houver problemas, o evento não será importável.
    """

    problemas = []
    ajustes = []

    if not isinstance(evento, dict):
        return None, ["Registro não é um objeto JSON."]

    evento_id = evento.get("evento_id")

    if not isinstance(evento_id, str) or not evento_id.strip():
        problemas.append("evento_id ausente ou inválido.")

    processo_original = evento.get("processo")
    processo = normalizar_processo(processo_original)

    if processo is None:
        problemas.append("Número do processo ausente ou inválido.")
    elif processo != processo_original:
        ajustes.append("Número do processo normalizado.")

    valor_original = evento.get("valor")
    valor = converter_valor(valor_original)

    if valor is None:
        problemas.append("Valor ausente ou inválido.")
    elif valor <= 0:
        problemas.append("Valor deve ser positivo para um pagamento.")
    elif valor != valor_original:
        ajustes.append("Valor convertido para formato decimal.")

    data_original = evento.get("data_pagamento")
    data_pagamento = converter_data(data_original)

    if data_pagamento is None:
        problemas.append("Data de pagamento ausente ou inválida.")
    elif str(data_pagamento) != str(data_original):
        ajustes.append("Data de pagamento normalizada.")

    tipo = evento.get("tipo")

    if tipo != "pagamento":
        problemas.append(
            f"Tipo '{tipo}' não documentado como evento importável. "
            "Confirmar tratamento com o tribunal."
        )

    atualizado_em = evento.get("atualizado_em")

    if not isinstance(atualizado_em, str) or not atualizado_em.strip():
        problemas.append("Campo atualizado_em ausente ou inválido.")
    else:
        try:
            datetime.fromisoformat(
                atualizado_em.replace("Z", "+00:00")
            )
        except ValueError:
            problemas.append("Campo atualizado_em não contém timestamp válido.")

    if problemas:
        return None, problemas

    normalizado = {
        "evento_id": evento_id.strip(),
        "processo": processo,
        "valor": valor,
        "data_pagamento": data_pagamento,
        "tipo": "pagamento",
        "atualizado_em": atualizado_em.strip(),
    }

    return {
        "evento": normalizado,
        "ajustes": ajustes,
    }, []


def classificar_eventos(eventos: list[dict]) -> dict:
    """
    Classifica os eventos em:
    - importaveis
    - corrigidos
    - aprovados_sem_alteracao
    - descartados
    - pendentes
    """

    resultado = {
        "importaveis": [],
        "corrigidos": [],
        "aprovados_sem_alteracao": [],
        "descartados": [],
        "pendentes": [],
    }

    grupos = {}

    # Agrupa os registros pelo identificador do evento.
    for indice, evento in enumerate(eventos):
        if not isinstance(evento, dict):
            resultado["pendentes"].append({
                "indice": indice,
                "registro": evento,
                "motivos": ["Registro não é um objeto JSON."]
            })
            continue

        evento_id = evento.get("evento_id")

        if not isinstance(evento_id, str) or not evento_id.strip():
            resultado["pendentes"].append({
                "indice": indice,
                "registro": evento,
                "motivos": ["evento_id ausente ou inválido."]
            })
            continue

        grupos.setdefault(evento_id.strip(), []).append(
            (indice, evento)
        )

    for evento_id, registros in grupos.items():

        # Identifica eventos com mesmo ID e conteúdo divergente.
        conteudos = [registro for _, registro in registros]

        if len(registros) > 1:
            primeiro = conteudos[0]

            sao_identicos = all(
                registro == primeiro
                for registro in conteudos[1:]
            )

            if sao_identicos:
                # Mantém uma ocorrência e descarta as repetições.
                for indice, registro in registros[1:]:
                    resultado["descartados"].append({
                        "indice": indice,
                        "evento_id": evento_id,
                        "registro": registro,
                        "motivo": "Duplicata idêntica de outro registro."
                    })

                registros = registros[:1]

            else:
                for indice, registro in registros:
                    resultado["pendentes"].append({
                        "indice": indice,
                        "evento_id": evento_id,
                        "registro": registro,
                        "motivos": [
                            "Mesmo evento_id encontrado com conteúdos diferentes.",
                            "Necessária confirmação da versão correta com o tribunal."
                        ]
                    })

                continue

        indice, registro = registros[0]

        validacao, problemas = validar_evento(registro)

        if problemas:
            resultado["pendentes"].append({
                "indice": indice,
                "evento_id": evento_id,
                "registro": registro,
                "motivos": problemas
            })
            continue

        evento_normalizado = validacao["evento"]
        ajustes = validacao["ajustes"]

        resultado["importaveis"].append(evento_normalizado)

        if ajustes:
            resultado["corrigidos"].append({
                "indice": indice,
                "evento_id": evento_id,
                "original": registro,
                "normalizado": evento_normalizado,
                "ajustes": ajustes
            })
        else:
            resultado["aprovados_sem_alteracao"].append({
                "indice": indice,
                "evento_id": evento_id
            })

    return resultado

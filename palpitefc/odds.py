"""Tira a margem da casa da odd, para comparar chance com chance.

A soma de 1/odd passa de 100%: a diferença é a margem. O método de Shin
(1993) supõe que parte do dinheiro vem de quem sabe mais, e por isso corta
mais da zebra do que do favorito. É o padrão em penaltyblog e no pacote
`implied` do R. A divisão proporcional fica como reserva.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq

MERCADOS = ("casa", "empate", "fora")


def margem(odds: dict[str, float | None]) -> float | None:
    if not _completas(odds):
        return None
    return sum(1.0 / odds[mercado] for mercado in MERCADOS) - 1.0


def proporcional(odds: dict[str, float | None]) -> dict[str, float] | None:
    if not _completas(odds):
        return None
    brutas = {mercado: 1.0 / odds[mercado] for mercado in MERCADOS}
    total = sum(brutas.values())
    return {mercado: valor / total for mercado, valor in brutas.items()}


def shin(odds: dict[str, float | None]) -> dict[str, float] | None:
    if not _completas(odds):
        return None
    brutas = [1.0 / odds[mercado] for mercado in MERCADOS]
    total = sum(brutas)
    if total <= 1.0:
        return proporcional(odds)

    def chances(z: float) -> list[float]:
        return [
            (math.sqrt(z * z + 4 * (1 - z) * bruta * bruta / total) - z) / (2 * (1 - z))
            for bruta in brutas
        ]

    try:
        z = brentq(lambda z: sum(chances(z)) - 1.0, 0.0, 0.4)
    except ValueError:
        return proporcional(odds)
    resultado = chances(z)
    soma = sum(resultado)
    return {mercado: valor / soma for mercado, valor in zip(MERCADOS, resultado)}


def _completas(odds: dict[str, float | None] | None) -> bool:
    return bool(odds) and all((odds.get(mercado) or 0) > 1.0 for mercado in MERCADOS)

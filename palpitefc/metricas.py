"""Notas de previsão para o 1X2. Quanto menor, melhor.

RPS (Epstein, 1969; Constantinou e Fenton, 2012) é a nota mais usada no
futebol porque leva a ordem em conta: dar 60% ao empate num jogo que a casa
venceu erra menos do que dar 60% ao visitante. Brier e log loss completam.
"""

from __future__ import annotations

import math

MERCADOS = ("casa", "empate", "fora")
CHANCE_MINIMA = 1e-6


def rps(chance: dict[str, float], real: str) -> float:
    acumulada = 0.0
    observada = 0.0
    total = 0.0
    for mercado in MERCADOS[:-1]:
        acumulada += chance[mercado]
        observada += 1.0 if mercado == real else 0.0
        total += (acumulada - observada) ** 2
    return total / (len(MERCADOS) - 1)


def brier(chance: dict[str, float], real: str) -> float:
    return sum((chance[mercado] - (1.0 if mercado == real else 0.0)) ** 2 for mercado in MERCADOS)


def log_loss(chance: dict[str, float], real: str) -> float:
    return -math.log(max(chance[real], CHANCE_MINIMA))


def notas(chance: dict[str, float], real: str) -> dict[str, float]:
    return {"rps": rps(chance, real), "brier": brier(chance, real), "logLoss": log_loss(chance, real)}


def media_das_notas(lista: list[dict[str, float]]) -> dict[str, float] | None:
    if not lista:
        return None
    return {chave: sum(item[chave] for item in lista) / len(lista) for chave in ("rps", "brier", "logLoss")}


def calibracao(pares: list[tuple[float, bool]], faixas: int = 10) -> list[dict]:
    """Agrupa (chance prevista, aconteceu?) em faixas de 10 pontos."""
    grupos: list[list[tuple[float, bool]]] = [[] for _ in range(faixas)]
    for chance, aconteceu in pares:
        posicao = min(int(chance * faixas), faixas - 1)
        grupos[posicao].append((chance, aconteceu))
    linhas = []
    for posicao, grupo in enumerate(grupos):
        if not grupo:
            continue
        linhas.append(
            {
                "de": posicao / faixas,
                "ate": (posicao + 1) / faixas,
                "prevista": sum(chance for chance, _ in grupo) / len(grupo),
                "observada": sum(1 for _, aconteceu in grupo if aconteceu) / len(grupo),
                "casos": len(grupo),
            }
        )
    return linhas

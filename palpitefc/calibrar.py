"""Escolhe o decaimento (xi) e a regularização (l2) pelo menor RPS.

A busca usa temporadas passadas, jogo a jogo e sem olhar o resultado à
frente. A temporada atual fica de fora da escolha e serve só de prova, para
o número publicado não ser ajustado em cima dele mesmo.

    python -m palpitefc.calibrar
"""

from __future__ import annotations

import itertools
import json
from concurrent.futures import ProcessPoolExecutor

from palpitefc.dados import carregar
from palpitefc.metricas import media_das_notas
from palpitefc.model import L2_PADRAO, XI_DECAIMENTO
from palpitefc.retrospectiva import prever_temporada

TEMPORADAS_DE_ESCOLHA = ("2024", "2025")
TEMPORADA_DE_PROVA = "2026"
GRADE_XI = (0.001, 0.0015, 0.002, 0.003, 0.004, 0.006)
GRADE_L2 = (0.0, 2.0, 5.0, 10.0, 20.0)


def _avaliar(argumentos: tuple[float, float, tuple[str, ...]]) -> dict:
    xi, l2, temporadas = argumentos
    jogos = carregar()
    cartoes = []
    for temporada in temporadas:
        cartoes += prever_temporada(jogos, temporada, xi=xi, l2=l2, por_dia=True)
    media = media_das_notas([cartao["notas"]["modelo"] for cartao in cartoes])
    mercado = media_das_notas([cartao["notas"]["mercado"] for cartao in cartoes if cartao["notas"]["mercado"]])
    return {"xi": xi, "l2": l2, "jogos": len(cartoes), **media, "rpsMercado": mercado["rps"] if mercado else None}


def buscar() -> dict:
    combinacoes = [(xi, l2, TEMPORADAS_DE_ESCOLHA) for xi, l2 in itertools.product(GRADE_XI, GRADE_L2)]
    with ProcessPoolExecutor() as executor:
        linhas = list(executor.map(_avaliar, combinacoes))
    linhas.sort(key=lambda linha: linha["rps"])
    melhor = linhas[0]
    with ProcessPoolExecutor() as executor:
        prova_melhor, prova_atual = executor.map(
            _avaliar,
            [
                (melhor["xi"], melhor["l2"], (TEMPORADA_DE_PROVA,)),
                (XI_DECAIMENTO, L2_PADRAO, (TEMPORADA_DE_PROVA,)),
            ],
        )
    return {"escolha": linhas, "melhor": melhor, "prova": {"melhor": prova_melhor, "atual": prova_atual}}


if __name__ == "__main__":
    resultado = buscar()
    print(f"{'xi':>7} {'l2':>5} {'jogos':>5} {'RPS':>7} {'Brier':>7} {'LogLoss':>8} {'RPS odd':>8}")
    for linha in resultado["escolha"]:
        print(
            f"{linha['xi']:>7} {linha['l2']:>5} {linha['jogos']:>5} {linha['rps']:.5f} "
            f"{linha['brier']:.5f} {linha['logLoss']:.5f} {linha['rpsMercado'] or 0:.5f}"
        )
    print("prova", TEMPORADA_DE_PROVA, json.dumps(resultado["prova"], indent=2))

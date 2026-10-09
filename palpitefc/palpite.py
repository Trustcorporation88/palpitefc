"""Transforma a tabela de placares num cartão de sugestão.

O palpite em destaque só existe quando a chance do modelo, aplicada na odd
média da casa, tem retorno esperado positivo. Sem odd, o cartão mostra a
chance e não recomenda aposta.
"""

from __future__ import annotations

from palpitefc.dados import nome_publico
from palpitefc.model import Modelo, mercados, placares_provaveis

RETORNO_MINIMO = 0.03


def _retorno(chance: float, odd: float | None) -> float | None:
    if odd is None or odd <= 1.01:
        return None
    return chance * odd - 1.0


def avaliar(modelo: Modelo, casa: str, fora: str, odds: dict[str, float | None] | None = None) -> dict:
    grade = modelo.tabela(casa, fora)
    chance = mercados(grade)
    lam, mu = modelo.gols_esperados(casa, fora)
    odds = odds or {}
    opcoes = []
    for mercado, chave_odd in (("casa", "casa"), ("empate", "empate"), ("fora", "fora")):
        retorno = _retorno(chance[mercado], odds.get(chave_odd))
        if retorno is None:
            continue
        opcoes.append(
            {
                "mercado": mercado,
                "chance": chance[mercado],
                "odd": odds[chave_odd],
                "retorno": retorno,
            }
        )

    palpite = None
    if opcoes:
        melhor = max(opcoes, key=lambda item: item["retorno"])
        if melhor["retorno"] >= RETORNO_MINIMO:
            palpite = melhor

    ordem = ("casa", "empate", "fora")
    mais_provavel = max(ordem, key=lambda mercado: chance[mercado])
    return {
        "casa": casa,
        "fora": fora,
        "casaNome": nome_publico(casa),
        "foraNome": nome_publico(fora),
        "golsEsperados": {"casa": round(lam, 2), "fora": round(mu, 2)},
        "chance": {chave: chance[chave] for chave in (*ordem, "ambos", "mais15", "mais25", "mais35")},
        "placares": placares_provaveis(grade),
        "maisProvavel": mais_provavel,
        "odds": {
            "casa": odds.get("casa"),
            "empate": odds.get("empate"),
            "fora": odds.get("fora"),
        },
        "palpite": palpite,
    }

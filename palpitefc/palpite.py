"""Transforma a tabela de placares no cartão de um jogo.

Com odd, o cartão traz também a chance da casa de aposta sem a margem, para
comparar chance com chance. A "vantagem" (chance do modelo vezes a odd média
acima de 3%) só é calculada para a conferência histórica: em 2026 ela perdeu
dinheiro, e o site não a mostra como palpite.
"""

from __future__ import annotations

from palpitefc.dados import nome_publico
from palpitefc.model import Modelo, mercados, placares_provaveis
from palpitefc.odds import margem, shin

RETORNO_MINIMO = 0.03
GRADE_EXIBIDA = 6


def _retorno(chance: float, odd: float | None) -> float | None:
    if odd is None or odd <= 1.01:
        return None
    return chance * odd - 1.0


def avaliar(
    modelo: Modelo,
    casa: str,
    fora: str,
    odds: dict[str, float | None] | None = None,
    marcar_vantagem: bool = False,
    incluir_grade: bool = False,
) -> dict:
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
    if marcar_vantagem and opcoes:
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
        "mercado": shin(odds),
        "margem": margem(odds),
        "palpite": palpite,
        **({"grade": _grade_exibida(grade)} if incluir_grade else {}),
    }


def _grade_exibida(grade) -> list[list[float]]:
    """Placares de 0 a 5 gols para cada lado. O resto fica de fora da figura."""
    return [[float(grade[i, j]) for j in range(GRADE_EXIBIDA)] for i in range(GRADE_EXIBIDA)]

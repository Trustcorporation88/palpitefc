"""Confere o modelo jogo a jogo, sem usar o resultado que ainda não existia."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from palpitefc.dados import PASTA, carregar, para_ajuste
from palpitefc.model import XI_DECAIMENTO, ajustar
from palpitefc.palpite import avaliar

ARQUIVO = PASTA / "retrospectiva.json"
JANELA = timedelta(days=900)


def _resumo(avaliacoes: list[dict]) -> dict:
    com_resultado = [item for item in avaliacoes if item["resultado"]]
    acertos = sum(1 for item in com_resultado if item["acertouMaisProvavel"])
    palpites = [item for item in com_resultado if item["palpite"]]
    acertos_palpite = sum(1 for item in palpites if item["palpiteAcertou"])
    lucro = 0.0
    for item in palpites:
        if item["palpiteAcertou"]:
            lucro += item["palpite"]["odd"] - 1.0
        else:
            lucro -= 1.0

    favoritos = [item for item in com_resultado if item["favoritoOdd"]]
    acertos_favorito = sum(1 for item in favoritos if item["favoritoAcertou"])
    lucro_favorito = 0.0
    for item in favoritos:
        if item["favoritoAcertou"]:
            lucro_favorito += item["favoritoOddValor"] - 1.0
        else:
            lucro_favorito -= 1.0

    return {
        "jogos": len(com_resultado),
        "acertosMaisProvavel": acertos,
        "taxaMaisProvavel": acertos / len(com_resultado) if com_resultado else 0.0,
        "palpites": len(palpites),
        "acertosPalpite": acertos_palpite,
        "taxaPalpite": acertos_palpite / len(palpites) if palpites else 0.0,
        "lucroPalpite": lucro,
        "favoritos": len(favoritos),
        "acertosFavorito": acertos_favorito,
        "taxaFavorito": acertos_favorito / len(favoritos) if favoritos else 0.0,
        "lucroFavorito": lucro_favorito,
    }


def construir(temporada: str = "2026") -> dict:
    jogos = carregar()
    modelos: dict[datetime, object] = {}
    avaliacoes = []

    for jogo in jogos:
        if jogo["temporada"] != temporada or jogo["gols_casa"] is None:
            continue
        historico = [
            anterior
            for anterior in jogos
            if anterior["gols_casa"] is not None
            and anterior["quando"] < jogo["quando"]
            and jogo["quando"] - anterior["quando"] <= JANELA
        ]
        base = para_ajuste(historico, jogo["quando"])
        times_vistos = {item["casa"] for item in base} | {item["fora"] for item in base}
        if jogo["casa"] not in times_vistos or jogo["fora"] not in times_vistos:
            continue
        if len(base) < 80:
            continue

        if jogo["quando"] not in modelos:
            modelos[jogo["quando"]] = ajustar(base, XI_DECAIMENTO)
        cartao = avaliar(
            modelos[jogo["quando"]],
            jogo["casa"],
            jogo["fora"],
            {
                "casa": jogo["odd_casa"],
                "empate": jogo["odd_empate"],
                "fora": jogo["odd_fora"],
            },
        )
        real = (
            "casa"
            if jogo["gols_casa"] > jogo["gols_fora"]
            else "fora"
            if jogo["gols_casa"] < jogo["gols_fora"]
            else "empate"
        )
        palpite = cartao["palpite"]
        odds = cartao["odds"]
        favorito = None
        if all(odds.values()):
            favorito = min(("casa", "empate", "fora"), key=lambda mercado: odds[mercado])
        cartao["quando"] = jogo["quando"].isoformat(timespec="minutes")
        cartao["resultado"] = {
            "casa": jogo["gols_casa"],
            "fora": jogo["gols_fora"],
            "mercado": real,
        }
        cartao["acertouMaisProvavel"] = cartao["maisProvavel"] == real
        cartao["palpiteAcertou"] = palpite["mercado"] == real if palpite else None
        cartao["favoritoOdd"] = favorito
        cartao["favoritoOddValor"] = odds[favorito] if favorito else None
        cartao["favoritoAcertou"] = favorito == real if favorito else None
        avaliacoes.append(cartao)

    return {
        "temporada": temporada,
        "geradoEm": datetime.now().isoformat(timespec="seconds"),
        "resumo": _resumo(avaliacoes),
        "jogos": avaliacoes,
    }


def salvar(destino: Path = ARQUIVO) -> dict:
    retrospectiva = construir()
    destino.write_text(json.dumps(retrospectiva), encoding="utf-8")
    return retrospectiva["resumo"]


if __name__ == "__main__":
    print(salvar())

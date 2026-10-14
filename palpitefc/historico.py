"""Forma recente e confronto direto, só com os jogos da Série A do arquivo.

O football-data só traz a Série A (desde 2012). A forma de quem acabou de
subir conta os últimos jogos dele na Série A, que podem ser antigos, e o
confronto direto fica curto para quem passou anos fora.
"""

from __future__ import annotations

from palpitefc.dados import nome_publico

JOGOS_DA_FORMA = 5
ULTIMOS_DO_CONFRONTO = 5


def resultado_para(jogo: dict, time: str) -> str:
    """V, E ou D do ponto de vista de `time`."""
    feitos, sofridos = (jogo["gols_casa"], jogo["gols_fora"]) if jogo["casa"] == time else (jogo["gols_fora"], jogo["gols_casa"])
    if feitos > sofridos:
        return "V"
    if feitos < sofridos:
        return "D"
    return "E"


def _jogados(jogos: list[dict]) -> list[dict]:
    return [jogo for jogo in jogos if jogo["gols_casa"] is not None]


def forma(jogos: list[dict], time: str, quantos: int = JOGOS_DA_FORMA, temporadas=None) -> list[dict]:
    """Os últimos jogos de `time`, do mais recente para o mais antigo.

    Com `temporadas`, só contam os jogos delas: o time que volta à Série A
    depois de anos não mostra como forma de hoje as derrotas de 2021.
    """
    do_time = [
        jogo
        for jogo in _jogados(jogos)
        if time in (jogo["casa"], jogo["fora"]) and (temporadas is None or jogo["temporada"] in temporadas)
    ]
    linhas = []
    for jogo in reversed(do_time[-quantos:]):
        em_casa = jogo["casa"] == time
        adversario = jogo["fora"] if em_casa else jogo["casa"]
        linhas.append(
            {
                "quando": jogo["quando"].isoformat(timespec="minutes"),
                "temporada": jogo["temporada"],
                "adversario": adversario,
                "adversarioNome": nome_publico(adversario),
                "mando": "casa" if em_casa else "fora",
                "golsPro": jogo["gols_casa"] if em_casa else jogo["gols_fora"],
                "golsContra": jogo["gols_fora"] if em_casa else jogo["gols_casa"],
                "resultado": resultado_para(jogo, time),
            }
        )
    return linhas


def confronto(jogos: list[dict], time_a: str, time_b: str, ultimos: int = ULTIMOS_DO_CONFRONTO) -> dict:
    """Todos os jogos entre os dois na Série A do arquivo, com os mais recentes."""
    entre = [jogo for jogo in _jogados(jogos) if {jogo["casa"], jogo["fora"]} == {time_a, time_b}]
    vitorias = {time_a: 0, time_b: 0}
    gols = {time_a: 0, time_b: 0}
    empates = 0
    for jogo in entre:
        resultado = resultado_para(jogo, time_a)
        if resultado == "V":
            vitorias[time_a] += 1
        elif resultado == "D":
            vitorias[time_b] += 1
        else:
            empates += 1
        gols[jogo["casa"]] += jogo["gols_casa"]
        gols[jogo["fora"]] += jogo["gols_fora"]
    return {
        "jogos": len(entre),
        "desde": min((jogo["temporada"] for jogo in entre), default=None),
        "inicioDaBase": min((jogo["temporada"] for jogo in jogos), default=None),
        "vitorias": vitorias,
        "empates": empates,
        "gols": gols,
        "ultimos": [
            {
                "quando": jogo["quando"].isoformat(timespec="minutes"),
                "casa": jogo["casa"],
                "fora": jogo["fora"],
                "casaNome": nome_publico(jogo["casa"]),
                "foraNome": nome_publico(jogo["fora"]),
                "golsCasa": jogo["gols_casa"],
                "golsFora": jogo["gols_fora"],
            }
            for jogo in reversed(entre[-ultimos:])
        ],
    }

"""Junta o modelo, a última rodada e os confrontos que ainda faltam."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from palpitefc.dados import carregar, nome_publico, para_ajuste
from palpitefc.model import XI_DECAIMENTO, ajustar
from palpitefc.palpite import avaliar
from palpitefc.retrospectiva import ARQUIVO as RETRO_ARQUIVO
from palpitefc.retrospectiva import JANELA

INTERVALO_RODADA = timedelta(hours=36)


class Painel:
    def __init__(self) -> None:
        self.jogos = carregar()
        self.retro = json.loads(RETRO_ARQUIVO.read_text(encoding="utf-8"))
        ultimo = max(jogo["quando"] for jogo in self.jogos if jogo["gols_casa"] is not None)
        agora = ultimo + timedelta(minutes=1)
        historico = [
            jogo
            for jogo in self.jogos
            if jogo["gols_casa"] is not None and agora - jogo["quando"] <= JANELA
        ]
        self.modelo = ajustar(para_ajuste(historico, agora), XI_DECAIMENTO)
        self.times_2026 = sorted(
            {jogo["casa"] for jogo in self.jogos if jogo["temporada"] == "2026"}
            | {jogo["fora"] for jogo in self.jogos if jogo["temporada"] == "2026"}
        )
        feitos = {
            (jogo["casa"], jogo["fora"])
            for jogo in self.jogos
            if jogo["temporada"] == "2026" and jogo["gols_casa"] is not None
        }
        self.restantes = [
            (casa, fora)
            for casa in self.times_2026
            for fora in self.times_2026
            if casa != fora and (casa, fora) not in feitos and casa in self.modelo.ataque and fora in self.modelo.ataque
        ]

    def times(self) -> list[dict[str, str]]:
        return [{"id": time, "nome": nome_publico(time)} for time in self.times_2026]

    def inicio(self) -> dict:
        rodada = _ultima_rodada(self.retro["jogos"])
        return {
            "competicao": "Brasileirão Série A 2026",
            "fonte": "football-data.co.uk",
            "resumo": self.retro["resumo"],
            "rodada": rodada,
            "restantes": len(self.restantes),
            "mando": self.modelo.mando,
            "rho": self.modelo.rho,
        }

    def do_time(self, time: str) -> dict:
        if time not in self.times_2026:
            raise KeyError(time)
        jogos = [
            avaliar(self.modelo, casa, fora)
            for casa, fora in self.restantes
            if casa == time or fora == time
        ]
        jogos.sort(key=lambda jogo: (jogo["casa"] != time, -jogo["chance"]["casa"] if jogo["casa"] == time else -jogo["chance"]["fora"]))
        return {"time": time, "nome": nome_publico(time), "jogos": jogos}

    def simular(self, casa: str, fora: str) -> dict:
        if casa not in self.modelo.ataque or fora not in self.modelo.ataque or casa == fora:
            raise KeyError((casa, fora))
        return avaliar(self.modelo, casa, fora)

    def forca(self) -> list[dict]:
        linhas = []
        for time in self.times_2026:
            if time not in self.modelo.ataque:
                continue
            linhas.append(
                {
                    "id": time,
                    "nome": nome_publico(time),
                    "ataque": math.exp(self.modelo.ataque[time]) - 1,
                    "defesa": math.exp(self.modelo.defesa[time]) - 1,
                }
            )
        linhas.sort(key=lambda linha: linha["ataque"], reverse=True)
        return linhas


def _ultima_rodada(jogos: list[dict]) -> list[dict]:
    grupos: list[list[dict]] = []
    anterior: datetime | None = None
    for jogo in jogos:
        quando = datetime.fromisoformat(jogo["quando"])
        if anterior is None or quando - anterior > INTERVALO_RODADA:
            grupos.append([])
        grupos[-1].append(jogo)
        anterior = quando
    return grupos[-1] if grupos else []


_painel: Painel | None = None


def painel() -> Painel:
    global _painel
    if _painel is None:
        _painel = Painel()
    return _painel

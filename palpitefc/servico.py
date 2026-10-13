"""Junta o modelo, a tabela, a última rodada e os confrontos que ainda faltam."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from palpitefc.dados import carregar, carregar_proximos, nome_publico, para_ajuste
from palpitefc.metricas import media_das_notas
from palpitefc.model import L2_PADRAO, XI_DECAIMENTO, ajustar
from palpitefc.palpite import avaliar
from palpitefc.retrospectiva import ARQUIVO as RETRO_ARQUIVO
from palpitefc.retrospectiva import JANELA
from palpitefc.simulacao import classificacao, simular

TEMPORADA = "2026"
INTERVALO_RODADA = timedelta(hours=36)


class Painel:
    def __init__(self) -> None:
        self.jogos = carregar()
        self.retro = json.loads(RETRO_ARQUIVO.read_text(encoding="utf-8"))
        ultimo = max(jogo["quando"] for jogo in self.jogos if jogo["gols_casa"] is not None)
        self.ultimo_jogo = ultimo
        agora = ultimo + timedelta(minutes=1)
        historico = [
            jogo
            for jogo in self.jogos
            if jogo["gols_casa"] is not None and agora - jogo["quando"] <= JANELA
        ]
        self.modelo = ajustar(para_ajuste(historico, agora), XI_DECAIMENTO, L2_PADRAO)
        da_temporada = [jogo for jogo in self.jogos if jogo["temporada"] == TEMPORADA]
        self.times_2026 = sorted({jogo["casa"] for jogo in da_temporada} | {jogo["fora"] for jogo in da_temporada})
        feitos = {(jogo["casa"], jogo["fora"]) for jogo in da_temporada if jogo["gols_casa"] is not None}
        self.restantes = [
            (casa, fora)
            for casa in self.times_2026
            for fora in self.times_2026
            if casa != fora and (casa, fora) not in feitos and casa in self.modelo.ataque and fora in self.modelo.ataque
        ]
        self.classificacao = classificacao(da_temporada, self.times_2026)
        self.simulacao = simular(self.modelo, self.classificacao, self.restantes)
        self.rodadas = _rodadas(self.retro["jogos"])
        self.proximos = self._proximos(feitos)

    def _proximos(self, feitos: set[tuple[str, str]]) -> list[dict]:
        cartoes = []
        for jogo in carregar_proximos():
            par = (jogo["casa"], jogo["fora"])
            if par in feitos or jogo["casa"] not in self.modelo.ataque or jogo["fora"] not in self.modelo.ataque:
                continue
            odds = {"casa": jogo["odd_casa"], "empate": jogo["odd_empate"], "fora": jogo["odd_fora"]}
            cartao = avaliar(self.modelo, jogo["casa"], jogo["fora"], odds)
            cartao["quando"] = jogo["quando"].isoformat(timespec="minutes")
            cartao["resultado"] = None
            cartoes.append(cartao)
        return cartoes

    def times(self) -> list[dict[str, str]]:
        return [{"id": time, "nome": nome_publico(time)} for time in self.times_2026]

    def inicio(self) -> dict:
        return {
            "competicao": f"Brasileirão Série A {TEMPORADA}",
            "fonte": "football-data.co.uk",
            "atualizadoEm": self.ultimo_jogo.isoformat(timespec="minutes"),
            "resumo": _sem_calibracao(self.retro["resumo"]),
            "rodada": self.rodadas[-1] if self.rodadas else [],
            "proximos": self.proximos,
            "restantes": len(self.restantes),
            "mando": self.modelo.mando,
            "rho": self.modelo.rho,
        }

    def tabela(self) -> dict:
        return {"atualizadoEm": self.ultimo_jogo.isoformat(timespec="minutes"), **self.simulacao}

    def conta(self) -> dict:
        serie = []
        acumulado_modelo: list[dict] = []
        acumulado_mercado: list[dict] = []
        for numero, rodada in enumerate(self.rodadas, start=1):
            acumulado_modelo += [jogo["notas"]["modelo"] for jogo in rodada]
            acumulado_mercado += [jogo["notas"]["mercado"] for jogo in rodada if jogo["notas"]["mercado"]]
            serie.append(
                {
                    "bloco": numero,
                    "inicio": rodada[0]["quando"],
                    "jogos": len(rodada),
                    "modelo": media_das_notas(acumulado_modelo)["rps"],
                    "mercado": (media_das_notas(acumulado_mercado) or {}).get("rps"),
                }
            )
        return {
            "temporada": self.retro["temporada"],
            "geradoEm": self.retro["geradoEm"],
            "config": self.retro.get("config"),
            "resumo": self.retro["resumo"],
            "serie": serie,
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
        linha = next((linha for linha in self.simulacao["times"] if linha["id"] == time), None)
        return {"time": time, "nome": nome_publico(time), "tabela": linha, "jogos": jogos}

    def simular(self, casa: str, fora: str) -> dict:
        if casa not in self.modelo.ataque or fora not in self.modelo.ataque or casa == fora:
            raise KeyError((casa, fora))
        return avaliar(self.modelo, casa, fora, incluir_grade=True)

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
        linhas.sort(key=lambda linha: linha["ataque"] - linha["defesa"], reverse=True)
        return linhas


def _sem_calibracao(resumo: dict) -> dict:
    return {chave: valor for chave, valor in resumo.items() if chave != "calibracao"}


def _rodadas(jogos: list[dict]) -> list[list[dict]]:
    """Agrupa os jogos em rodadas: um intervalo de mais de 36 horas abre outra."""
    grupos: list[list[dict]] = []
    anterior: datetime | None = None
    for jogo in sorted(jogos, key=lambda item: item["quando"]):
        quando = datetime.fromisoformat(jogo["quando"])
        if anterior is None or quando - anterior > INTERVALO_RODADA:
            grupos.append([])
        grupos[-1].append(jogo)
        anterior = quando
    return grupos


_painel: Painel | None = None


def painel() -> Painel:
    global _painel
    if _painel is None:
        _painel = Painel()
    return _painel

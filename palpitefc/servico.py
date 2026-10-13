"""Junta o modelo, a tabela, a última rodada e os confrontos que ainda faltam."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta

from palpitefc.conferir_tabela import ARQUIVO as CONFERENCIA_TABELA
from palpitefc.dados import (
    TEMPORADA_ATUAL,
    carregar,
    carregar_calendario,
    carregar_proximos,
    nome_publico,
    para_ajuste,
    promovidos,
)
from palpitefc.metricas import media_das_notas
from palpitefc.model import L2_PADRAO, PROMOVIDO_PADRAO, XI_DECAIMENTO, ajustar
from palpitefc.palpite import avaliar
from palpitefc.retrospectiva import ARQUIVO as RETRO_ARQUIVO
from palpitefc.retrospectiva import JANELA
from palpitefc.simulacao import classificacao, simular

TEMPORADA = TEMPORADA_ATUAL
INTERVALO_RODADA = timedelta(hours=36)
# O openfootball dá a todos os jogos de uma rodada a data do primeiro dia.
# Jogo pendente com data prevista mais antiga que o último resultado menos
# essa folga ficou para trás: foi adiado.
FOLGA_ATRASO = timedelta(days=3)
IMPACTOS_EXIBIDOS = 10


class Painel:
    def __init__(self) -> None:
        self.jogos = carregar()
        self.retro = json.loads(RETRO_ARQUIVO.read_text(encoding="utf-8"))
        self.conferencia_tabela = (
            json.loads(CONFERENCIA_TABELA.read_text(encoding="utf-8")) if CONFERENCIA_TABELA.exists() else None
        )
        ultimo = max(jogo["quando"] for jogo in self.jogos if jogo["gols_casa"] is not None)
        self.ultimo_jogo = ultimo
        agora = ultimo + timedelta(minutes=1)
        historico = [
            jogo
            for jogo in self.jogos
            if jogo["gols_casa"] is not None and agora - jogo["quando"] <= JANELA
        ]
        self.modelo = ajustar(
            para_ajuste(historico, agora),
            XI_DECAIMENTO,
            L2_PADRAO,
            promovidos(self.jogos, TEMPORADA),
            PROMOVIDO_PADRAO,
            com_incerteza=True,
        )
        da_temporada = [jogo for jogo in self.jogos if jogo["temporada"] == TEMPORADA]
        self.times_2026 = sorted({jogo["casa"] for jogo in da_temporada} | {jogo["fora"] for jogo in da_temporada})
        feitos = {(jogo["casa"], jogo["fora"]) for jogo in da_temporada if jogo["gols_casa"] is not None}
        self.calendario = carregar_calendario()
        self.restantes = sorted(
            (
                (casa, fora)
                for casa in self.times_2026
                for fora in self.times_2026
                if casa != fora and (casa, fora) not in feitos and casa in self.modelo.ataque and fora in self.modelo.ataque
            ),
            key=self._ordem,
        )
        self.proxima_rodada = self._qual_a_proxima_rodada()
        self.classificacao = classificacao(da_temporada, self.times_2026)
        self.simulacao = simular(self.modelo, self.classificacao, self.restantes)
        for jogo in self.simulacao["impacto"]:
            jogo["agenda"] = self.agenda(jogo["casa"], jogo["fora"])
        self.rodadas = _rodadas(self.retro["jogos"])
        self.proximos = self._proximos(feitos)

    def agenda(self, casa: str, fora: str) -> dict | None:
        """Rodada e data previstas pelo calendário, quando o jogo está nele."""
        jogo = self.calendario.get((casa, fora))
        if not jogo:
            return None
        atrasado = jogo["adiado"] or date.fromisoformat(jogo["data"]) < self.ultimo_jogo.date() - FOLGA_ATRASO
        return {"rodada": jogo["rodada"], "data": jogo["data"], "hora": jogo["hora"], "atrasado": atrasado}

    def _ordem(self, par: tuple[str, str]) -> tuple:
        jogo = self.calendario.get(par)
        if not jogo:
            return ("9999-99-99", 99, *par)
        return (jogo["data"], jogo["rodada"], *par)

    def _qual_a_proxima_rodada(self) -> int | None:
        """A menor rodada com jogo pendente que não ficou para trás."""
        rodadas = [
            agenda["rodada"] for agenda in (self.agenda(*par) for par in self.restantes) if agenda and not agenda["atrasado"]
        ]
        return min(rodadas) if rodadas else None

    def _na_proxima_rodada(self, agenda: dict | None) -> bool:
        return bool(agenda) and not agenda["atrasado"] and agenda["rodada"] == self.proxima_rodada

    def _cartao(self, casa: str, fora: str, odds: dict | None = None) -> dict:
        cartao = avaliar(self.modelo, casa, fora, odds)
        cartao["agenda"] = self.agenda(casa, fora)
        return cartao

    def _proximos(self, feitos: set[tuple[str, str]]) -> list[dict]:
        """Próxima rodada e jogos atrasados.

        A data e a odd do football-data valem mais que a data prevista do
        calendário; o calendário completa os jogos que ele ainda não listou.
        """
        cartoes = []
        listados = set()
        for jogo in carregar_proximos():
            par = (jogo["casa"], jogo["fora"])
            if par in feitos or jogo["casa"] not in self.modelo.ataque or jogo["fora"] not in self.modelo.ataque:
                continue
            odds = {"casa": jogo["odd_casa"], "empate": jogo["odd_empate"], "fora": jogo["odd_fora"]}
            cartao = self._cartao(*par, odds)
            cartao["quando"] = jogo["quando"].isoformat(timespec="minutes")
            cartao["resultado"] = None
            cartoes.append(cartao)
            listados.add(par)
        for par in self.restantes:
            # Mando invertido: o football-data já listou o mesmo jogo ao contrário.
            if par in listados or (par[1], par[0]) in listados:
                continue
            agenda = self.agenda(*par)
            if not agenda or not (agenda["atrasado"] or self._na_proxima_rodada(agenda)):
                continue
            cartao = self._cartao(*par)
            cartao["resultado"] = None
            cartoes.append(cartao)

        def ordem(cartao: dict) -> tuple:
            agenda = cartao["agenda"] or {}
            sem_data = not cartao.get("quando") and agenda.get("atrasado", False)
            return (sem_data, cartao.get("quando") or agenda.get("data") or "9999", cartao["casa"])

        cartoes.sort(key=ordem)
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
            "proximaRodada": self.proxima_rodada,
            "proximos": self.proximos,
            "restantes": len(self.restantes),
            "mando": self.modelo.mando,
            "rho": self.modelo.rho,
        }

    def tabela(self) -> dict:
        impacto = self.simulacao["impacto"]
        da_proxima = [jogo for jogo in impacto if self._na_proxima_rodada(jogo["agenda"])]
        return {
            "atualizadoEm": self.ultimo_jogo.isoformat(timespec="minutes"),
            "proximaRodada": self.proxima_rodada,
            **{chave: valor for chave, valor in self.simulacao.items() if chave != "impacto"},
            "impacto": impacto[:IMPACTOS_EXIBIDOS],
            "impactoProximaRodada": da_proxima,
        }

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
            "tabela": self.conferencia_tabela,
            "simulacao": {
                "simulacoes": self.simulacao["simulacoes"],
                "variantes": self.simulacao["variantes"],
                "escalaIncerteza": self.simulacao["escalaIncerteza"],
            },
        }

    def do_time(self, time: str) -> dict:
        if time not in self.times_2026:
            raise KeyError(time)
        jogos = [self._cartao(casa, fora) for casa, fora in self.restantes if casa == time or fora == time]
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

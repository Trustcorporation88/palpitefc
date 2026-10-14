"""Junta o modelo, a tabela, a última rodada e os confrontos que ainda faltam."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta

from palpitefc.conferir_tabela import ARQUIVO as CONFERENCIA_TABELA
from palpitefc.dados import (
    TIMES_NA_SERIE_A,
    carregar,
    carregar_proximos,
    nome_publico,
    outra_leitura_da_madrugada_inglesa,
    para_ajuste,
    promovidos,
    temporada_em_exibicao,
)
from palpitefc.metricas import media_das_notas
from palpitefc.model import L2_PADRAO, PROMOVIDO_PADRAO, XI_DECAIMENTO, ajustar
from palpitefc.historico import confronto, forma
from palpitefc.palpite import avaliar
from palpitefc.retrospectiva import ARQUIVO as RETRO_ARQUIVO
from palpitefc.retrospectiva import JANELA
from palpitefc.simulacao import ZONAS_ANO, classificacao, simular
from palpitefc.texto import resumo_do_jogo

INTERVALO_RODADA = timedelta(hours=36)
# O openfootball dá a todos os jogos de uma rodada a data do primeiro dia.
# Jogo pendente com data prevista mais antiga que o último resultado menos
# essa folga ficou para trás: foi adiado.
FOLGA_ATRASO = timedelta(days=3)
IMPACTOS_EXIBIDOS = 10
# Durante os jogos a tabela é refeita a cada gol: metade das simulações basta.
SIMULACOES_AO_VIVO = 10_000


class Painel:
    def __init__(self) -> None:
        self.jogos = carregar()
        # A temporada nova só entra quando os 20 times são conhecidos.
        self.temporada, self.calendario, self.fonte_calendario = temporada_em_exibicao(self.jogos)
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
        da_temporada = [jogo for jogo in self.jogos if jogo["temporada"] == self.temporada]
        # Na primeira rodada, só o calendário conhece os 20 times.
        do_arquivo = {jogo["casa"] for jogo in da_temporada} | {jogo["fora"] for jogo in da_temporada}
        juntos = do_arquivo | {lado for par in self.calendario for lado in par}
        if len(juntos) > TIMES_NA_SERIE_A:
            # Nome traduzido errado criaria um clube a mais na tabela.
            print(f"Calendário ignorado: {len(juntos)} times somando o calendário ao arquivo")
            self.calendario, self.fonte_calendario, juntos = {}, None, do_arquivo
        self.times_temporada = sorted(juntos)
        self.modelo = ajustar(
            para_ajuste(historico, agora),
            XI_DECAIMENTO,
            L2_PADRAO,
            promovidos(self.jogos, self.temporada, self.times_temporada),
            PROMOVIDO_PADRAO,
            com_incerteza=True,
            times_extras=frozenset(self.times_temporada),
        )
        feitos = {(jogo["casa"], jogo["fora"]) for jogo in da_temporada if jogo["gols_casa"] is not None}
        self.restantes = sorted(
            (
                (casa, fora)
                for casa in self.times_temporada
                for fora in self.times_temporada
                if casa != fora and (casa, fora) not in feitos
            ),
            key=self._ordem,
        )
        self.proxima_rodada = self._qual_a_proxima_rodada()
        self.classificacao = classificacao(da_temporada, self.times_temporada)
        self.simulacao = simular(self.modelo, self.classificacao, self.restantes)
        for jogo in self.simulacao["impacto"]:
            jogo["agenda"] = self.agenda(jogo["casa"], jogo["fora"])
        self.rodadas = _rodadas(self.retro["jogos"])
        self.impacto_por_par = {(jogo["casa"], jogo["fora"]): jogo for jogo in self.simulacao["impacto"]}
        self._formas: dict[str, list[dict]] = {}
        self._confrontos: dict[frozenset, dict] = {}
        # Jogos que o football-data listou sem a hora: a hora deles não é confirmada.
        self._sem_hora_publicada: set[tuple[str, str]] = set()
        self.proximos = self._proximos(feitos)

    def forma_de(self, time: str) -> list[dict]:
        if time not in self._formas:
            # Só a temporada em exibição e a anterior contam como forma de hoje.
            temporadas = {self.temporada, str(int(self.temporada) - 1)}
            self._formas[time] = forma(self.jogos, time, temporadas=temporadas)
        return self._formas[time]

    def confronto_de(self, casa: str, fora: str) -> dict:
        chave = frozenset((casa, fora))
        if chave not in self._confrontos:
            self._confrontos[chave] = confronto(self.jogos, casa, fora)
        return self._confrontos[chave]

    def _com_contexto(self, cartao: dict) -> dict:
        """Forma dos dois times e o texto curto do jogo, só com números do site."""
        casa, fora = cartao["casa"], cartao["fora"]
        cartao["forma"] = {
            "casa": [jogo["resultado"] for jogo in self.forma_de(casa)],
            "fora": [jogo["resultado"] for jogo in self.forma_de(fora)],
        }
        cartao["texto"] = resumo_do_jogo(
            cartao, self.forma_de(casa), self.forma_de(fora), self.confronto_de(casa, fora), self.impacto_por_par.get((casa, fora))
        )
        return cartao

    def hora_confirmada(self, casa: str, fora: str, quando: str) -> str:
        """Na madrugada em que o Reino Unido atrasa o relógio, a hora inglesa
        tem duas leituras. Se o calendário, que vem na hora local, confirma a
        outra, vale a do calendário."""
        agenda = self.calendario.get((casa, fora))
        outra = outra_leitura_da_madrugada_inglesa(datetime.fromisoformat(quando))
        if not agenda or not agenda["hora"] or outra is None:
            return quando
        do_calendario = f'{agenda["data"]}T{agenda["hora"]}'
        return do_calendario if do_calendario == outra.isoformat(timespec="minutes") else quando

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
            return ("9999-99-99", "99:99", 99, *par)
        # Sem hora confirmada, o jogo vai para o fim do dia.
        return (jogo["data"], jogo["hora"] or "99:99", jogo["rodada"], *par)

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
        return self._com_contexto(cartao)

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
            cartao["quando"] = self.hora_confirmada(*par, jogo["quando"].isoformat(timespec="minutes"))
            if jogo.get("semHora"):
                self._sem_hora_publicada.add(par)
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
            # "2026-10-17T18:00": a hora do football-data e a do calendário se comparam igual.
            do_calendario = f'{agenda.get("data") or "9999-99-99"}T{agenda.get("hora") or "99:99"}'
            return (sem_data, cartao.get("quando") or do_calendario, cartao["casa"])

        cartoes.sort(key=ordem)
        return cartoes

    def times(self) -> list[dict[str, str]]:
        return [{"id": time, "nome": nome_publico(time)} for time in self.times_temporada]

    def inicio(self) -> dict:
        return {
            "competicao": f"Brasileirão Série A {self.temporada}",
            "fonteCalendario": self.fonte_calendario,
            "fonte": "football-data.co.uk",
            "atualizadoEm": self.ultimo_jogo.isoformat(timespec="minutes"),
            "resumo": _sem_calibracao(self.retro["resumo"]),
            "temporada": self.temporada,
            "rodada": [
                {**jogo, "quando": self.hora_confirmada(jogo["casa"], jogo["fora"], jogo["quando"])}
                for jogo in (self.rodadas[-1] if self.rodadas else [])
            ],
            "proximaRodada": self.proxima_rodada,
            "proximos": self.proximos,
            "restantes": len(self.restantes),
            "mando": self.modelo.mando,
            "rho": self.modelo.rho,
        }

    def inicios_pendentes(self) -> list[tuple[tuple[str, str], datetime, bool]]:
        """Quando cada jogo pendente pode começar, e se a hora está confirmada.

        A hora do football-data e a do calendário mudam em ritmos diferentes:
        quando divergem, o par vem duas vezes e as duas janelas valem. Sem
        hora, só o dia (meio-dia, com a hora não confirmada). Jogo que o
        calendário dá como adiado não abre janela pela hora antiga, e jogo
        atrasado sem data nova fica de fora.
        """
        inicios = set()
        for cartao in self.proximos:
            par = (cartao["casa"], cartao["fora"])
            jogo = self.calendario.get(par)
            if cartao.get("quando") and not (jogo and jogo["adiado"]):
                certo = par not in self._sem_hora_publicada
                inicios.add((par, datetime.fromisoformat(cartao["quando"]), certo))
        com_hora = {par for par, _, certo in inicios if certo}
        for par in self.restantes:
            agenda = self.agenda(*par)
            if not agenda or agenda["atrasado"]:
                continue
            if agenda["hora"]:
                inicios.add((par, datetime.fromisoformat(f'{agenda["data"]}T{agenda["hora"]}'), True))
            elif par not in com_hora:
                inicios.add((par, datetime.fromisoformat(f'{agenda["data"]}T12:00'), False))
        return sorted(inicios)

    def se_terminar_assim(self, placares: dict[tuple[str, str], tuple[int, int]]) -> dict | None:
        """A tabela do fim do campeonato se os jogos em andamento terminarem como estão.

        Cada jogo ao vivo entra na classificação com o placar de agora, e só o
        resto do campeonato é simulado. Não há chance de vitória do jogo em
        andamento: é o número que se usa para apostar ao vivo.
        """
        pendentes = set(self.restantes)
        validos = {par: placar for par, placar in placares.items() if par in pendentes}
        if not validos:
            return None
        terminados = [
            {"temporada": self.temporada, "casa": casa, "fora": fora, "gols_casa": gols_casa, "gols_fora": gols_fora}
            for (casa, fora), (gols_casa, gols_fora) in validos.items()
        ]
        da_temporada = [jogo for jogo in self.jogos if jogo["temporada"] == self.temporada] + terminados
        tabela = classificacao(da_temporada, self.times_temporada)
        restantes = [par for par in self.restantes if par not in validos]
        simulado = simular(self.modelo, tabela, restantes, simulacoes=SIMULACOES_AO_VIVO)
        antes = {linha["id"]: linha for linha in self.simulacao["times"]}
        return {
            "jogos": len(validos),
            "simulacoes": simulado["simulacoes"],
            "zonas": simulado["zonas"],
            "times": [
                {
                    "id": linha["id"],
                    "nome": linha["nome"],
                    "posicao": linha["posicao"],
                    "pts": linha["pts"],
                    "zonas": linha["zonas"],
                    "posicaoAntes": antes[linha["id"]]["posicao"],
                    "ptsAntes": antes[linha["id"]]["pts"],
                    "zonasAntes": antes[linha["id"]]["zonas"],
                }
                for linha in simulado["times"]
            ],
        }

    def tabela(self) -> dict:
        impacto = self.simulacao["impacto"]
        da_proxima = [jogo for jogo in impacto if self._na_proxima_rodada(jogo["agenda"])]
        return {
            "atualizadoEm": self.ultimo_jogo.isoformat(timespec="minutes"),
            "proximaRodada": self.proxima_rodada,
            "regraDasVagas": ZONAS_ANO,
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
        if time not in self.times_temporada:
            raise KeyError(time)
        jogos = [self._cartao(casa, fora) for casa, fora in self.restantes if casa == time or fora == time]
        linha = next((linha for linha in self.simulacao["times"] if linha["id"] == time), None)
        return {"time": time, "nome": nome_publico(time), "tabela": linha, "forma": self.forma_de(time), "jogos": jogos}

    def simular(self, casa: str, fora: str) -> dict:
        if casa not in self.modelo.ataque or fora not in self.modelo.ataque or casa == fora:
            raise KeyError((casa, fora))
        cartao = self._com_contexto(avaliar(self.modelo, casa, fora, incluir_grade=True))
        cartao["confronto"] = self.confronto_de(casa, fora)
        cartao["formaDetalhada"] = {"casa": self.forma_de(casa), "fora": self.forma_de(fora)}
        return cartao

    def forca(self) -> list[dict]:
        linhas = []
        for time in self.times_temporada:
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

"""Placar ao vivo da Série A, pela API da Bzzoiro (BSD), só perto dos jogos.

O servidor consulta a lista de jogos em andamento a cada 20 segundos na
janela de cada jogo (10 minutos antes do início até 2h30 depois) e enquanto
a fonte mostrar um jogo em andamento, mesmo que a janela já tenha fechado
(início atrasado, paralisação). No dia de jogo sem hora confirmada, olha a
cada 2 minutos; no resto do dia, das 11h à meia-noite, a cada 10 minutos,
para achar jogo remarcado ou fora do calendário. De madrugada, nada. Tudo
cabe na cota grátis de 7.500 consultas por dia. Quando um placar muda, a
tabela do fim do campeonato é refeita como se os jogos em andamento
terminassem assim.

O placar visto ao vivo fica só na memória, e o deploy o apagaria antes de o
arquivo de resultados trazê-lo. Por isso, ao ligar, uma consulta busca os
jogos encerrados dos últimos dias.

O token fica na variável BSD_TOKEN, só no servidor. Sem ele, nada disto roda
e o site continua como sempre. A licença da Bzzoiro permite exibir os dados
no próprio site, não repassá-los como feed: a rota /api/aovivo serve só às
páginas do PalpiteFC.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta

from palpitefc.dados import FUSO_DO_SITE, IDS_BZZOIRO, nome_publico

LIGA = 9
URL_DOS_EVENTOS = "https://sports.bzzoiro.com/api/v2/events/"
URL_AO_VIVO = f"{URL_DOS_EVENTOS}live/?league_id={LIGA}"
INTERVALO_NO_JOGO = 20
INTERVALO_SEM_HORA = 120
INTERVALO_SENTINELA = 600
HORA_DE_ACORDAR = time(11)
ANTES_DO_INICIO = timedelta(minutes=10)
DEPOIS_DO_INICIO = timedelta(minutes=150)
# O openfootball põe na rodada inteira a data do primeiro dia.
DIAS_SEM_HORA = timedelta(days=3)
# Jogo visto em andamento segue no ritmo de jogo até o apito, com este teto.
TETO_EM_CAMPO = timedelta(hours=4)
# Sem notícia da fonte por este tempo, o placar pode não ser o de agora.
SEM_NOTICIA = timedelta(minutes=3)
DIAS_RECUPERADOS = 4
ESPERA_MAXIMA = 3600
TEMPO_LIMITE = 10
FORMATO_DO_TOKEN = re.compile(r"[A-Za-z0-9_.\-]{16,256}")
STATUS_ENCERRADO = {"finished", "aet", "ft"}
STATUS_NAO_COMECOU = {"notstarted", "upcoming", "delayed"}
STATUS_ADIADO = {"postponed", "cancelled", "unresolved"}
EM_ANDAMENTO = {"ao vivo", "intervalo", "vai começar"}
ORDEM_NA_TELA = {"ao vivo": 0, "intervalo": 0, "sem atualização": 1, "encerrado": 2}


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """O urllib repassaria o cabeçalho com o token para outro endereço."""

    def redirect_request(self, *args, **kwargs):
        return None


class ErroDaFonte(Exception):
    """Falha da Bzzoiro, já sem nada do token na mensagem."""

    def __init__(self, motivo: str, esperar: float = 0.0) -> None:
        super().__init__(motivo)
        self.esperar = esperar


def ler_token() -> str | None:
    token = os.environ.get("BSD_TOKEN", "").strip()
    return token if FORMATO_DO_TOKEN.fullmatch(token) else None


def times_sem_id(times) -> list[str]:
    """Times da temporada que a tabela de ids da Bzzoiro não conhece (na virada do ano)."""
    conhecidos = set(IDS_BZZOIRO.values())
    return sorted(time for time in times if time not in conhecidos)


def _inteiro(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def rotulo_do_minuto(periodo: str | None, bruto, relativo: bool | None) -> str | None:
    """O minuto como se lê no placar: 57, 45+2, 90+3.

    A doc fala em "minutos do período atual" (relativo: o 2º tempo recomeça
    do zero), mas a fonte pode contar do apito inicial. Quem decide a leitura
    é AoVivo, que vê a sequência de minutos do jogo.
    """
    if not _inteiro(bruto) or bruto < 0 or periodo in ("halftime", "FT"):
        return None
    if periodo == "1st_half":
        return str(bruto) if bruto <= 45 else f"45+{bruto - 45}"
    if periodo == "2nd_half":
        if relativo:
            return str(45 + bruto) if bruto <= 45 else f"90+{bruto - 45}"
        return str(bruto) if bruto <= 90 else f"90+{bruto - 90}"
    return str(bruto)


def _valor_do_minuto(rotulo: str) -> int:
    return sum(int(parte) for parte in rotulo.split("+"))


def situacao(status: str, periodo: str | None) -> str:
    status = (status or "").lower()
    if status in STATUS_ENCERRADO or periodo == "FT":
        return "encerrado"
    if status in STATUS_ADIADO:
        return "adiado"
    if periodo == "halftime" or status == "halftime":
        return "intervalo"
    if status in STATUS_NAO_COMECOU:
        return "vai começar"
    return "ao vivo"


def _gols(valor) -> int | None:
    return valor if _inteiro(valor) and 0 <= valor < 100 else None


def _quando(valor) -> datetime | None:
    """O event_date (UTC) na hora de Brasília."""
    if not isinstance(valor, str):
        return None
    try:
        momento = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento.astimezone(FUSO_DO_SITE).replace(tzinfo=None) if momento.tzinfo else None


def _eventos(bruto) -> list:
    # /events/live/ devolve "events"; a lista paginada pode vir em "results".
    if not isinstance(bruto, dict):
        return []
    eventos = bruto.get("events", bruto.get("results"))
    return [evento for evento in eventos if isinstance(evento, dict)] if isinstance(eventos, list) else []


def _da_liga(evento: dict) -> bool:
    return evento.get("league_id") in (None, LIGA)


def converter(bruto: dict) -> dict[tuple[str, str], dict]:
    """Da resposta da Bzzoiro para (casa, fora) -> placar, situação e minuto bruto.

    Time que não está na tabela de ids fica de fora: melhor um jogo a menos
    do que um placar no jogo errado.
    """
    jogos = {}
    for evento in _eventos(bruto):
        casa, fora = IDS_BZZOIRO.get(evento.get("home_team_id")), IDS_BZZOIRO.get(evento.get("away_team_id"))
        if not casa or not fora or not _da_liga(evento):
            continue
        periodo = evento.get("period") if isinstance(evento.get("period"), str) else None
        estado = situacao(str(evento.get("status") or ""), periodo)
        gols_casa, gols_fora = _gols(evento.get("home_score")), _gols(evento.get("away_score"))
        prorrogacao = evento.get("extra_time_score")
        if isinstance(prorrogacao, dict) and gols_casa is not None and gols_fora is not None:
            # A fonte separa os gols da prorrogação; aqui o placar é o total.
            gols_casa += _gols(prorrogacao.get("home")) or 0
            gols_fora += _gols(prorrogacao.get("away")) or 0
        if estado in ("vai começar", "adiado"):
            # Antes do apito a fonte pode mandar 0–0, que não é placar.
            gols_casa = gols_fora = None
        elif gols_casa is None or gols_fora is None:
            continue
        jogos[(casa, fora)] = {
            "casa": casa,
            "fora": fora,
            "golsCasa": gols_casa,
            "golsFora": gols_fora,
            "situacao": estado,
            "periodo": periodo,
            "minutoBruto": evento.get("current_minute"),
            "quando": _quando(evento.get("event_date")),
        }
    return jogos


def ids_desconhecidos(bruto: dict) -> set[int]:
    """Ids de time da Série A que a tabela não conhece: o jogo deles some do ao vivo."""
    ids = set()
    for evento in _eventos(bruto):
        if _da_liga(evento):
            ids |= {
                time for time in (evento.get("home_team_id"), evento.get("away_team_id")) if _inteiro(time) and time not in IDS_BZZOIRO
            }
    return ids


def url_dos_encerrados(hoje: date) -> str:
    # Um dia a mais no fim: a data da fonte é a de UTC, à frente da de Brasília.
    return (
        f"{URL_DOS_EVENTOS}?league_id={LIGA}&status=finished"
        f"&date_from={hoje - timedelta(days=DIAS_RECUPERADOS)}&date_to={hoje + timedelta(days=1)}&limit=200"
    )


def _baixar_da_bzzoiro(token: str, url: str) -> dict:
    pedido = urllib.request.Request(
        url,
        headers={"Authorization": f"Token {token}", "User-Agent": "PalpiteFC (+https://github.com/Trustcorporation88/palpitefc)"},
    )
    abridor = urllib.request.build_opener(_SemRedirecionar)
    try:
        with abridor.open(pedido, timeout=TEMPO_LIMITE) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        esperar = 0.0
        if erro.code == 429:
            try:
                esperar = float(erro.headers.get("Retry-After", "60"))
            except ValueError:
                esperar = 60.0
        raise ErroDaFonte(f"HTTP {erro.code}", esperar) from None
    except (urllib.error.URLError, TimeoutError, OSError) as erro:
        raise ErroDaFonte(type(erro).__name__) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ErroDaFonte("resposta que não é JSON") from None


def placares(jogos: dict[tuple[str, str], dict]) -> dict[tuple[str, str], tuple[int, int]]:
    return {par: (jogo["golsCasa"], jogo["golsFora"]) for par, jogo in jogos.items() if jogo["golsCasa"] is not None}


def agora_em_brasilia() -> datetime:
    return datetime.now(FUSO_DO_SITE).replace(tzinfo=None)


def _iso(momento: datetime | None) -> str | None:
    return momento.isoformat(timespec="seconds") if momento else None


class AoVivo:
    def __init__(self, painel, token: str, baixar=None, relogio=agora_em_brasilia) -> None:
        self.painel = painel
        self._baixar = baixar or (lambda url: _baixar_da_bzzoiro(token, url))
        self._relogio = relogio
        # Os dicionários são trocados inteiros, nunca alterados no lugar: a rota
        # /api/aovivo os lê de outra thread enquanto a consulta roda.
        self.jogos: dict[tuple[str, str], dict] = {}
        # Por jogo: quando a fonte o mostrou pela primeira e pela última vez e a leitura do minuto.
        self._vistos: dict[tuple[str, str], dict] = {}
        self.tabela: dict | None = None
        self.erro: str | None = None
        self.ultima_consulta: datetime | None = None
        self.modo: str | None = None
        self.desconhecidos: frozenset[int] = frozenset()

    @property
    def consultando(self) -> bool:
        """Perto de jogo (ritmo de jogo ou dia sem hora), não na olhada de 10 em 10 minutos."""
        return self.modo in ("jogo", "dia")

    def _em_campo(self, agora: datetime) -> bool:
        return any(
            jogo["situacao"] in EM_ANDAMENTO
            and self._vistos[par]["visto"] == self.ultima_consulta
            and agora - self._vistos[par]["desde"] <= TETO_EM_CAMPO
            for par, jogo in self.jogos.items()
            if par in self._vistos
        )

    def janela(self, agora: datetime) -> tuple[str | None, float]:
        """Em que ritmo consultar agora ("jogo", "dia", "sentinela" ou nada) e quanto esperar."""
        if not self.painel.restantes:
            return None, ESPERA_MAXIMA
        if self._em_campo(agora):
            return "jogo", INTERVALO_NO_JOGO
        inicios = self.painel.inicios_pendentes()
        confirmados = [inicio for _, inicio, certo in inicios if certo]
        if any(inicio - ANTES_DO_INICIO <= agora <= inicio + DEPOIS_DO_INICIO for inicio in confirmados):
            return "jogo", INTERVALO_NO_JOGO
        proxima = min((inicio - ANTES_DO_INICIO for inicio in confirmados if inicio - ANTES_DO_INICIO > agora), default=None)
        ate_a_proxima = (proxima - agora).total_seconds() if proxima else ESPERA_MAXIMA
        if agora.time() >= HORA_DE_ACORDAR:
            sem_hora = any(not certo and inicio.date() <= agora.date() <= inicio.date() + DIAS_SEM_HORA for _, inicio, certo in inicios)
            modo, intervalo = ("dia", INTERVALO_SEM_HORA) if sem_hora else ("sentinela", INTERVALO_SENTINELA)
            return modo, max(1.0, min(intervalo, ate_a_proxima))
        acordar = (datetime.combine(agora.date(), HORA_DE_ACORDAR) - agora).total_seconds()
        return None, max(1.0, min(ate_a_proxima, acordar, ESPERA_MAXIMA))

    def _minuto(self, visto: dict, jogo: dict, agora: datetime) -> str | None:
        periodo, bruto = jogo["periodo"], jogo["minutoBruto"]
        if periodo == "2nd_half" and _inteiro(bruto):
            if bruto <= 44:
                visto["relativo"] = True
            elif visto["relativo"] is None:
                # Primeira olhada no 2º tempo já com 45 ou mais: começo do 2º tempo
                # contado do apito inicial, ou acréscimo contado do reinício. O
                # relógio desempata: no acréscimo, já se passaram mais de 90 minutos.
                visto["relativo"] = bool(jogo["quando"] and agora - jogo["quando"] >= timedelta(minutes=90))
        rotulo = rotulo_do_minuto(periodo, bruto, visto["relativo"])
        anterior = visto["minuto"]
        if rotulo and anterior and anterior[0] == periodo and _valor_do_minuto(rotulo) < _valor_do_minuto(anterior[1]):
            # O minuto não volta dentro do mesmo período.
            return anterior[1]
        if rotulo:
            visto["minuto"] = (periodo, rotulo)
        return rotulo

    def _juntar(self, novos: dict, agora: datetime, so_novos: bool = False) -> bool:
        pendentes = set(self.painel.restantes)
        # Jogo que saiu da lista ao vivo (acabou há mais de 10 minutos) fica com o
        # último placar visto até o arquivo de resultados trazê-lo.
        jogos = {par: jogo for par, jogo in self.jogos.items() if par in pendentes}
        vistos = {par: dict(visto) for par, visto in self._vistos.items() if par in pendentes}
        for par, novo in novos.items():
            if par not in pendentes or (so_novos and par in jogos):
                continue
            visto = vistos.setdefault(par, {"desde": agora, "relativo": None, "minuto": None})
            visto["visto"] = agora
            jogos[par] = {
                "casa": novo["casa"],
                "fora": novo["fora"],
                "golsCasa": novo["golsCasa"],
                "golsFora": novo["golsFora"],
                "minuto": self._minuto(visto, novo, agora) if novo["situacao"] == "ao vivo" else None,
                "situacao": novo["situacao"],
                "quando": novo["quando"],
            }
        mudou = placares(jogos) != placares(self.jogos)
        self._vistos = vistos
        self.jogos = jogos
        if mudou:
            self.tabela = self.painel.se_terminar_assim(placares(jogos))
        return mudou

    def consultar(self) -> bool:
        """Uma consulta. Devolve True quando algum placar mudou (e a tabela foi refeita)."""
        bruto = self._baixar(URL_AO_VIVO)
        agora = self._relogio()
        self.ultima_consulta = agora
        self.desconhecidos = self.desconhecidos | ids_desconhecidos(bruto)
        return self._juntar(converter(bruto), agora)

    def recuperar(self) -> bool:
        """Os jogos encerrados dos últimos dias que o arquivo de resultados ainda não trouxe."""
        agora = self._relogio()
        bruto = self._baixar(url_dos_encerrados(agora.date()))
        encerrados = {par: jogo for par, jogo in converter(bruto).items() if jogo["situacao"] == "encerrado"}
        return self._juntar(encerrados, agora, so_novos=True)

    async def rodar(self) -> None:
        try:
            await asyncio.to_thread(self.recuperar)
        except ErroDaFonte as erro:
            self.erro = str(erro)
        except Exception as erro:  # noqa: BLE001 - o placar ao vivo nunca derruba o site
            self.erro = type(erro).__name__
        while True:
            espera = INTERVALO_SENTINELA
            try:
                self.modo, espera = self.janela(self._relogio())
                if self.modo:
                    await asyncio.to_thread(self.consultar)
                    self.erro = None
            except ErroDaFonte as erro:
                self.erro = str(erro)
                espera = max(espera, erro.esperar)
            except Exception as erro:  # noqa: BLE001 - o placar ao vivo nunca derruba o site
                self.erro = type(erro).__name__
            await asyncio.sleep(espera)

    def estado(self) -> dict:
        agora = self._relogio()
        jogos, vistos = self.jogos, self._vistos
        lista = []
        for par, jogo in jogos.items():
            if jogo["golsCasa"] is None:
                continue
            visto = vistos.get(par, {}).get("visto")
            atual = jogo["situacao"]
            if atual != "encerrado" and visto and agora - visto > SEM_NOTICIA:
                # A fonte falhou ou o jogo saiu da lista sem o apito final: o
                # placar pode não ser o de agora, e a página não pode dizer "ao vivo".
                atual = "sem atualização"
            lista.append(
                {
                    **jogo,
                    "situacao": atual,
                    "minuto": jogo["minuto"] if atual == "ao vivo" else None,
                    "quando": _iso(jogo["quando"]),
                    "vistoEm": _iso(visto),
                    "casaNome": nome_publico(jogo["casa"]),
                    "foraNome": nome_publico(jogo["fora"]),
                }
            )
        lista.sort(key=lambda jogo: (ORDEM_NA_TELA.get(jogo["situacao"], 0), jogo["casa"]))
        return {
            "ativo": True,
            "consultando": self.consultando,
            "agora": _iso(agora),
            "ultimaConsulta": _iso(self.ultima_consulta),
            "erro": self.erro,
            "jogos": lista,
            "seTerminarAssim": self.tabela,
        }


DESLIGADO = {
    "ativo": False,
    "consultando": False,
    "agora": None,
    "ultimaConsulta": None,
    "erro": None,
    "jogos": [],
    "seTerminarAssim": None,
}

"""Leitura do Brasileirão publicado pelo football-data.co.uk."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# O football-data.co.uk publica a hora do Reino Unido: o jogo das 21h30 de
# Brasília aparece à 01h30 do dia seguinte. Tudo é convertido na leitura.
FUSO_DA_FONTE = ZoneInfo("Europe/London")
FUSO_DO_SITE = ZoneInfo("America/Sao_Paulo")
RODADAS = 38
_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")
_HORA = re.compile(r"\d{2}:\d{2}")
PASTA = Path(__file__).resolve().parent.parent / "data"
ARQUIVO = PASTA / "BRA.csv"
# new_league_fixtures.csv só traz os jogos dos próximos dias, com a odd de
# antes do fechamento. O football-data atualiza às terças e sextas.
ARQUIVO_PROXIMOS = PASTA / "proximos.csv"
# Tabela completa da temporada, com rodada e data prevista, do openfootball
# (domínio público). Atrasa algumas semanas; a data é só a prevista.
ARQUIVO_CALENDARIO = PASTA / "calendario.json"

# Nome no openfootball -> nome no football-data.
NOMES_OPENFOOTBALL = {
    "Botafogo FR": "Botafogo RJ",
    "CA Mineiro": "Atletico-MG",
    "CA Paranaense": "Athletico-PR",
    "CR Flamengo": "Flamengo RJ",
    "CR Vasco da Gama": "Vasco",
    "Chapecoense AF": "Chapecoense-SC",
    "Clube do Remo": "Remo",
    "Coritiba FBC": "Coritiba",
    "Cruzeiro EC": "Cruzeiro",
    "EC Bahia": "Bahia",
    "EC Vitória": "Vitoria",
    "Fluminense FC": "Fluminense",
    "Grêmio FBPA": "Gremio",
    "Mirassol FC": "Mirassol",
    "RB Bragantino": "Bragantino",
    "SC Corinthians Paulista": "Corinthians",
    "SC Internacional": "Internacional",
    "SE Palmeiras": "Palmeiras",
    "Santos FC": "Santos",
    "São Paulo FC": "Sao Paulo",
}

NOMES = {
    "Athletico-PR": "Athletico-PR",
    "Atletico-MG": "Atlético-MG",
    "Bahia": "Bahia",
    "Botafogo RJ": "Botafogo",
    "Bragantino": "Bragantino",
    "Chapecoense-SC": "Chapecoense",
    "Corinthians": "Corinthians",
    "Coritiba": "Coritiba",
    "Cruzeiro": "Cruzeiro",
    "Flamengo RJ": "Flamengo",
    "Fluminense": "Fluminense",
    "Gremio": "Grêmio",
    "Internacional": "Internacional",
    "Mirassol": "Mirassol",
    "Palmeiras": "Palmeiras",
    "Remo": "Remo",
    "Santos": "Santos",
    "Sao Paulo": "São Paulo",
    "Vasco": "Vasco",
    "Vitoria": "Vitória",
}


def nome_publico(time: str) -> str:
    return NOMES.get(time, time)


def _numero(texto: str) -> float | None:
    texto = (texto or "").strip()
    if not texto:
        return None
    return float(texto)


def _odd(linha: dict, *colunas: str) -> float | None:
    for coluna in colunas:
        valor = _numero(linha.get(coluna, ""))
        if valor and valor > 1.01:
            return valor
    return None


def hora_de_brasilia(data: str, hora: str) -> datetime:
    """Data e hora do football-data (Reino Unido) em hora de Brasília, sem fuso.

    Sem hora publicada, fica o dia publicado ao meio-dia, sem conversão:
    converter a meia-noite inglesa jogaria o jogo para a véspera.
    """
    if not hora.strip():
        return datetime.strptime(f"{data.strip()} 12:00", "%d/%m/%Y %H:%M")
    inglesa = datetime.strptime(f"{data.strip()} {hora.strip()}", "%d/%m/%Y %H:%M").replace(tzinfo=FUSO_DA_FONTE)
    return inglesa.astimezone(FUSO_DO_SITE).replace(tzinfo=None)


def carregar(caminho: Path = ARQUIVO) -> list[dict]:
    jogos: list[dict] = []
    with caminho.open(newline="", encoding="utf-8-sig") as arquivo:
        for linha in csv.DictReader(arquivo):
            quando = hora_de_brasilia(linha["Date"], linha["Time"])
            gols_casa = _numero(linha.get("HG", ""))
            gols_fora = _numero(linha.get("AG", ""))
            odd_casa = _odd(linha, "AvgCH", "MaxCH", "PSCH", "B365CH")
            odd_empate = _odd(linha, "AvgCD", "MaxCD", "PSCD", "B365CD")
            odd_fora = _odd(linha, "AvgCA", "MaxCA", "PSCA", "B365CA")
            jogos.append(
                {
                    "temporada": linha["Season"].strip(),
                    "quando": quando,
                    "casa": linha["Home"].strip(),
                    "fora": linha["Away"].strip(),
                    "gols_casa": None if gols_casa is None else int(gols_casa),
                    "gols_fora": None if gols_fora is None else int(gols_fora),
                    "odd_casa": odd_casa,
                    "odd_empate": odd_empate,
                    "odd_fora": odd_fora,
                }
            )
    jogos.sort(key=lambda jogo: jogo["quando"])
    return jogos


def carregar_proximos(caminho: Path = ARQUIVO_PROXIMOS) -> list[dict]:
    """Jogos marcados da Série A. Arquivo ausente ou sem o Brasil: lista vazia."""
    if not caminho.exists():
        return []
    jogos = []
    with caminho.open(newline="", encoding="utf-8-sig") as arquivo:
        for linha in csv.DictReader(arquivo):
            if (linha.get("Country") or "").strip() != "Brazil" or (linha.get("League") or "").strip() != "Serie A":
                continue
            jogos.append(
                {
                    "quando": hora_de_brasilia(linha["Date"], linha.get("Time") or ""),
                    "casa": linha["Home"].strip(),
                    "fora": linha["Away"].strip(),
                    "odd_casa": _odd(linha, "AvgH", "B365H", "MaxH"),
                    "odd_empate": _odd(linha, "AvgD", "B365D", "MaxD"),
                    "odd_fora": _odd(linha, "AvgA", "B365A", "MaxA"),
                }
            )
    jogos.sort(key=lambda jogo: jogo["quando"])
    return jogos


def temporada_atual(jogos: list[dict]) -> str:
    """A temporada mais recente do arquivo. Na virada do ano, o site muda sozinho."""
    return max(jogo["temporada"] for jogo in jogos)


def promovidos(jogos: list[dict], temporada: str) -> frozenset[str]:
    """Times da temporada que não estavam na Série A do ano anterior.

    A lista de participantes é pública antes do primeiro jogo, então usá-la
    não vaza resultado nenhum.
    """
    anterior = str(int(temporada) - 1)
    da_temporada = {lado for jogo in jogos if jogo["temporada"] == temporada for lado in (jogo["casa"], jogo["fora"])}
    do_ano_anterior = {lado for jogo in jogos if jogo["temporada"] == anterior for lado in (jogo["casa"], jogo["fora"])}
    if not do_ano_anterior:
        return frozenset()
    return frozenset(da_temporada - do_ano_anterior)


def validar_jogo_do_calendario(jogo: dict) -> dict:
    """Confere cada campo antes de ele chegar ao site.

    O calendário vem de um repositório de terceiros e vai para a página sem
    revisão humana: data, hora e rodada fora do formato derrubam a leitura,
    em vez de virar texto (ou script) na tela.
    """
    rodada, data, hora = jogo.get("rodada"), jogo.get("data"), jogo.get("hora")
    if not isinstance(rodada, int) or isinstance(rodada, bool) or not 1 <= rodada <= RODADAS:
        raise ValueError(f"Rodada inválida no calendário: {rodada!r}")
    if not isinstance(data, str) or not _DATA.fullmatch(data):
        raise ValueError(f"Data inválida no calendário: {data!r}")
    date.fromisoformat(data)
    if hora is not None and (not isinstance(hora, str) or not _HORA.fullmatch(hora)):
        raise ValueError(f"Hora inválida no calendário: {hora!r}")
    times = set(NOMES_OPENFOOTBALL.values())
    if jogo.get("casa") not in times or jogo.get("fora") not in times:
        raise ValueError(f"Time desconhecido no calendário: {jogo.get('casa')!r} x {jogo.get('fora')!r}")
    if not isinstance(jogo.get("adiado"), bool):
        raise ValueError("Campo 'adiado' inválido no calendário")
    return {"rodada": rodada, "data": data, "hora": hora, "casa": jogo["casa"], "fora": jogo["fora"], "adiado": jogo["adiado"]}


def converter_calendario(bruto: dict) -> list[dict]:
    """Do formato do openfootball para rodada, data e times do football-data.

    Time sem tradução derruba a conversão: é melhor falhar na atualização do
    que publicar a tabela com um confronto a menos.
    """
    jogos = []
    for jogo in bruto["matches"]:
        casa, fora = jogo["team1"], jogo["team2"]
        faltando = [nome for nome in (casa, fora) if nome not in NOMES_OPENFOOTBALL]
        if faltando:
            raise ValueError(f"Time sem tradução no calendário: {', '.join(map(str, faltando))}")
        jogos.append(
            validar_jogo_do_calendario(
                {
                    "rodada": int(str(jogo["round"]).split()[-1]),
                    "data": jogo["date"],
                    "hora": jogo.get("time"),
                    "casa": NOMES_OPENFOOTBALL[casa],
                    "fora": NOMES_OPENFOOTBALL[fora],
                    "adiado": jogo.get("status") == "postponed",
                }
            )
        )
    return jogos


def carregar_calendario(temporada: str, caminho: Path = ARQUIVO_CALENDARIO) -> tuple[dict[tuple[str, str], dict], str | None]:
    """(casa, fora) -> rodada, data e hora previstas, e a fonte do calendário.

    Sem arquivo, de outra temporada ou com campo inválido: vazio. O site
    continua sem as datas, em vez de cair.
    """
    if not caminho.exists():
        return {}, None
    try:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        if conteudo.get("temporada") != temporada:
            return {}, None
        jogos = [validar_jogo_do_calendario(jogo) for jogo in conteudo["jogos"]]
        fonte = conteudo.get("fonte", "openfootball")
        if fonte not in FONTES_DO_CALENDARIO:
            raise ValueError(f"Fonte desconhecida: {fonte!r}")
    except (ValueError, KeyError, TypeError, AttributeError) as erro:
        print(f"Calendário ignorado: {erro}")
        return {}, None
    return {(jogo["casa"], jogo["fora"]): jogo for jogo in jogos}, fonte


# football-data.org: só com chave gratuita, mas é oficial e traz a hora assim
# que a CBF confirma. Até lá o jogo fica SCHEDULED, com uma data provisória.
FONTES_DO_CALENDARIO = ("openfootball", "football-data.org")
STATUS_COM_HORA = {"TIMED", "IN_PLAY", "PAUSED", "FINISHED", "SUSPENDED", "AWARDED"}


def _normalizado(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _time_do_football_data_org(time: dict) -> str:
    nome = str(time.get("name") or "")
    if nome in NOMES_OPENFOOTBALL:
        return NOMES_OPENFOOTBALL[nome]
    procurados = {_normalizado(str(time.get(campo) or "")) for campo in ("name", "shortName")} - {""}
    for identificador, publico in NOMES.items():
        if procurados & {_normalizado(identificador), _normalizado(publico)}:
            return identificador
    raise ValueError(f"Time sem tradução no football-data.org: {nome!r}")


def converter_football_data_org(bruto: dict) -> list[dict]:
    """Do formato da API v4 do football-data.org para o calendário do site."""
    jogos = []
    for jogo in bruto["matches"]:
        status = jogo.get("status")
        utc = datetime.fromisoformat(str(jogo["utcDate"]).replace("Z", "+00:00"))
        if status in STATUS_COM_HORA:
            local = utc.astimezone(FUSO_DO_SITE)
            data, hora = local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
        else:
            # Data provisória: a hora não vale, e converter a mudaria de dia.
            data, hora = utc.strftime("%Y-%m-%d"), None
        jogos.append(
            validar_jogo_do_calendario(
                {
                    "rodada": jogo.get("matchday"),
                    "data": data,
                    "hora": hora,
                    "casa": _time_do_football_data_org(jogo["homeTeam"]),
                    "fora": _time_do_football_data_org(jogo["awayTeam"]),
                    "adiado": status == "POSTPONED",
                }
            )
        )
    return jogos


def para_ajuste(jogos: list[dict], agora: datetime) -> list[dict]:
    """Só jogos já realizados, com a idade em dias a partir de `agora`."""
    prontos = []
    for jogo in jogos:
        if jogo["gols_casa"] is None or jogo["quando"] >= agora:
            continue
        dias = max(0.0, (agora - jogo["quando"]).total_seconds() / 86400)
        prontos.append(
            {
                "casa": jogo["casa"],
                "fora": jogo["fora"],
                "gols_casa": jogo["gols_casa"],
                "gols_fora": jogo["gols_fora"],
                "dias": dias,
            }
        )
    return prontos

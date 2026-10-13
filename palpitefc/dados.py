"""Leitura do Brasileirão publicado pelo football-data.co.uk."""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from pathlib import Path

TEMPORADA_ATUAL = "2026"
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


def carregar(caminho: Path = ARQUIVO) -> list[dict]:
    jogos: list[dict] = []
    with caminho.open(newline="", encoding="utf-8-sig") as arquivo:
        for linha in csv.DictReader(arquivo):
            quando = datetime.strptime(
                f"{linha['Date'].strip()} {linha['Time'].strip() or '00:00'}",
                "%d/%m/%Y %H:%M",
            )
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
                    "quando": datetime.strptime(
                        f"{linha['Date'].strip()} {linha['Time'].strip() or '00:00'}", "%d/%m/%Y %H:%M"
                    ),
                    "casa": linha["Home"].strip(),
                    "fora": linha["Away"].strip(),
                    "odd_casa": _odd(linha, "AvgH", "B365H", "MaxH"),
                    "odd_empate": _odd(linha, "AvgD", "B365D", "MaxD"),
                    "odd_fora": _odd(linha, "AvgA", "B365A", "MaxA"),
                }
            )
    jogos.sort(key=lambda jogo: jogo["quando"])
    return jogos


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


def carregar_calendario(
    caminho: Path = ARQUIVO_CALENDARIO, temporada: str = TEMPORADA_ATUAL
) -> dict[tuple[str, str], dict]:
    """(casa, fora) -> rodada, data e hora previstas.

    Sem arquivo, de outra temporada ou com campo inválido: vazio. O site
    continua sem as datas, em vez de cair.
    """
    if not caminho.exists():
        return {}
    try:
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        if conteudo.get("temporada") != temporada:
            return {}
        jogos = [validar_jogo_do_calendario(jogo) for jogo in conteudo["jogos"]]
    except (ValueError, KeyError, TypeError, AttributeError) as erro:
        print(f"Calendário ignorado: {erro}")
        return {}
    return {(jogo["casa"], jogo["fora"]): jogo for jogo in jogos}


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

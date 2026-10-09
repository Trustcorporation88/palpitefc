"""Leitura do Brasileirão publicado pelo football-data.co.uk."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent.parent / "data"
ARQUIVO = PASTA / "BRA.csv"

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

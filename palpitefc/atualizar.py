"""Baixa os resultados e os próximos jogos do football-data, o calendário da
temporada, e refaz a conferência.

    python -m palpitefc.atualizar

O calendário vem do football-data.org quando a variável FOOTBALL_DATA_ORG_TOKEN
traz uma chave (gratuita, em football-data.org/client/register): é oficial e
tem a hora assim que a CBF confirma. Sem chave, ou se ele falhar, vem do
openfootball, que é aberto mas atrasa algumas semanas.

O arquivo novo só substitui o antigo se for lido sem erro e não tiver menos
jogos com placar. Dos próximos jogos, só a Série A é guardada, para o arquivo
não mudar quando mudam as outras ligas.
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import urllib.request
from pathlib import Path

from palpitefc.dados import (
    ARQUIVO,
    ARQUIVO_CALENDARIO,
    ARQUIVO_PROXIMOS,
    carregar,
    converter_calendario,
    converter_football_data_org,
    temporada_atual,
)
from palpitefc.retrospectiva import salvar

URL_RESULTADOS = "https://www.football-data.co.uk/new/BRA.csv"
URL_PROXIMOS = "https://www.football-data.co.uk/new_league_fixtures.csv"
URL_CALENDARIO = "https://raw.githubusercontent.com/openfootball/football.json/master/{temporada}/br.1.json"
URL_FOOTBALL_DATA_ORG = "https://api.football-data.org/v4/competitions/BSA/matches?season={temporada}"
JOGOS_MINIMOS_CALENDARIO = 300
TEMPO_LIMITE = 60
COLUNAS_PROXIMOS = {"Country", "League", "Date", "Time", "Home", "Away"}


def baixar(url: str, cabecalhos: dict[str, str] | None = None) -> bytes:
    pedido = urllib.request.Request(
        url, headers={"User-Agent": "PalpiteFC (+https://github.com/Trustcorporation88/palpitefc)", **(cabecalhos or {})}
    )
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
        return resposta.read()


def _com_placar(caminho: Path) -> int:
    return sum(1 for jogo in carregar(caminho) if jogo["gols_casa"] is not None)


def gravar_resultados(conteudo: bytes, destino: Path = ARQUIVO) -> int:
    """Confere o arquivo baixado e devolve quantos jogos novos com placar ele traz."""
    with tempfile.TemporaryDirectory() as pasta:
        provisorio = Path(pasta) / "BRA.csv"
        provisorio.write_bytes(conteudo)
        novos = _com_placar(provisorio)
    antigos = _com_placar(destino) if destino.exists() else 0
    if novos < antigos:
        raise ValueError(f"O arquivo baixado tem {novos} jogos com placar; o atual tem {antigos}")
    if not destino.exists() or destino.read_bytes() != conteudo:
        destino.write_bytes(conteudo)
    return novos - antigos


def gravar_proximos(conteudo: bytes, destino: Path = ARQUIVO_PROXIMOS) -> int:
    texto = conteudo.decode("utf-8-sig")
    leitor = csv.DictReader(io.StringIO(texto))
    faltando = COLUNAS_PROXIMOS - set(leitor.fieldnames or [])
    if faltando:
        # Resposta vazia ou página de erro no lugar do CSV: não grava nada.
        raise ValueError(f"Lista de próximos jogos sem as colunas {sorted(faltando)}")
    linhas = [
        linha
        for linha in leitor
        if (linha.get("Country") or "").strip() == "Brazil" and (linha.get("League") or "").strip() == "Serie A"
    ]
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, fieldnames=leitor.fieldnames, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(linhas)
    _gravar_se_mudou(destino, saida.getvalue())
    return len(linhas)


def calendario_openfootball(temporada: str) -> list[dict]:
    return converter_calendario(json.loads(baixar(URL_CALENDARIO.format(temporada=temporada)).decode("utf-8-sig")))


def calendario_football_data_org(temporada: str, chave: str) -> list[dict]:
    # A chave vai só no cabeçalho; a mensagem de erro do urllib não a repete.
    bruto = baixar(URL_FOOTBALL_DATA_ORG.format(temporada=temporada), {"X-Auth-Token": chave})
    return converter_football_data_org(json.loads(bruto.decode("utf-8")))


def gravar_calendario(
    jogos: list[dict], temporada: str, fonte: str = "openfootball", destino: Path = ARQUIVO_CALENDARIO
) -> int:
    if len(jogos) < JOGOS_MINIMOS_CALENDARIO:
        raise ValueError(f"Calendário com só {len(jogos)} jogos")
    # Um jogo por linha: o diff do commit mostra só o que mudou de data. A
    # temporada vai junto para o calendário velho não valer no ano seguinte.
    linhas = ",\n".join(json.dumps(jogo, ensure_ascii=False) for jogo in jogos)
    texto = f'{{"temporada": {json.dumps(temporada)}, "fonte": {json.dumps(fonte)}, "jogos": [\n{linhas}\n]}}\n'
    _gravar_se_mudou(destino, texto)
    return len(jogos)


def _gravar_se_mudou(destino: Path, texto: str) -> None:
    # Bytes com \n: o arquivo sai igual no Windows e no GitHub Actions.
    conteudo = texto.encode("utf-8")
    if not destino.exists() or destino.read_bytes() != conteudo:
        destino.write_bytes(conteudo)


def _opcional(nome: str, tarefa):
    """Sem os próximos jogos ou o calendário, o site continua; só some a parte deles."""
    try:
        return tarefa()
    except (OSError, ValueError, KeyError) as erro:
        print(f"{nome} não atualizado: {erro}")
        return None


def atualizar() -> dict:
    jogos_novos = gravar_resultados(baixar(URL_RESULTADOS))
    temporada = temporada_atual(carregar())
    proximos = _opcional("Próximos jogos", lambda: gravar_proximos(baixar(URL_PROXIMOS)))
    chave = os.environ.get("FOOTBALL_DATA_ORG_TOKEN", "").strip()
    calendario, fonte = None, None
    if chave:
        calendario = _opcional(
            "Calendário do football-data.org",
            lambda: gravar_calendario(calendario_football_data_org(temporada, chave), temporada, "football-data.org"),
        )
        fonte = "football-data.org" if calendario else None
    if calendario is None:
        calendario = _opcional(
            "Calendário do openfootball", lambda: gravar_calendario(calendario_openfootball(temporada), temporada)
        )
        fonte = "openfootball" if calendario else None
    resumo = salvar()
    return {
        "temporada": temporada,
        "jogosNovos": jogos_novos,
        "proximos": proximos,
        "calendario": calendario,
        "fonteCalendario": fonte,
        "conferidos": resumo["jogos"],
    }


if __name__ == "__main__":
    print(json.dumps(atualizar(), ensure_ascii=False))

"""Baixa os resultados e os próximos jogos do football-data, o calendário do
openfootball, e refaz a conferência.

    python -m palpitefc.atualizar

O arquivo novo só substitui o antigo se for lido sem erro e não tiver menos
jogos com placar. Dos próximos jogos, só a Série A é guardada, para o arquivo
não mudar quando mudam as outras ligas.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import urllib.request
from pathlib import Path

from palpitefc.dados import (
    ARQUIVO,
    ARQUIVO_CALENDARIO,
    ARQUIVO_PROXIMOS,
    TEMPORADA_ATUAL,
    carregar,
    converter_calendario,
)
from palpitefc.retrospectiva import salvar

URL_RESULTADOS = "https://www.football-data.co.uk/new/BRA.csv"
URL_PROXIMOS = "https://www.football-data.co.uk/new_league_fixtures.csv"
URL_CALENDARIO = "https://raw.githubusercontent.com/openfootball/football.json/master/{temporada}/br.1.json"
JOGOS_MINIMOS_CALENDARIO = 300
TEMPO_LIMITE = 60
COLUNAS_PROXIMOS = {"Country", "League", "Date", "Time", "Home", "Away"}


def baixar(url: str) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": "PalpiteFC (+https://github.com/Trustcorporation88/palpitefc)"})
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


def gravar_calendario(
    conteudo: bytes, destino: Path = ARQUIVO_CALENDARIO, temporada: str = TEMPORADA_ATUAL
) -> int:
    jogos = converter_calendario(json.loads(conteudo.decode("utf-8-sig")))
    if len(jogos) < JOGOS_MINIMOS_CALENDARIO:
        raise ValueError(f"Calendário com só {len(jogos)} jogos")
    # Um jogo por linha: o diff do commit mostra só o que mudou de data. A
    # temporada vai junto para o calendário velho não valer no ano seguinte.
    linhas = ",\n".join(json.dumps(jogo, ensure_ascii=False) for jogo in jogos)
    texto = f'{{"temporada": {json.dumps(temporada)}, "jogos": [\n{linhas}\n]}}\n'
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
    proximos = _opcional("Próximos jogos", lambda: gravar_proximos(baixar(URL_PROXIMOS)))
    calendario = _opcional(
        "Calendário", lambda: gravar_calendario(baixar(URL_CALENDARIO.format(temporada=TEMPORADA_ATUAL)))
    )
    resumo = salvar()
    return {"jogosNovos": jogos_novos, "proximos": proximos, "calendario": calendario, "conferidos": resumo["jogos"]}


if __name__ == "__main__":
    print(json.dumps(atualizar(), ensure_ascii=False))

"""Baixa os resultados e os próximos jogos do football-data e refaz a conferência.

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

from palpitefc.dados import ARQUIVO, ARQUIVO_PROXIMOS, carregar
from palpitefc.retrospectiva import salvar

URL_RESULTADOS = "https://www.football-data.co.uk/new/BRA.csv"
URL_PROXIMOS = "https://www.football-data.co.uk/new_league_fixtures.csv"
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
    if not destino.exists() or destino.read_text(encoding="utf-8") != saida.getvalue():
        destino.write_text(saida.getvalue(), encoding="utf-8")
    return len(linhas)


def atualizar() -> dict:
    jogos_novos = gravar_resultados(baixar(URL_RESULTADOS))
    try:
        proximos = gravar_proximos(baixar(URL_PROXIMOS))
    except (OSError, ValueError) as erro:
        # Sem a lista de próximos jogos, o site continua; só some a seção.
        print(f"Próximos jogos não baixados: {erro}")
        proximos = None
    resumo = salvar()
    return {"jogosNovos": jogos_novos, "proximos": proximos, "conferidos": resumo["jogos"]}


if __name__ == "__main__":
    print(json.dumps(atualizar(), ensure_ascii=False))

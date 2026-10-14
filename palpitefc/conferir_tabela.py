"""Confere a simulação da tabela em temporadas que já acabaram.

Para cada temporada e cada corte (depois de 5, 10, 19 e 28 rodadas), ajusta o
modelo só com o que havia até ali, simula os jogos que de fato faltavam e
compara com a classificação final de verdade. Notas, menor é melhor:

- RPS da posição: a chance de terminar em cada posição, do 1º ao 20º, contra
  a posição final. Errar por uma posição custa menos que errar por dez.
- Brier das zonas: título, G4 e Z4.

A referência ingênua é "a tabela de hoje fica como está". A escala da
incerteza dos parâmetros é escolhida pelo menor RPS em 2013-2019 e conferida
em 2020-2023. 2024 e 2025 ficam de fora das duas: xi, l2 e o centro do
promovido foram escolhidos nelas, e a prova não pode ter visto a resposta.

    python -m palpitefc.conferir_tabela
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from palpitefc.dados import PASTA, carregar, para_ajuste, promovidos
from palpitefc.model import L2_PADRAO, PROMOVIDO_PADRAO, XI_DECAIMENTO, ajustar
from palpitefc.retrospectiva import historico_ate
from palpitefc.simulacao import ZONAS, classificacao, distribuicao_de_posicoes, sortear

ARQUIVO = PASTA / "conferencia_tabela.json"
TEMPORADAS_DE_ESCOLHA = tuple(str(ano) for ano in range(2013, 2020))
TEMPORADAS_DE_PROVA = tuple(str(ano) for ano in range(2020, 2024))
RODADAS_DE_CORTE = (5, 10, 19, 28)
GRADE_ESCALA = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0)
SIMULACOES = 4000
VARIANTES = 100
ZONAS_CONFERIDAS = ("titulo", "libertadores", "rebaixamento")
TABELA_DE_HOJE = "tabela de hoje"


def chave(escala: float) -> str:
    """Sempre com uma casa: "2.0", e não "2" num lado e "2.0" no outro."""
    return f"{escala:.1f}"


def rps_posicao(distribuicao: np.ndarray, reais: np.ndarray) -> float:
    """RPS médio da posição final. `reais` começa em 0 (o campeão)."""
    n_posicoes = distribuicao.shape[1]
    acumulada = np.cumsum(distribuicao, axis=1)[:, :-1]
    observada = (np.arange(n_posicoes - 1)[None, :] >= reais[:, None]).astype(float)
    return float(((acumulada - observada) ** 2).sum(axis=1).mean() / (n_posicoes - 1))


def brier_zonas(distribuicao: np.ndarray, reais: np.ndarray) -> dict[str, float]:
    notas = {}
    for zona in ZONAS:
        if zona["id"] not in ZONAS_CONFERIDAS:
            continue
        chance = distribuicao[:, zona["de"] - 1 : zona["ate"]].sum(axis=1)
        aconteceu = ((reais + 1 >= zona["de"]) & (reais + 1 <= zona["ate"])).astype(float)
        notas[zona["id"]] = float(((chance - aconteceu) ** 2).mean())
    return notas


def _conferir(argumentos: tuple[str, int]) -> list[dict]:
    temporada, rodada = argumentos
    jogos = carregar()
    da_temporada = [jogo for jogo in jogos if jogo["temporada"] == temporada and jogo["gols_casa"] is not None]
    times = sorted({jogo["casa"] for jogo in da_temporada} | {jogo["fora"] for jogo in da_temporada})
    final = {linha["id"]: linha["posicao"] - 1 for linha in classificacao(da_temporada, times)}

    corte = da_temporada[rodada * len(times) // 2]["quando"]
    tabela = classificacao([jogo for jogo in da_temporada if jogo["quando"] < corte], times)
    restantes = [(jogo["casa"], jogo["fora"]) for jogo in da_temporada if jogo["quando"] >= corte]
    base = para_ajuste(historico_ate(jogos, corte), corte)
    modelo = ajustar(
        base, XI_DECAIMENTO, L2_PADRAO, promovidos(jogos, temporada), PROMOVIDO_PADRAO, com_incerteza=True
    )
    reais = np.array([final[linha["id"]] for linha in tabela])

    hoje = np.eye(len(times))[[linha["posicao"] - 1 for linha in tabela]]
    linhas = [
        {"temporada": temporada, "rodada": rodada, "escala": TABELA_DE_HOJE, "rps": rps_posicao(hoje, reais), **brier_zonas(hoje, reais)}
    ]
    for escala in GRADE_ESCALA:
        sorteio = sortear(
            modelo, tabela, restantes, SIMULACOES, semente=int(temporada) * 100 + rodada, escala=escala, variantes=VARIANTES
        )
        distribuicao = distribuicao_de_posicoes(sorteio.posicoes)
        linhas.append(
            {
                "temporada": temporada,
                "rodada": rodada,
                "escala": chave(escala),
                "rps": rps_posicao(distribuicao, reais),
                **brier_zonas(distribuicao, reais),
            }
        )
    return linhas


def _media(linhas: list[dict], temporadas: tuple[str, ...]) -> dict:
    grupos: dict[str, list[dict]] = {}
    for linha in linhas:
        if linha["temporada"] in temporadas:
            grupos.setdefault(linha["escala"], []).append(linha)
    return {
        escala: {
            "cortes": len(itens),
            **{chave: float(np.mean([item[chave] for item in itens])) for chave in ("rps", *ZONAS_CONFERIDAS)},
        }
        for escala, itens in grupos.items()
    }


def conferir() -> dict:
    tarefas = [(temporada, rodada) for temporada in TEMPORADAS_DE_ESCOLHA + TEMPORADAS_DE_PROVA for rodada in RODADAS_DE_CORTE]
    with ProcessPoolExecutor() as executor:
        linhas = [linha for lote in executor.map(_conferir, tarefas) for linha in lote]
    escolha = _media(linhas, TEMPORADAS_DE_ESCOLHA)
    simuladas = {escala: notas for escala, notas in escolha.items() if escala != TABELA_DE_HOJE}
    melhor = min(simuladas, key=lambda escala: simuladas[escala]["rps"])
    por_corte = {
        str(rodada): _media([linha for linha in linhas if linha["rodada"] == rodada], TEMPORADAS_DE_PROVA)
        for rodada in RODADAS_DE_CORTE
    }
    return {
        "config": {
            "xi": XI_DECAIMENTO,
            "l2": L2_PADRAO,
            "promovido": PROMOVIDO_PADRAO,
            "simulacoes": SIMULACOES,
            "variantes": VARIANTES,
            "rodadasDeCorte": list(RODADAS_DE_CORTE),
            "temporadasDeEscolha": list(TEMPORADAS_DE_ESCOLHA),
            "temporadasDeProva": list(TEMPORADAS_DE_PROVA),
        },
        "melhorEscala": float(melhor),
        "melhorChave": melhor,
        "escolha": escolha,
        "prova": _media(linhas, TEMPORADAS_DE_PROVA),
        "provaPorCorte": por_corte,
    }


def salvar() -> dict:
    resultado = conferir()
    # Bytes com \n: o arquivo sai igual no Windows e no Linux.
    ARQUIVO.write_bytes(json.dumps(resultado, ensure_ascii=False, indent=1).encode("utf-8"))
    return resultado


if __name__ == "__main__":
    resultado = salvar()
    for nome in ("escolha", "prova"):
        print(f"\n{nome} ({', '.join(resultado['config']['temporadasDe' + nome.capitalize()])})")
        print(f"{'escala':>15} {'RPS posição':>12} {'título':>8} {'G4':>8} {'Z4':>8}")
        for escala, notas in sorted(resultado[nome].items(), key=lambda item: item[1]["rps"]):
            print(f"{escala:>15} {notas['rps']:>12.5f} {notas['titulo']:>8.5f} {notas['libertadores']:>8.5f} {notas['rebaixamento']:>8.5f}")
    print("\nmelhor escala:", resultado["melhorEscala"])

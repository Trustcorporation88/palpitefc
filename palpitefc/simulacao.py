"""Joga o resto do campeonato milhares de vezes com a tabela de placares.

Cada confronto que falta recebe um placar sorteado da mesma tabela que gera
as chances do jogo. Somando os pontos, sai a chance de cada time terminar em
cada posição. É o mesmo princípio do site de probabilidades da UFMG e da
antiga previsão do FiveThirtyEight.

Desempate da CBF: pontos, vitórias, saldo, gols marcados. Confronto direto e
cartões ficam de fora; o que ainda empatar é decidido por sorteio.
"""

from __future__ import annotations

import numpy as np

from palpitefc.dados import nome_publico
from palpitefc.model import Modelo

SIMULACOES = 20_000
SEMENTE = 2026

# Regra de 2026: o G6 acabou. Do 1º ao 4º vão à fase de grupos da
# Libertadores, o 5º à fase prévia, do 6º ao 11º à Sul-Americana e o Z4 cai.
# A CBF passa a vaga adiante quando o campeão da Copa do Brasil, da
# Libertadores ou da Sul-Americana já está classificado pela tabela.
ZONAS = (
    {"id": "titulo", "nome": "Título", "curto": "Título", "de": 1, "ate": 1},
    {"id": "libertadores", "nome": "Libertadores (fase de grupos)", "curto": "G4", "de": 1, "ate": 4},
    {"id": "prelibertadores", "nome": "Pré-Libertadores", "curto": "5º", "de": 5, "ate": 5},
    {"id": "sulamericana", "nome": "Sul-Americana", "curto": "Sul-Am.", "de": 6, "ate": 11},
    {"id": "rebaixamento", "nome": "Rebaixamento", "curto": "Z4", "de": 17, "ate": 20},
)
ZONAS_DE_IMPACTO = ("titulo", "libertadores", "rebaixamento")
IMPACTOS_EXIBIDOS = 10


def classificacao(jogos: list[dict], times: list[str]) -> list[dict]:
    """Tabela de hoje, com os jogos que já têm placar."""
    linhas = {time: {"id": time, "nome": nome_publico(time), "j": 0, "v": 0, "e": 0, "d": 0, "gp": 0, "gc": 0} for time in times}
    for jogo in jogos:
        if jogo["gols_casa"] is None or jogo["casa"] not in linhas or jogo["fora"] not in linhas:
            continue
        for time, feitos, sofridos in (
            (jogo["casa"], jogo["gols_casa"], jogo["gols_fora"]),
            (jogo["fora"], jogo["gols_fora"], jogo["gols_casa"]),
        ):
            linha = linhas[time]
            linha["j"] += 1
            linha["gp"] += feitos
            linha["gc"] += sofridos
            if feitos > sofridos:
                linha["v"] += 1
            elif feitos == sofridos:
                linha["e"] += 1
            else:
                linha["d"] += 1
    tabela = []
    for linha in linhas.values():
        linha["pts"] = 3 * linha["v"] + linha["e"]
        linha["sg"] = linha["gp"] - linha["gc"]
        tabela.append(linha)
    tabela.sort(key=lambda linha: (-linha["pts"], -linha["v"], -linha["sg"], -linha["gp"], linha["nome"]))
    for posicao, linha in enumerate(tabela, start=1):
        linha["posicao"] = posicao
    return tabela


def simular(
    modelo: Modelo,
    tabela: list[dict],
    restantes: list[tuple[str, str]],
    simulacoes: int = SIMULACOES,
    semente: int = SEMENTE,
) -> dict:
    times = [linha["id"] for linha in tabela]
    indice = {time: pos for pos, time in enumerate(times)}
    n_times = len(times)
    rng = np.random.default_rng(semente)

    pontos = np.tile(np.array([linha["pts"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    vitorias = np.tile(np.array([linha["v"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    saldo = np.tile(np.array([linha["sg"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    marcados = np.tile(np.array([linha["gp"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    sorteados: list[tuple[str, str, np.ndarray, np.ndarray]] = []

    for casa, fora in restantes:
        if casa not in indice or fora not in indice:
            continue
        grade = modelo.tabela(casa, fora)
        lado = grade.shape[1]
        acumulada = np.cumsum(grade.ravel())
        sorteio = np.searchsorted(acumulada, rng.random(simulacoes) * acumulada[-1], side="right")
        sorteio = np.minimum(sorteio, acumulada.size - 1)
        gols_casa = (sorteio // lado).astype(np.int32)
        gols_fora = (sorteio % lado).astype(np.int32)
        c, f = indice[casa], indice[fora]
        vence_casa = gols_casa > gols_fora
        vence_fora = gols_casa < gols_fora
        empate = ~(vence_casa | vence_fora)
        pontos[:, c] += 3 * vence_casa + empate
        pontos[:, f] += 3 * vence_fora + empate
        vitorias[:, c] += vence_casa
        vitorias[:, f] += vence_fora
        saldo[:, c] += gols_casa - gols_fora
        saldo[:, f] += gols_fora - gols_casa
        marcados[:, c] += gols_casa
        marcados[:, f] += gols_fora
        sorteados.append((casa, fora, np.sign(gols_casa - gols_fora).astype(np.int8), grade))

    # Uma chave só para ordenar: cada critério ocupa sua própria faixa de dígitos.
    chave = (
        pontos.astype(np.float64) * 1e9
        + vitorias * 1e6
        + (saldo + 500) * 1e3
        + np.minimum(marcados, 999)
        + rng.random((simulacoes, n_times))
    )
    ordem = np.argsort(-chave, axis=1)
    posicoes = np.empty_like(ordem)
    np.put_along_axis(posicoes, ordem, np.arange(n_times)[None, :].repeat(simulacoes, axis=0), axis=1)

    distribuicao = np.zeros((n_times, n_times))
    for pos in range(n_times):
        distribuicao[pos] = np.bincount(posicoes[:, pos], minlength=n_times) / simulacoes

    linhas = []
    for pos, linha in enumerate(tabela):
        zonas = {
            zona["id"]: float(distribuicao[pos, zona["de"] - 1 : zona["ate"]].sum()) for zona in ZONAS
        }
        linhas.append(
            {
                **linha,
                "pontosEsperados": float(pontos[:, pos].mean()),
                "pontosFaixa": [int(np.percentile(pontos[:, pos], 5)), int(np.percentile(pontos[:, pos], 95))],
                "zonas": zonas,
                "posicoes": [float(valor) for valor in distribuicao[pos]],
            }
        )
    return {
        "simulacoes": simulacoes,
        "jogosRestantes": len(restantes),
        "zonas": list(ZONAS),
        "times": linhas,
        "impacto": _impacto(sorteados, posicoes, indice),
    }


def _impacto(sorteados: list, posicoes: np.ndarray, indice: dict[str, int]) -> list[dict]:
    """Quanto cada confronto mexe na chance dos dois times.

    Compara as simulações em que o mandante venceu com as que o visitante
    venceu. É a mesma ideia da "importância do jogo" do FiveThirtyEight.
    """
    zonas = {zona["id"]: zona for zona in ZONAS if zona["id"] in ZONAS_DE_IMPACTO}
    jogos = []
    for casa, fora, sinal, grade in sorteados:
        vence_casa = sinal > 0
        vence_fora = sinal < 0
        if not vence_casa.any() or not vence_fora.any():
            continue
        efeitos = []
        for time, venceu, perdeu in ((casa, vence_casa, vence_fora), (fora, vence_fora, vence_casa)):
            posicao = posicoes[:, indice[time]] + 1
            melhor = None
            for zona in zonas.values():
                dentro = (posicao >= zona["de"]) & (posicao <= zona["ate"])
                se_vencer = float(dentro[venceu].mean())
                se_perder = float(dentro[perdeu].mean())
                diferenca = abs(se_vencer - se_perder)
                if melhor is None or diferenca > melhor["diferenca"]:
                    melhor = {
                        "time": time,
                        "nome": nome_publico(time),
                        "zona": zona["id"],
                        "zonaNome": zona["nome"],
                        "hoje": float(dentro.mean()),
                        "seVencer": se_vencer,
                        "sePerder": se_perder,
                        "diferenca": diferenca,
                    }
            efeitos.append(melhor)
        i, j = np.indices(grade.shape)
        jogos.append(
            {
                "casa": casa,
                "fora": fora,
                "casaNome": nome_publico(casa),
                "foraNome": nome_publico(fora),
                "chance": {
                    "casa": float(grade[i > j].sum()),
                    "empate": float(np.trace(grade)),
                    "fora": float(grade[i < j].sum()),
                },
                "peso": max(efeito["diferenca"] for efeito in efeitos),
                "efeitos": efeitos,
            }
        )
    jogos.sort(key=lambda jogo: jogo["peso"], reverse=True)
    return jogos[:IMPACTOS_EXIBIDOS]

"""Joga o resto do campeonato milhares de vezes com a tabela de placares.

Cada confronto que falta recebe um placar sorteado da mesma tabela que gera
as chances do jogo. Somando os pontos, sai a chance de cada time terminar em
cada posição. É o mesmo princípio do site de probabilidades da UFMG e da
antiga previsão do FiveThirtyEight.

A força dos times não é conhecida com exatidão. Por isso cada bloco de
temporadas usa uma versão do modelo sorteada da incerteza dos parâmetros
(covariância sanduíche). Sem isso, a simulação trata a força estimada como
certa e fica confiante demais. A escala dessa incerteza é conferida em
temporadas passadas por `python -m palpitefc.conferir_tabela`.

Desempate da CBF: pontos, vitórias, saldo, gols marcados. Confronto direto e
cartões ficam de fora; o que ainda empatar é decidido por sorteio.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from palpitefc.dados import nome_publico
from palpitefc.model import Modelo, tabelas_de_placares

SIMULACOES = 20_000
SEMENTE = 2026
# Versões do modelo sorteadas da incerteza; cada uma joga SIMULACOES / VARIANTES temporadas.
VARIANTES = 200
# Multiplica o desvio dos parâmetros; zero desliga a incerteza. Escolhida por
# `python -m palpitefc.conferir_tabela`: RPS da posição final 0,1006 -> 0,0986
# em 2013-2019 e 0,1012 -> 0,0993 na prova de 2020-2025. Um teste confere que
# este número é o mesmo que a conferência escolheu.
ESCALA_INCERTEZA = 1.5

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
# Pontuação final que aparece em menos casos que isso fica fora da curva.
CASOS_MINIMOS_PONTOS = 200


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


@dataclass
class Sorteio:
    pontos: np.ndarray  # (simulações, times), na ordem da tabela
    posicoes: np.ndarray  # (simulações, times); 0 é o líder
    jogos: list[tuple[str, str, np.ndarray]]  # casa, fora e o sinal do placar em cada simulação
    variantes: int


def sortear(
    modelo: Modelo,
    tabela: list[dict],
    restantes: list[tuple[str, str]],
    simulacoes: int = SIMULACOES,
    semente: int = SEMENTE,
    escala: float = ESCALA_INCERTEZA,
    variantes: int = VARIANTES,
) -> Sorteio:
    times = [linha["id"] for linha in tabela]
    indice = {time: pos for pos, time in enumerate(times)}
    n_times = len(times)
    rng = np.random.default_rng(semente)

    modelos = modelo.amostras(variantes, escala, rng) if escala > 0 and modelo.covariancia is not None else [modelo]
    n_variantes = len(modelos)
    por_variante = -(-simulacoes // n_variantes)
    simulacoes = por_variante * n_variantes
    ataque = np.array([[versao.ataque.get(time, 0.0) for time in times] for versao in modelos])
    defesa = np.array([[versao.defesa.get(time, 0.0) for time in times] for versao in modelos])
    mando = np.array([versao.mando for versao in modelos])
    rho = np.array([versao.rho for versao in modelos])

    pontos = np.tile(np.array([linha["pts"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    vitorias = np.tile(np.array([linha["v"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    saldo = np.tile(np.array([linha["sg"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    marcados = np.tile(np.array([linha["gp"] for linha in tabela], dtype=np.int32), (simulacoes, 1))
    jogos: list[tuple[str, str, np.ndarray]] = []

    for casa, fora in restantes:
        if casa not in indice or fora not in indice or casa not in modelo.ataque or fora not in modelo.ataque:
            continue
        c, f = indice[casa], indice[fora]
        grades = tabelas_de_placares(np.exp(mando + ataque[:, c] + defesa[:, f]), np.exp(ataque[:, f] + defesa[:, c]), rho)
        lado = grades.shape[2]
        acumuladas = np.cumsum(grades.reshape(n_variantes, -1), axis=1)
        sorte = rng.random((n_variantes, por_variante))
        sorteio = np.empty((n_variantes, por_variante), dtype=np.int64)
        for versao in range(n_variantes):
            sorteio[versao] = np.searchsorted(acumuladas[versao], sorte[versao] * acumuladas[versao, -1], side="right")
        sorteio = np.minimum(sorteio.ravel(), lado * lado - 1)
        gols_casa = (sorteio // lado).astype(np.int32)
        gols_fora = (sorteio % lado).astype(np.int32)
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
        jogos.append((casa, fora, np.sign(gols_casa - gols_fora).astype(np.int8)))

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
    return Sorteio(pontos=pontos, posicoes=posicoes, jogos=jogos, variantes=n_variantes)


def distribuicao_de_posicoes(posicoes: np.ndarray) -> np.ndarray:
    """Linha = time na ordem da tabela, coluna = chance de terminar em cada posição."""
    simulacoes, n_times = posicoes.shape
    distribuicao = np.zeros((n_times, n_times))
    for pos in range(n_times):
        distribuicao[pos] = np.bincount(posicoes[:, pos], minlength=n_times) / simulacoes
    return distribuicao


def simular(
    modelo: Modelo,
    tabela: list[dict],
    restantes: list[tuple[str, str]],
    simulacoes: int = SIMULACOES,
    semente: int = SEMENTE,
    escala: float = ESCALA_INCERTEZA,
    variantes: int = VARIANTES,
) -> dict:
    sorteio = sortear(modelo, tabela, restantes, simulacoes, semente, escala, variantes)
    pontos, posicoes = sorteio.pontos, sorteio.posicoes
    distribuicao = distribuicao_de_posicoes(posicoes)

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
    indice = {linha["id"]: pos for pos, linha in enumerate(tabela)}
    return {
        "simulacoes": int(pontos.shape[0]),
        "variantes": sorteio.variantes,
        "escalaIncerteza": escala if sorteio.variantes > 1 else 0.0,
        "jogosRestantes": len(sorteio.jogos),
        "zonas": list(ZONAS),
        "times": linhas,
        "pontosNecessarios": pontos_necessarios(pontos, posicoes),
        "impacto": _impacto(modelo, sorteio.jogos, posicoes, indice),
    }


def pontos_necessarios(pontos: np.ndarray, posicoes: np.ndarray, minimo: int = CASOS_MINIMOS_PONTOS) -> list[dict]:
    """Para cada pontuação final, a chance de cair em cada zona.

    Junta todos os times de todas as simulações: de quem terminou com 70
    pontos, quantos foram campeões? É a curva de "pontos necessários" do
    site da UFMG, e vale para o campeonato como ele está hoje.
    """
    if pontos.size == 0:
        return []
    valores = pontos.ravel().astype(np.int64)
    lugar = posicoes.ravel() + 1
    menor = int(valores.min())
    deslocados = valores - menor
    casos = np.bincount(deslocados)
    por_zona = {
        zona["id"]: np.bincount(deslocados, weights=(lugar >= zona["de"]) & (lugar <= zona["ate"]), minlength=casos.size)
        for zona in ZONAS
    }
    linhas = []
    for passo, quantos in enumerate(casos):
        if quantos < minimo:
            continue
        linhas.append(
            {
                "pontos": menor + passo,
                "casos": int(quantos),
                **{zona: float(contagem[passo] / quantos) for zona, contagem in por_zona.items()},
            }
        )
    return linhas


def _impacto(modelo: Modelo, jogos: list, posicoes: np.ndarray, indice: dict[str, int]) -> list[dict]:
    """Quanto cada confronto mexe na chance dos dois times, do maior para o menor.

    Compara as simulações em que cada time venceu com as que ele perdeu. É a
    mesma ideia da "importância do jogo" do FiveThirtyEight.
    """
    zonas = [zona for zona in ZONAS if zona["id"] in ZONAS_DE_IMPACTO]
    resultado = []
    for casa, fora, sinal in jogos:
        vence_casa = sinal > 0
        vence_fora = sinal < 0
        if not vence_casa.any() or not vence_fora.any():
            continue
        efeitos = []
        for time, venceu, perdeu in ((casa, vence_casa, vence_fora), (fora, vence_fora, vence_casa)):
            posicao = posicoes[:, indice[time]] + 1
            melhor = None
            for zona in zonas:
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
        grade = modelo.tabela(casa, fora)
        i, j = np.indices(grade.shape)
        resultado.append(
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
    resultado.sort(key=lambda jogo: jogo["peso"], reverse=True)
    return resultado

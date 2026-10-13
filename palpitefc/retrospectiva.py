"""Confere o modelo jogo a jogo, sem usar o resultado que ainda não existia.

Cada jogo recebe três previsões, todas feitas antes do apito:
- modelo: o Dixon-Coles ajustado só com jogos anteriores;
- mercado: a odd média de fechamento, sem a margem da casa (Shin);
- base: a frequência de vitória da casa, empate e vitória do visitante na
  mesma janela, igual para todo jogo. É o piso que qualquer modelo deve bater.

A conta é incremental. Cada jogo guarda uma impressão (placar e odds); se
um placar ou uma odd mudar no CSV, tudo é refeito a partir do primeiro jogo
afetado. Mudar os parâmetros, o código do cálculo ou o histórico anterior à
temporada refaz a temporada inteira.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from palpitefc.dados import PASTA, carregar, para_ajuste, promovidos
from palpitefc.metricas import MERCADOS, calibracao, media_das_notas, notas
from palpitefc.model import L2_PADRAO, PROMOVIDO_PADRAO, XI_DECAIMENTO, ajustar
from palpitefc.palpite import avaliar

ARQUIVO = PASTA / "retrospectiva.json"
JANELA = timedelta(days=900)
MINIMO_JOGOS = 80
VERSAO = 2
REAMOSTRAGENS = 5000
CODIGO_DO_CALCULO = ("model.py", "odds.py", "palpite.py", "metricas.py", "retrospectiva.py")


def _hash(conteudo: str) -> str:
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:12]


def impressao_do_codigo() -> str:
    pasta = Path(__file__).resolve().parent
    # read_text normaliza a quebra de linha: Windows e GitHub Actions chegam ao mesmo número.
    return _hash("".join((pasta / nome).read_text(encoding="utf-8") for nome in CODIGO_DO_CALCULO))


def configuracao(
    xi: float = XI_DECAIMENTO, l2: float = L2_PADRAO, promovido: float = PROMOVIDO_PADRAO, janela: timedelta = JANELA
) -> dict:
    return {
        "versao": VERSAO,
        "xi": xi,
        "l2": l2,
        "promovido": promovido,
        "janelaDias": janela.days,
        "minimoJogos": MINIMO_JOGOS,
        "codigo": impressao_do_codigo(),
    }


def impressoes(jogos: list[dict], temporada: str, janela: timedelta = JANELA) -> tuple[str, dict[str, list]]:
    """O que cada cartão da temporada usa do CSV: o histórico anterior (num
    hash só) e, jogo a jogo, o placar e as odds."""
    da_temporada = [jogo for jogo in jogos if jogo["temporada"] == temporada and jogo["gols_casa"] is not None]
    if not da_temporada:
        return "", {}
    inicio = min(jogo["quando"] for jogo in da_temporada)
    antes = [
        [jogo["quando"].isoformat(timespec="minutes"), jogo["casa"], jogo["fora"], jogo["gols_casa"], jogo["gols_fora"]]
        for jogo in jogos
        if jogo["gols_casa"] is not None and jogo["quando"] < inicio and inicio - jogo["quando"] <= janela
    ]
    por_jogo = {
        _chave(jogo): [jogo["gols_casa"], jogo["gols_fora"], jogo["odd_casa"], jogo["odd_empate"], jogo["odd_fora"]]
        for jogo in da_temporada
    }
    return _hash(json.dumps(antes)), por_jogo


def primeira_mudanca(atuais: dict[str, list], anteriores: dict[str, list]) -> str | None:
    """Data e hora do primeiro jogo novo, sumido ou com placar ou odd diferente."""
    mudados = [chave for chave in atuais.keys() | anteriores.keys() if atuais.get(chave) != anteriores.get(chave)]
    return min((chave.split("|")[0] for chave in mudados), default=None)


def resultado(gols_casa: int, gols_fora: int) -> str:
    if gols_casa > gols_fora:
        return "casa"
    if gols_casa < gols_fora:
        return "fora"
    return "empate"


def historico_ate(jogos: list[dict], quando: datetime, janela: timedelta = JANELA) -> list[dict]:
    return [
        anterior
        for anterior in jogos
        if anterior["gols_casa"] is not None and anterior["quando"] < quando and quando - anterior["quando"] <= janela
    ]


def frequencia_base(base: list[dict]) -> dict[str, float]:
    contagem = {mercado: 0 for mercado in MERCADOS}
    for jogo in base:
        contagem[resultado(jogo["gols_casa"], jogo["gols_fora"])] += 1
    total = sum(contagem.values())
    return {mercado: valor / total for mercado, valor in contagem.items()}


def _chave(jogo: dict) -> str:
    quando = jogo["quando"] if isinstance(jogo["quando"], str) else jogo["quando"].isoformat(timespec="minutes")
    return f"{quando}|{jogo['casa']}|{jogo['fora']}"


def prever_temporada(
    jogos: list[dict],
    temporada: str,
    xi: float = XI_DECAIMENTO,
    l2: float = L2_PADRAO,
    janela: timedelta = JANELA,
    prontos: dict[str, dict] | None = None,
    por_dia: bool = False,
    promovido: float = PROMOVIDO_PADRAO,
) -> list[dict]:
    """Um cartão por jogo da temporada. `por_dia` ajusta uma vez por data,
    com o que havia antes da meia-noite; serve para a busca de parâmetros."""
    prontos = prontos or {}
    subiram = promovidos(jogos, temporada)
    modelos: dict[datetime, object] = {}
    cartoes = []
    for jogo in jogos:
        if jogo["temporada"] != temporada or jogo["gols_casa"] is None:
            continue
        real = resultado(jogo["gols_casa"], jogo["gols_fora"])
        anterior = prontos.get(_chave(jogo))
        if anterior and anterior["resultado"] == {"casa": jogo["gols_casa"], "fora": jogo["gols_fora"], "mercado": real}:
            cartoes.append(anterior)
            continue

        corte = datetime.combine(jogo["quando"].date(), datetime.min.time()) if por_dia else jogo["quando"]
        historico = historico_ate(jogos, corte, janela)
        base = para_ajuste(historico, corte)
        times_vistos = {item["casa"] for item in base} | {item["fora"] for item in base}
        if jogo["casa"] not in times_vistos or jogo["fora"] not in times_vistos or len(base) < MINIMO_JOGOS:
            continue
        if corte not in modelos:
            modelos[corte] = ajustar(base, xi, l2, subiram, promovido)

        odds = {"casa": jogo["odd_casa"], "empate": jogo["odd_empate"], "fora": jogo["odd_fora"]}
        cartao = avaliar(modelos[corte], jogo["casa"], jogo["fora"], odds, marcar_vantagem=True)
        palpite = cartao["palpite"]
        favorito = min(MERCADOS, key=lambda mercado: odds[mercado]) if all(odds.values()) else None
        frequencia = frequencia_base(base)
        cartao["quando"] = jogo["quando"].isoformat(timespec="minutes")
        cartao["resultado"] = {"casa": jogo["gols_casa"], "fora": jogo["gols_fora"], "mercado": real}
        cartao["acertouMaisProvavel"] = cartao["maisProvavel"] == real
        cartao["palpiteAcertou"] = palpite["mercado"] == real if palpite else None
        cartao["favoritoOdd"] = favorito
        cartao["favoritoOddValor"] = odds[favorito] if favorito else None
        cartao["favoritoAcertou"] = favorito == real if favorito else None
        cartao["notas"] = {
            "modelo": notas(cartao["chance"], real),
            "mercado": notas(cartao["mercado"], real) if cartao["mercado"] else None,
            "base": notas(frequencia, real),
        }
        cartoes.append(cartao)
    return cartoes


def _lucro(itens: list[dict], acertou, odd) -> float:
    return sum(odd(item) - 1.0 if acertou(item) else -1.0 for item in itens)


def diferenca_pareada(modelo: list[float], mercado: list[float], semente: int = 7) -> dict | None:
    """RPS do modelo menos RPS da odd, jogo a jogo, com intervalo de 95% por
    bootstrap. Positivo quer dizer que a odd foi melhor."""
    if len(modelo) < 2:
        return None
    diferencas = np.asarray(modelo) - np.asarray(mercado)
    rng = np.random.default_rng(semente)
    sorteio = rng.integers(0, len(diferencas), size=(REAMOSTRAGENS, len(diferencas)))
    medias = diferencas[sorteio].mean(axis=1)
    return {
        "media": float(diferencas.mean()),
        "ic95": [float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))],
    }


def resumir(avaliacoes: list[dict]) -> dict:
    com_resultado = [item for item in avaliacoes if item["resultado"]]
    palpites = [item for item in com_resultado if item["palpite"]]
    favoritos = [item for item in com_resultado if item["favoritoOdd"]]
    com_mercado = [item for item in com_resultado if item["notas"]["mercado"]]
    acertos = sum(1 for item in com_resultado if item["acertouMaisProvavel"])
    acertos_palpite = sum(1 for item in palpites if item["palpiteAcertou"])
    acertos_favorito = sum(1 for item in favoritos if item["favoritoAcertou"])

    pares_modelo = []
    pares_mercado = []
    for item in com_resultado:
        real = item["resultado"]["mercado"]
        for mercado in MERCADOS:
            pares_modelo.append((item["chance"][mercado], mercado == real))
            if item["mercado"]:
                pares_mercado.append((item["mercado"][mercado], mercado == real))

    modelo_rps_melhor = sum(
        1 for item in com_mercado if item["notas"]["modelo"]["rps"] < item["notas"]["mercado"]["rps"]
    )
    return {
        "jogos": len(com_resultado),
        "acertosMaisProvavel": acertos,
        "taxaMaisProvavel": acertos / len(com_resultado) if com_resultado else 0.0,
        "palpites": len(palpites),
        "acertosPalpite": acertos_palpite,
        "taxaPalpite": acertos_palpite / len(palpites) if palpites else 0.0,
        "lucroPalpite": _lucro(palpites, lambda item: item["palpiteAcertou"], lambda item: item["palpite"]["odd"]),
        "favoritos": len(favoritos),
        "acertosFavorito": acertos_favorito,
        "taxaFavorito": acertos_favorito / len(favoritos) if favoritos else 0.0,
        "lucroFavorito": _lucro(favoritos, lambda item: item["favoritoAcertou"], lambda item: item["favoritoOddValor"]),
        "notas": {
            "modelo": media_das_notas([item["notas"]["modelo"] for item in com_resultado]),
            "base": media_das_notas([item["notas"]["base"] for item in com_resultado]),
            "mercado": media_das_notas([item["notas"]["mercado"] for item in com_mercado]),
            "modeloMesmosJogos": media_das_notas([item["notas"]["modelo"] for item in com_mercado]),
            "jogosComMercado": len(com_mercado),
            "jogosModeloMelhor": modelo_rps_melhor,
            "diferencaRps": diferenca_pareada(
                [item["notas"]["modelo"]["rps"] for item in com_mercado],
                [item["notas"]["mercado"]["rps"] for item in com_mercado],
            ),
        },
        "calibracao": {"modelo": calibracao(pares_modelo), "mercado": calibracao(pares_mercado)},
    }


def construir(temporada: str = "2026", anterior: dict | None = None) -> dict:
    jogos = carregar()
    historico, por_jogo = impressoes(jogos, temporada)
    config = {**configuracao(), "historico": historico}
    prontos = {}
    if anterior and anterior.get("config") == config and anterior.get("temporada") == temporada:
        corte = primeira_mudanca(por_jogo, anterior.get("impressoes", {}))
        prontos = {
            _chave(item): item for item in anterior.get("jogos", []) if corte is None or item["quando"] < corte
        }
    avaliacoes = prever_temporada(jogos, temporada, prontos=prontos)
    gerado = datetime.now().isoformat(timespec="seconds")
    if prontos and anterior.get("jogos") == avaliacoes:
        # Nada mudou: o arquivo sai idêntico e não gera commit nem deploy.
        gerado = anterior.get("geradoEm", gerado)
    return {
        "temporada": temporada,
        "geradoEm": gerado,
        "config": config,
        "resumo": resumir(avaliacoes),
        "impressoes": por_jogo,
        "jogos": avaliacoes,
    }


def salvar(destino: Path = ARQUIVO, do_zero: bool = False) -> dict:
    anterior = None
    if destino.exists() and not do_zero:
        anterior = json.loads(destino.read_text(encoding="utf-8"))
    retrospectiva = construir(anterior=anterior)
    destino.write_text(json.dumps(retrospectiva, ensure_ascii=False), encoding="utf-8")
    return retrospectiva["resumo"]


if __name__ == "__main__":
    import sys

    resumo = salvar(do_zero="--do-zero" in sys.argv)
    print(json.dumps({chave: valor for chave, valor in resumo.items() if chave != "calibracao"}, indent=2, ensure_ascii=False))

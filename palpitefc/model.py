"""Dixon-Coles para o placar de um jogo.

Uma única tabela de placares gera todos os mercados, para as chances
não se contradizerem. Jogos antigos pesam menos. O mando de campo entra
como parâmetro próprio. Cada campeonato é ajustado só com os seus times.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

# Escolhidos por `python -m palpitefc.calibrar`: menor RPS em 2024 e 2025,
# jogo a jogo e sem olhar o resultado à frente.
XI_DECAIMENTO = 0.002
L2_PADRAO = 10.0
# Centro da regularização do time que subiu da Série B: ataque abaixo da
# média e defesa acima (sofre mais). Também escolhido pelo RPS: 0,20620 ->
# 0,20597 em 2024-2025 e 0,20468 -> 0,20422 na prova de 2026.
PROMOVIDO_PADRAO = 0.1
GOLS_MAX = 10
RHO_LIMITE = 0.2


@dataclass
class Modelo:
    times: list[str]
    ataque: dict[str, float]
    defesa: dict[str, float]
    mando: float
    rho: float
    # Covariância dos parâmetros livres (ataques e defesas menos o último
    # time, mando e rho), na ordem de `times`. Só existe quando pedida.
    covariancia: np.ndarray | None = field(default=None, repr=False)

    def gols_esperados(self, casa: str, fora: str) -> tuple[float, float]:
        lam = float(
            np.exp(self.mando + self.ataque[casa] + self.defesa[fora])
        )
        mu = float(np.exp(self.ataque[fora] + self.defesa[casa]))
        return lam, mu

    def tabela(self, casa: str, fora: str) -> np.ndarray:
        lam, mu = self.gols_esperados(casa, fora)
        return tabela_de_placares(lam, mu, self.rho)

    def parametros(self) -> np.ndarray:
        return np.array(
            [self.ataque[time] for time in self.times[:-1]]
            + [self.defesa[time] for time in self.times[:-1]]
            + [self.mando, self.rho]
        )

    def amostras(self, quantidade: int, escala: float, rng: np.random.Generator) -> list[Modelo]:
        """Modelos plausíveis, sorteados em volta do ajustado.

        Com `escala` zero, ou sem covariância, todos são o próprio modelo.
        """
        if escala <= 0 or self.covariancia is None:
            return [self] * quantidade
        centro = self.parametros()
        valores, vetores = np.linalg.eigh(self.covariancia)
        raiz = vetores * np.sqrt(np.clip(valores, 0.0, None))
        sorteios = centro + escala * rng.standard_normal((quantidade, centro.size)) @ raiz.T
        n_times = len(self.times)
        modelos = []
        for parametros in sorteios:
            ataque, defesa, mando, rho = _desempacotar(parametros, n_times)
            modelos.append(
                Modelo(
                    times=self.times,
                    ataque=dict(zip(self.times, ataque.tolist())),
                    defesa=dict(zip(self.times, defesa.tolist())),
                    mando=mando,
                    rho=float(np.clip(rho, -RHO_LIMITE, RHO_LIMITE)),
                )
            )
        return modelos


def tabela_de_placares(lam: float, mu: float, rho: float, gols_max: int = GOLS_MAX) -> np.ndarray:
    """P(gols da casa, gols do visitante), com a correção de Dixon-Coles."""
    return tabelas_de_placares(np.array([lam]), np.array([mu]), np.array([rho]), gols_max)[0]


def tabelas_de_placares(lams: np.ndarray, mus: np.ndarray, rhos: np.ndarray, gols_max: int = GOLS_MAX) -> np.ndarray:
    """Várias tabelas de uma vez: uma por par (lam, mu, rho)."""
    gols = np.arange(0, gols_max + 1)
    lams = np.asarray(lams, dtype=float)[:, None]
    mus = np.asarray(mus, dtype=float)[:, None]
    rhos = np.asarray(rhos, dtype=float)
    casa = np.exp(gols * np.log(lams) - lams - gammaln(gols + 1))
    fora = np.exp(gols * np.log(mus) - mus - gammaln(gols + 1))
    grades = casa[:, :, None] * fora[:, None, :]
    lam, mu = lams[:, 0], mus[:, 0]
    grades[:, 0, 0] *= 1.0 - lam * mu * rhos
    grades[:, 0, 1] *= 1.0 + lam * rhos
    grades[:, 1, 0] *= 1.0 + mu * rhos
    grades[:, 1, 1] *= 1.0 - rhos
    grades = np.clip(grades, 0.0, None)
    totais = grades.sum(axis=(1, 2))
    if np.any(totais <= 0):
        raise ValueError("Tabela de placares sem probabilidade")
    return grades / totais[:, None, None]


def mercados(grade: np.ndarray) -> dict[str, float]:
    i, j = np.indices(grade.shape)
    return {
        "casa": float(grade[i > j].sum()),
        "empate": float(np.trace(grade)),
        "fora": float(grade[i < j].sum()),
        "ambos": float(grade[1:, 1:].sum()),
        "mais15": float(grade[i + j >= 2].sum()),
        "mais25": float(grade[i + j >= 3].sum()),
        "mais35": float(grade[i + j >= 4].sum()),
    }


def placares_provaveis(grade: np.ndarray, limite: int = 3) -> list[dict[str, float | int]]:
    planos = [
        (int(i), int(j), float(grade[i, j]))
        for i in range(grade.shape[0])
        for j in range(grade.shape[1])
    ]
    planos.sort(key=lambda item: item[2], reverse=True)
    return [
        {"casa": casa, "fora": fora, "chance": chance}
        for casa, fora, chance in planos[:limite]
    ]


def _desempacotar(parametros: np.ndarray, n_times: int) -> tuple[np.ndarray, np.ndarray, float, float]:
    """O último time fecha a soma zero de ataque e de defesa."""
    livres = n_times - 1
    ataque = np.empty(n_times)
    defesa = np.empty(n_times)
    ataque[:livres] = parametros[:livres]
    ataque[livres] = -ataque[:livres].sum()
    defesa[:livres] = parametros[livres : 2 * livres]
    defesa[livres] = -defesa[:livres].sum()
    return ataque, defesa, float(parametros[-2]), float(parametros[-1])


@dataclass
class _Dados:
    casa: np.ndarray
    fora: np.ndarray
    gols_casa: np.ndarray
    gols_fora: np.ndarray
    pesos: np.ndarray
    n_times: int
    l2: float = 0.0
    centro_ataque: np.ndarray | None = None
    centro_defesa: np.ndarray | None = None


def _por_jogo(parametros: np.ndarray, dados: _Dados):
    """log da chance de cada placar e as derivadas em relação ao log de lam,
    ao log de mu e a rho. None quando o rho torna algum placar impossível."""
    ataque, defesa, mando, rho = _desempacotar(parametros, dados.n_times)
    casa, fora, gols_casa, gols_fora = dados.casa, dados.fora, dados.gols_casa, dados.gols_fora
    lam = np.exp(mando + ataque[casa] + defesa[fora])
    mu = np.exp(ataque[fora] + defesa[casa])

    tau = np.ones(len(gols_casa))
    dtau_lam = np.zeros(len(gols_casa))
    dtau_mu = np.zeros(len(gols_casa))
    dtau_rho = np.zeros(len(gols_casa))
    zero_zero = (gols_casa == 0) & (gols_fora == 0)
    zero_um = (gols_casa == 0) & (gols_fora == 1)
    um_zero = (gols_casa == 1) & (gols_fora == 0)
    um_um = (gols_casa == 1) & (gols_fora == 1)
    tau[zero_zero] = 1.0 - lam[zero_zero] * mu[zero_zero] * rho
    dtau_lam[zero_zero] = -mu[zero_zero] * rho
    dtau_mu[zero_zero] = -lam[zero_zero] * rho
    dtau_rho[zero_zero] = -lam[zero_zero] * mu[zero_zero]
    tau[zero_um] = 1.0 + lam[zero_um] * rho
    dtau_lam[zero_um] = rho
    dtau_rho[zero_um] = lam[zero_um]
    tau[um_zero] = 1.0 + mu[um_zero] * rho
    dtau_mu[um_zero] = rho
    dtau_rho[um_zero] = mu[um_zero]
    tau[um_um] = 1.0 - rho
    dtau_rho[um_um] = -1.0
    if np.any(tau <= 1e-8):
        return None

    log_p = (
        np.log(tau)
        + gols_casa * np.log(lam)
        - lam
        - gammaln(gols_casa + 1)
        + gols_fora * np.log(mu)
        - mu
        - gammaln(gols_fora + 1)
    )
    d_lam = gols_casa - lam + lam * dtau_lam / tau
    d_mu = gols_fora - mu + mu * dtau_mu / tau
    d_rho = dtau_rho / tau
    return (ataque, defesa), log_p, d_lam, d_mu, d_rho


def _penalidade(ataque: np.ndarray, defesa: np.ndarray, dados: _Dados) -> tuple[float, np.ndarray, np.ndarray]:
    """L2 em volta do centro de cada time (zero, ou o centro do promovido)."""
    if dados.l2 <= 0:
        return 0.0, np.zeros_like(ataque), np.zeros_like(defesa)
    desvio_ataque = ataque - (dados.centro_ataque if dados.centro_ataque is not None else 0.0)
    desvio_defesa = defesa - (dados.centro_defesa if dados.centro_defesa is not None else 0.0)
    valor = dados.l2 * float((desvio_ataque**2).sum() + (desvio_defesa**2).sum())
    return valor, 2 * dados.l2 * desvio_ataque, 2 * dados.l2 * desvio_defesa


def _para_livres(d_ataque: np.ndarray, d_defesa: np.ndarray, d_mando, d_rho, n_times: int) -> np.ndarray:
    """Leva derivadas por time para os parâmetros livres (regra da cadeia da soma zero)."""
    livres = n_times - 1
    ataque_livre = d_ataque[..., :livres] - d_ataque[..., livres : livres + 1]
    defesa_livre = d_defesa[..., :livres] - d_defesa[..., livres : livres + 1]
    return np.concatenate(
        [ataque_livre, defesa_livre, np.asarray(d_mando)[..., None], np.asarray(d_rho)[..., None]], axis=-1
    )


def _verossimilhanca_negativa(parametros: np.ndarray, dados: _Dados) -> tuple[float, np.ndarray]:
    """Valor e gradiente analítico. Sem o gradiente, o L-BFGS-B estima cada
    derivada por diferença finita e o ajuste fica dezenas de vezes mais lento."""
    calculo = _por_jogo(parametros, dados)
    if calculo is None:
        return 1e12, np.zeros_like(parametros)
    (ataque, defesa), log_p, d_lam, d_mu, d_rho = calculo
    pesos, n_times = dados.pesos, dados.n_times
    g_lam = pesos * d_lam
    g_mu = pesos * d_mu
    d_ataque = np.bincount(dados.casa, g_lam, n_times) + np.bincount(dados.fora, g_mu, n_times)
    d_defesa = np.bincount(dados.fora, g_lam, n_times) + np.bincount(dados.casa, g_mu, n_times)

    pena, pena_ataque, pena_defesa = _penalidade(ataque, defesa, dados)
    valor = float(-(pesos * log_p).sum()) + pena
    gradiente = _para_livres(
        d_ataque - pena_ataque, d_defesa - pena_defesa, float(g_lam.sum()), float((pesos * d_rho).sum()), n_times
    )
    return valor, -gradiente


def _covariancia(parametros: np.ndarray, dados: _Dados) -> np.ndarray:
    """Covariância H⁻¹ (J + P) H⁻¹.

    H é a curvatura do objetivo (com a regularização). J soma, jogo a jogo,
    o quadrado do peso vezes o gradiente do log da chance: com pesos que caem
    no tempo, é a correção sanduíche, que não finge ter mais informação do
    que há. P é a curvatura da regularização, lida como uma priori: sem ela,
    o time com poucos jogos, muito puxado para o centro, sairia com incerteza
    quase zero. Quando o modelo está certo e os pesos são iguais, J + P = H e
    a conta vira H⁻¹, a covariância bayesiana de sempre.
    """
    passo = 1e-5
    tamanho = parametros.size
    curvatura = np.empty((tamanho, tamanho))
    for coluna in range(tamanho):
        deslocamento = np.zeros(tamanho)
        deslocamento[coluna] = passo
        mais = _verossimilhanca_negativa(parametros + deslocamento, dados)[1]
        menos = _verossimilhanca_negativa(parametros - deslocamento, dados)[1]
        curvatura[:, coluna] = (mais - menos) / (2 * passo)
    curvatura = (curvatura + curvatura.T) / 2

    _, _, d_lam, d_mu, d_rho = _por_jogo(parametros, dados)
    n_jogos, n_times = len(d_lam), dados.n_times
    linhas = np.arange(n_jogos)
    por_time_ataque = np.zeros((n_jogos, n_times))
    por_time_defesa = np.zeros((n_jogos, n_times))
    np.add.at(por_time_ataque, (linhas, dados.casa), d_lam)
    np.add.at(por_time_ataque, (linhas, dados.fora), d_mu)
    np.add.at(por_time_defesa, (linhas, dados.fora), d_lam)
    np.add.at(por_time_defesa, (linhas, dados.casa), d_mu)
    escores = _para_livres(por_time_ataque, por_time_defesa, d_lam, d_rho, n_times) * dados.pesos[:, None]
    informacao = escores.T @ escores

    # Curvatura de l2·Σ(a − centro)² nos parâmetros livres: o último time
    # vale −Σ dos outros, daí o 11ᵀ além da identidade.
    livres = n_times - 1
    priori = np.zeros((tamanho, tamanho))
    if dados.l2 > 0:
        bloco = 2 * dados.l2 * (np.eye(livres) + np.ones((livres, livres)))
        priori[:livres, :livres] = bloco
        priori[livres : 2 * livres, livres : 2 * livres] = bloco

    inversa = np.linalg.pinv(curvatura)
    covariancia = inversa @ (informacao + priori) @ inversa
    return (covariancia + covariancia.T) / 2


def ajustar(
    jogos: list[dict],
    xi: float = XI_DECAIMENTO,
    l2: float = L2_PADRAO,
    promovidos: set[str] | frozenset[str] = frozenset(),
    deslocamento_promovido: float = PROMOVIDO_PADRAO,
    com_incerteza: bool = False,
    times_extras: set[str] | frozenset[str] = frozenset(),
) -> Modelo:
    """Ajusta ataque, defesa, mando e rho. `jogos` traz casa, fora, gols e dias.

    `l2` puxa ataque e defesa para um centro: a média da liga, ou, para os
    `promovidos`, um ataque `deslocamento_promovido` abaixo e uma defesa o
    mesmo tanto acima. Segura o time que chega com poucos jogos na base.

    `times_extras` entram mesmo sem jogo na base: no primeiro jogo de quem
    acabou de subir, a força dele é o próprio centro, com a incerteza da
    regularização. Sem `l2`, eles ficariam sem informação nenhuma.
    """
    if len(jogos) < 20:
        raise ValueError("Histórico curto demais para ajustar o modelo")
    com_jogo = {jogo["casa"] for jogo in jogos} | {jogo["fora"] for jogo in jogos}
    if set(times_extras) - com_jogo and l2 <= 0:
        raise ValueError("Time sem jogo na base precisa de regularização (l2 > 0)")

    times = sorted(com_jogo | set(times_extras))
    indice = {time: pos for pos, time in enumerate(times)}
    n_times = len(times)
    dias = np.array([jogo["dias"] for jogo in jogos], dtype=float)
    pesos = np.exp(-xi * dias)
    centro = np.array([deslocamento_promovido if time in promovidos else 0.0 for time in times])
    dados = _Dados(
        casa=np.array([indice[jogo["casa"]] for jogo in jogos], dtype=int),
        fora=np.array([indice[jogo["fora"]] for jogo in jogos], dtype=int),
        gols_casa=np.array([jogo["gols_casa"] for jogo in jogos], dtype=float),
        gols_fora=np.array([jogo["gols_fora"] for jogo in jogos], dtype=float),
        pesos=pesos / pesos.mean(),
        n_times=n_times,
        l2=l2,
        centro_ataque=-centro,
        centro_defesa=centro,
    )

    livres = n_times - 1
    chute = np.zeros(2 * livres + 2)
    chute[-2] = 0.2
    chute[-1] = -0.05
    limites = [(None, None)] * (2 * livres) + [(None, None), (-RHO_LIMITE, RHO_LIMITE)]

    ajuste = minimize(
        _verossimilhanca_negativa,
        chute,
        args=(dados,),
        jac=True,
        method="L-BFGS-B",
        bounds=limites,
        options={"maxiter": 500, "ftol": 1e-10, "gtol": 1e-6},
    )
    # Ponto inviável devolve 1e12 com gradiente zero, que o L-BFGS-B pode tomar por convergência.
    if not np.isfinite(ajuste.fun) or ajuste.fun >= 1e11:
        raise RuntimeError(f"O modelo não convergiu: {ajuste.message}")

    ataque, defesa, mando, rho = _desempacotar(ajuste.x, n_times)
    return Modelo(
        times=times,
        ataque={time: float(ataque[pos]) for time, pos in indice.items()},
        defesa={time: float(defesa[pos]) for time, pos in indice.items()},
        mando=mando,
        rho=rho,
        covariancia=_covariancia(ajuste.x, dados) if com_incerteza else None,
    )

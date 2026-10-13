"""Dixon-Coles para o placar de um jogo.

Uma única tabela de placares gera todos os mercados, para as chances
não se contradizerem. Jogos antigos pesam menos. O mando de campo entra
como parâmetro próprio. Cada campeonato é ajustado só com os seus times.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

# Escolhidos por `python -m palpitefc.calibrar`: menor RPS em 2024 e 2025,
# jogo a jogo e sem olhar o resultado à frente.
XI_DECAIMENTO = 0.002
L2_PADRAO = 10.0
GOLS_MAX = 10
RHO_LIMITE = 0.2


@dataclass
class Modelo:
    times: list[str]
    ataque: dict[str, float]
    defesa: dict[str, float]
    mando: float
    rho: float

    def gols_esperados(self, casa: str, fora: str) -> tuple[float, float]:
        lam = float(
            np.exp(self.mando + self.ataque[casa] + self.defesa[fora])
        )
        mu = float(np.exp(self.ataque[fora] + self.defesa[casa]))
        return lam, mu

    def tabela(self, casa: str, fora: str) -> np.ndarray:
        lam, mu = self.gols_esperados(casa, fora)
        return tabela_de_placares(lam, mu, self.rho)


def tabela_de_placares(lam: float, mu: float, rho: float, gols_max: int = GOLS_MAX) -> np.ndarray:
    """P(gols da casa, gols do visitante), com a correção de Dixon-Coles."""
    gols = np.arange(0, gols_max + 1)
    casa = np.exp(gols * np.log(lam) - lam - gammaln(gols + 1))
    fora = np.exp(gols * np.log(mu) - mu - gammaln(gols + 1))
    grade = np.outer(casa, fora)
    grade[0, 0] *= 1.0 - lam * mu * rho
    grade[0, 1] *= 1.0 + lam * rho
    grade[1, 0] *= 1.0 + mu * rho
    grade[1, 1] *= 1.0 - rho
    grade = np.clip(grade, 0.0, None)
    total = grade.sum()
    if total <= 0:
        raise ValueError("Tabela de placares sem probabilidade")
    return grade / total


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


def _verossimilhanca_negativa(
    parametros: np.ndarray,
    casa: np.ndarray,
    fora: np.ndarray,
    gols_casa: np.ndarray,
    gols_fora: np.ndarray,
    pesos: np.ndarray,
    n_times: int,
    l2: float = 0.0,
) -> tuple[float, np.ndarray]:
    """Valor e gradiente analítico. Sem o gradiente, o L-BFGS-B estima cada
    derivada por diferença finita e o ajuste fica dezenas de vezes mais lento."""
    ataque, defesa, mando, rho = _desempacotar(parametros, n_times)
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
        return 1e12, np.zeros_like(parametros)

    log_p = (
        np.log(tau)
        + gols_casa * np.log(lam)
        - lam
        - gammaln(gols_casa + 1)
        + gols_fora * np.log(mu)
        - mu
        - gammaln(gols_fora + 1)
    )
    valor = float(-(pesos * log_p).sum())

    # Derivada do log da chance em relação ao log de lam e de mu.
    g_lam = pesos * (gols_casa - lam + lam * dtau_lam / tau)
    g_mu = pesos * (gols_fora - mu + mu * dtau_mu / tau)
    g_rho = float((pesos * dtau_rho / tau).sum())
    d_ataque = np.bincount(casa, g_lam, n_times) + np.bincount(fora, g_mu, n_times)
    d_defesa = np.bincount(fora, g_lam, n_times) + np.bincount(casa, g_mu, n_times)
    d_mando = float(g_lam.sum())

    if l2 > 0:
        valor += l2 * float((ataque**2).sum() + (defesa**2).sum())
        d_ataque = d_ataque - 2 * l2 * ataque
        d_defesa = d_defesa - 2 * l2 * defesa

    livres = n_times - 1
    gradiente = np.empty_like(parametros)
    gradiente[:livres] = d_ataque[:livres] - d_ataque[livres]
    gradiente[livres : 2 * livres] = d_defesa[:livres] - d_defesa[livres]
    gradiente[-2] = d_mando
    gradiente[-1] = g_rho
    return valor, -gradiente


def ajustar(jogos: list[dict], xi: float = XI_DECAIMENTO, l2: float = L2_PADRAO) -> Modelo:
    """Ajusta ataque, defesa, mando e rho. `jogos` traz casa, fora, gols e dias.

    `l2` puxa ataque e defesa para a média. Ajuda o time recém-promovido, que
    chega com poucos jogos na base.
    """
    if len(jogos) < 20:
        raise ValueError("Histórico curto demais para ajustar o modelo")

    times = sorted({jogo["casa"] for jogo in jogos} | {jogo["fora"] for jogo in jogos})
    indice = {time: pos for pos, time in enumerate(times)}
    n_times = len(times)
    casa = np.array([indice[jogo["casa"]] for jogo in jogos], dtype=int)
    fora = np.array([indice[jogo["fora"]] for jogo in jogos], dtype=int)
    gols_casa = np.array([jogo["gols_casa"] for jogo in jogos], dtype=float)
    gols_fora = np.array([jogo["gols_fora"] for jogo in jogos], dtype=float)
    dias = np.array([jogo["dias"] for jogo in jogos], dtype=float)
    pesos = np.exp(-xi * dias)
    pesos = pesos / pesos.mean()

    livres = n_times - 1
    chute = np.zeros(2 * livres + 2)
    chute[-2] = 0.2
    chute[-1] = -0.05
    limites = [(None, None)] * (2 * livres) + [(None, None), (-RHO_LIMITE, RHO_LIMITE)]

    ajuste = minimize(
        _verossimilhanca_negativa,
        chute,
        args=(casa, fora, gols_casa, gols_fora, pesos, n_times, l2),
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
    )

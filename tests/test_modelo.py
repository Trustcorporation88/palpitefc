import unittest
from datetime import datetime, timedelta

import numpy as np
from scipy.optimize import approx_fprime

from palpitefc.model import _Dados, _verossimilhanca_negativa, ajustar, mercados, tabela_de_placares, tabelas_de_placares
from palpitefc.palpite import avaliar


class TesteModelo(unittest.TestCase):
    def test_tabela_soma_um_e_corrige_placar_baixo(self):
        grade = tabela_de_placares(1.4, 1.1, -0.1)
        self.assertAlmostEqual(float(grade.sum()), 1.0, places=6)
        independente = tabela_de_placares(1.4, 1.1, 0.0)
        self.assertGreater(grade[0, 0], independente[0, 0])
        varias = tabelas_de_placares(np.array([1.4, 0.9]), np.array([1.1, 1.6]), np.array([-0.1, 0.05]))
        np.testing.assert_allclose(varias[0], grade)
        np.testing.assert_allclose(varias[1], tabela_de_placares(0.9, 1.6, 0.05))

    def test_mercados_fecham_o_resultado(self):
        grade = tabela_de_placares(1.5, 1.2, -0.05)
        chance = mercados(grade)
        self.assertAlmostEqual(chance["casa"] + chance["empate"] + chance["fora"], 1.0, places=6)
        self.assertGreater(chance["mais15"], chance["mais25"])
        self.assertGreater(chance["mais25"], chance["mais35"])

    def test_time_que_sempre_vence_em_casa_segue_favorito(self):
        forte, fraco = "Forte", "Fraco"
        jogos = []
        inicio = datetime(2026, 1, 1)
        for dia in range(40):
            quando = inicio + timedelta(days=dia)
            jogos.append(
                {
                    "casa": forte,
                    "fora": fraco,
                    "gols_casa": 2,
                    "gols_fora": 0,
                    "dias": 40 - dia,
                }
            )
            jogos.append(
                {
                    "casa": fraco,
                    "fora": forte,
                    "gols_casa": 0,
                    "gols_fora": 2,
                    "dias": 40 - dia,
                }
            )
        modelo = ajustar(jogos)
        cartao = avaliar(modelo, forte, fraco, {"casa": 2.5, "empate": 4.5, "fora": 8.0}, marcar_vantagem=True)
        self.assertGreater(cartao["chance"]["casa"], 0.6)
        self.assertEqual(cartao["maisProvavel"], "casa")
        self.assertIsNotNone(cartao["palpite"])
        self.assertEqual(cartao["palpite"]["mercado"], "casa")

    def test_sem_odd_nao_ha_palpite(self):
        grade = tabela_de_placares(1.3, 1.1, -0.04)
        self.assertAlmostEqual(float(grade.sum()), 1.0, places=6)
        jogos = []
        inicio = datetime(2026, 1, 1)
        for dia in range(30):
            jogos.append(
                {
                    "casa": "A",
                    "fora": "B",
                    "gols_casa": 1,
                    "gols_fora": 1,
                    "dias": float(dia),
                }
            )
        modelo = ajustar(jogos)
        cartao = avaliar(modelo, "A", "B", {})
        self.assertIsNone(cartao["palpite"])

    def test_gradiente_bate_com_diferenca_finita(self):
        rng = np.random.default_rng(3)
        n_times, n_jogos = 6, 120
        casa = rng.integers(0, n_times, n_jogos)
        fora = (casa + rng.integers(1, n_times, n_jogos)) % n_times
        gols_casa = rng.poisson(1.4, n_jogos).astype(float)
        gols_fora = rng.poisson(1.0, n_jogos).astype(float)
        pesos = rng.uniform(0.5, 1.5, n_jogos)
        parametros = np.concatenate([rng.normal(0, 0.2, 2 * (n_times - 1)), [0.3, -0.08]])
        centro = rng.normal(0, 0.1, n_times)
        for l2, centro_ataque, centro_defesa in ((0.0, None, None), (5.0, None, None), (5.0, -centro, centro)):
            dados = _Dados(casa, fora, gols_casa, gols_fora, pesos, n_times, l2, centro_ataque, centro_defesa)
            _, gradiente = _verossimilhanca_negativa(parametros, dados)
            numerico = approx_fprime(parametros, lambda p: _verossimilhanca_negativa(p, dados)[0], 1e-7)
            np.testing.assert_allclose(gradiente, numerico, rtol=1e-4, atol=1e-3)

    def test_incerteza_cai_com_mais_jogos(self):
        rng = np.random.default_rng(5)
        times = ["A", "B", "C", "D", "E", "F"]
        forca = dict(zip(times, np.linspace(-0.3, 0.3, len(times))))

        def temporadas(quantas):
            jogos = []
            for _ in range(quantas):
                for casa in times:
                    for fora in times:
                        if casa != fora:
                            jogos.append(
                                {
                                    "casa": casa,
                                    "fora": fora,
                                    "gols_casa": int(rng.poisson(np.exp(0.3 + forca[casa] - forca[fora]))),
                                    "gols_fora": int(rng.poisson(np.exp(forca[fora] - forca[casa]))),
                                    "dias": 10.0,
                                }
                            )
            return jogos

        pouco = ajustar(temporadas(2), l2=1.0, com_incerteza=True)
        muito = ajustar(temporadas(20), l2=1.0, com_incerteza=True)
        self.assertEqual(pouco.covariancia.shape, (2 * len(times), 2 * len(times)))
        self.assertGreater(np.trace(pouco.covariancia), 3 * np.trace(muito.covariancia))
        self.assertTrue(np.all(np.linalg.eigvalsh(muito.covariancia) > -1e-9))
        amostras = muito.amostras(400, 1.0, np.random.default_rng(1))
        desvio = np.std([modelo.ataque["A"] for modelo in amostras])
        self.assertGreater(desvio, 0)
        self.assertEqual(muito.amostras(3, 0.0, rng), [muito] * 3)

    def test_promovido_comeca_abaixo_da_media(self):
        jogos = []
        times = ["A", "B", "C", "D"]
        for rodada in range(10):
            for casa in times:
                for fora in times:
                    if casa != fora:
                        jogos.append({"casa": casa, "fora": fora, "gols_casa": 1 + rodada % 2, "gols_fora": 1, "dias": 30.0})
        jogos.append({"casa": "Novo", "fora": "A", "gols_casa": 1, "gols_fora": 1, "dias": 1.0})
        neutro = ajustar(jogos, l2=10.0)
        promovido = ajustar(jogos, l2=10.0, promovidos={"Novo"}, deslocamento_promovido=0.3)
        self.assertLess(promovido.ataque["Novo"], neutro.ataque["Novo"])
        self.assertGreater(promovido.defesa["Novo"], neutro.defesa["Novo"])

    def test_l2_segura_time_com_poucos_jogos(self):
        jogos = []
        times = ["A", "B", "C", "D"]
        for rodada in range(15):
            for casa in times:
                for fora in times:
                    if casa != fora:
                        jogos.append({"casa": casa, "fora": fora, "gols_casa": 1 + (rodada + len(casa)) % 2, "gols_fora": 1, "dias": 30.0})
        jogos.append({"casa": "Novo", "fora": "A", "gols_casa": 5, "gols_fora": 0, "dias": 1.0})
        livre = ajustar(jogos, l2=0.0)
        contido = ajustar(jogos, l2=10.0)
        self.assertLess(abs(contido.ataque["Novo"]), abs(livre.ataque["Novo"]))


if __name__ == "__main__":
    unittest.main()

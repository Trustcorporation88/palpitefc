import unittest

from fastapi.testclient import TestClient

from palpitefc.server import app


class TesteApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cliente = TestClient(app)
        cls.cliente.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cliente.__exit__(None, None, None)

    def test_pagina_traz_versao_nos_estaticos(self):
        resposta = self.cliente.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("{{versao}}", resposta.text)
        self.assertIn("/static/app.js?v=", resposta.text)
        self.assertEqual(self.cliente.head("/").status_code, 200)

    def test_saude(self):
        resposta = self.cliente.get("/api/saude")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])
        self.assertEqual(resposta.headers["cache-control"], "no-store")

    def test_inicio_traz_notas(self):
        dados = self.cliente.get("/api/inicio").json()
        notas = dados["resumo"]["notas"]
        self.assertLess(notas["modelo"]["rps"], notas["base"]["rps"])
        self.assertNotIn("calibracao", dados["resumo"])
        self.assertTrue(dados["rodada"])

    def test_tabela_com_vinte_times(self):
        dados = self.cliente.get("/api/tabela").json()
        self.assertEqual(len(dados["times"]), 20)
        self.assertAlmostEqual(sum(time["zonas"]["titulo"] for time in dados["times"]), 1.0, places=6)
        # Depois da última rodada não sobra jogo para mexer na tabela.
        if dados["jogosRestantes"]:
            self.assertTrue(dados["impacto"])
        else:
            self.assertEqual(dados["impacto"], [])

    def test_conta(self):
        dados = self.cliente.get("/api/conta").json()
        self.assertTrue(dados["serie"])
        self.assertIn("calibracao", dados["resumo"])
        self.assertEqual(dados["config"]["versao"], 2)

    def test_time_e_simulador(self):
        time = self.cliente.get("/api/times").json()["times"][0]["id"]
        dados = self.cliente.get(f"/api/time/{time}").json()
        self.assertEqual(dados["tabela"]["id"], time)
        self.assertEqual(self.cliente.get("/api/time/Inexistente").status_code, 404)
        jogo = self.cliente.get("/api/simular", params={"casa": "Palmeiras", "fora": "Flamengo RJ"}).json()
        self.assertEqual(len(jogo["grade"]), 6)
        self.assertIsNone(jogo["palpite"])
        self.assertEqual(self.cliente.get("/api/simular", params={"casa": "Palmeiras", "fora": "Palmeiras"}).status_code, 400)

    def test_cabecalhos(self):
        resposta = self.cliente.get("/api/forca")
        self.assertEqual(resposta.headers["cache-control"], "public, max-age=300")
        self.assertEqual(resposta.headers["x-content-type-options"], "nosniff")

    def test_versao_errada_nao_fica_em_cache(self):
        self.assertEqual(self.cliente.get("/api/forca", params={"v": "outra"}).headers["cache-control"], "no-store")
        self.assertEqual(self.cliente.get("/static/app.js", params={"v": "outra"}).headers["cache-control"], "no-store")
        pagina = self.cliente.get("/").text
        versao = pagina.split('data-versao="')[1].split('"')[0]
        self.assertEqual(
            self.cliente.get("/static/app.js", params={"v": versao}).headers["cache-control"], "public, max-age=86400"
        )


if __name__ == "__main__":
    unittest.main()

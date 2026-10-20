import unittest
from unittest import mock

from fastapi.testclient import TestClient

from palpitefc import contas
from palpitefc.server import app

AMBIENTE = {"SUPABASE_URL": "https://exemplo.supabase.co", "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_teste"}


class TesteApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Quem entra aqui já tem conta e aceitou o termo.
        cls.patches = [mock.patch.dict("os.environ", AMBIENTE), mock.patch.object(contas, "pode_ver", return_value=True)]
        for patch in cls.patches:
            patch.start()
        cls.cliente = TestClient(app, headers={"Authorization": "Bearer token-de-teste-1234567890"})
        cls.cliente.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cliente.__exit__(None, None, None)
        for patch in cls.patches:
            patch.stop()

    def test_privacidade_e_publica(self):
        with TestClient(app) as sem_login:
            resposta = sem_login.get("/privacidade")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("LGPD", resposta.text)
        self.assertIn("Privacidade", resposta.text)

    def test_conferencia_exige_o_token_de_conferencia(self):
        from datetime import datetime
        from types import SimpleNamespace
        from palpitefc import server

        jogos = {
            ("Mirassol", "Internacional"): {
                "casa": "Mirassol", "fora": "Internacional", "golsCasa": 2, "golsFora": 0,
                "situacao": "encerrado", "minuto": None, "quando": datetime(2026, 10, 16, 20, 0),
            },
            ("Flamengo RJ", "Bahia"): {
                "casa": "Flamengo RJ", "fora": "Bahia", "golsCasa": 1, "golsFora": 1,
                "situacao": "ao vivo", "minuto": "30", "quando": datetime(2026, 10, 17, 18, 0),
            },
        }
        with mock.patch.dict("os.environ", {"CONFERENCIA_TOKEN": "conferencia-de-teste-1234567890"}),                 mock.patch.object(server, "ao_vivo", SimpleNamespace(jogos=jogos)), TestClient(app) as sem_login:
            self.assertEqual(sem_login.get("/api/conferencia").status_code, 401)
            self.assertEqual(sem_login.get("/api/conferencia", headers={"X-Conferencia-Token": "errado"}).status_code, 401)
            resposta = sem_login.get("/api/conferencia", headers={"X-Conferencia-Token": "conferencia-de-teste-1234567890"})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["jogos"][0]["placar"], "2–0")
        self.assertEqual(dados["jogos"][0]["resultado"], "casa")
        self.assertIn("chance", dados["jogos"][0])

    def test_api_pede_login(self):
        sem_login = TestClient(app)
        with sem_login:
            for caminho in ("/api/inicio", "/api/tabela", "/api/aovivo"):
                resposta = sem_login.get(caminho)
                self.assertEqual(resposta.status_code, 401)
                self.assertEqual(resposta.headers["cache-control"], "private, no-store")
            # O aviso de saúde continua aberto e não traz nada da conta.
            self.assertEqual(sem_login.get("/api/saude").status_code, 200)

    def test_token_que_nao_vale_ou_sem_termo(self):
        with mock.patch.object(contas, "pode_ver", return_value=False):
            with TestClient(app, headers={"Authorization": "Bearer token-inventado-1234567890"}) as cliente:
                self.assertEqual(cliente.get("/api/inicio").status_code, 401)

    def test_sem_configuracao_nao_abre(self):
        with mock.patch.dict("os.environ", {"SUPABASE_URL": ""}):
            with TestClient(app) as cliente:
                self.assertEqual(cliente.get("/api/inicio").status_code, 503)

    def test_pagina_leva_a_configuracao_publica_do_login(self):
        with mock.patch.dict("os.environ", AMBIENTE):
            from palpitefc import server
            server.pagina_inicial.cache_clear()
            pagina = server.pagina_inicial()
        self.assertIn('content="https://exemplo.supabase.co"', pagina)
        self.assertIn('content="sb_publishable_teste"', pagina)
        self.assertIn(f'content="{contas.VERSAO_DO_TERMO}"', pagina)
        self.assertNotIn("service_role", pagina)
        server.pagina_inicial.cache_clear()

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
        ao_vivo = resposta.json()["aoVivo"]
        self.assertEqual(set(ao_vivo), {"ativo", "consultando", "ultimaConsulta", "erro", "jogos", "timesSemId", "idsDesconhecidos"})
        # Só o formato: na virada do ano a lista enche e não pode travar a atualização dos dados.
        self.assertIsInstance(ao_vivo["timesSemId"], list)

    def test_ao_vivo_sem_token(self):
        resposta = self.cliente.get("/api/aovivo")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers["cache-control"], "private, no-store")
        self.assertEqual(resposta.json()["jogos"], [])

    def test_inicio_traz_notas(self):
        dados = self.cliente.get("/api/inicio").json()
        self.assertRegex(dados["competicao"], r"^Brasileirão Série A \d{4}$")
        self.assertIn(dados["fonteCalendario"], (None, "openfootball", "football-data.org"))
        notas = dados["resumo"]["notas"]
        # No começo da temporada, com poucos jogos, a média da liga pode ganhar por sorte.
        if dados["resumo"]["jogos"] >= 100:
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
            self.assertTrue(dados["pontosNecessarios"])
            self.assertGreater(dados["variantes"], 1)
        else:
            self.assertEqual(dados["impacto"], [])
        self.assertLessEqual(len(dados["impacto"]), 10)
        for jogo in dados["impactoProximaRodada"]:
            self.assertEqual(jogo["agenda"]["rodada"], dados["proximaRodada"])
            self.assertFalse(jogo["agenda"]["atrasado"])

    def test_proxima_rodada_vem_do_calendario(self):
        dados = self.cliente.get("/api/inicio").json()
        if dados["proximaRodada"] is None:
            self.skipTest("Sem calendário ou sem jogo restante")
        for jogo in dados["proximos"]:
            self.assertIsNone(jogo["resultado"])
            self.assertTrue(jogo.get("quando") or jogo["agenda"])
        time = self.cliente.get("/api/times").json()["times"][0]["id"]
        jogos = self.cliente.get(f"/api/time/{time}").json()["jogos"]
        momentos = [(jogo["agenda"]["data"], jogo["agenda"]["hora"] or "99:99") for jogo in jogos if jogo["agenda"]]
        self.assertEqual(momentos, sorted(momentos))
        na_rodada = [
            jogo.get("quando") or f'{jogo["agenda"]["data"]}T{jogo["agenda"]["hora"] or "99:99"}'
            for jogo in dados["proximos"]
            if not jogo["agenda"] or not jogo["agenda"]["atrasado"]
        ]
        self.assertEqual(na_rodada, sorted(na_rodada))

    def test_conta(self):
        dados = self.cliente.get("/api/conta").json()
        self.assertTrue(dados["serie"])
        self.assertIn("calibracao", dados["resumo"])
        self.assertEqual(dados["config"]["versao"], 2)
        self.assertIn("promovido", dados["config"])
        if dados["tabela"]:
            self.assertIn(dados["tabela"]["melhorChave"], dados["tabela"]["prova"])

    def test_time_e_simulador(self):
        time = self.cliente.get("/api/times").json()["times"][0]["id"]
        dados = self.cliente.get(f"/api/time/{time}").json()
        self.assertEqual(dados["tabela"]["id"], time)
        self.assertEqual(self.cliente.get("/api/time/Inexistente").status_code, 404)
        # Até 5: estreante sem jogo na base tem forma menor, e a atualização diária não pode travar por isso.
        self.assertLessEqual(len(dados["forma"]), 5)
        self.assertTrue(all(jogo["texto"] and len(jogo["forma"]["casa"]) <= 5 for jogo in dados["jogos"]))
        jogo = self.cliente.get("/api/simular", params={"casa": "Palmeiras", "fora": "Flamengo RJ"}).json()
        self.assertEqual(len(jogo["grade"]), 6)
        self.assertIsNone(jogo["palpite"])
        self.assertGreater(jogo["confronto"]["jogos"], 0)
        self.assertEqual(
            jogo["confronto"]["vitorias"]["Palmeiras"] + jogo["confronto"]["vitorias"]["Flamengo RJ"] + jogo["confronto"]["empates"],
            jogo["confronto"]["jogos"],
        )
        self.assertLessEqual(len(jogo["formaDetalhada"]["fora"]), 5)
        self.assertTrue(any("Pela conta" in frase for frase in jogo["texto"]))
        self.assertEqual(self.cliente.get("/api/simular", params={"casa": "Palmeiras", "fora": "Palmeiras"}).status_code, 400)

    def test_cabecalhos(self):
        resposta = self.cliente.get("/api/forca")
        # Por usuário: o navegador não guarda a resposta de quem saiu.
        self.assertEqual(resposta.headers["cache-control"], "private, no-store")
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

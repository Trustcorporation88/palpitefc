import io
import json
import unittest
import urllib.error
from unittest import mock

from fastapi.testclient import TestClient

from palpitefc import contas
from palpitefc.server import app

AMBIENTE = {
    "SUPABASE_URL": "https://exemplo.supabase.co",
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_teste",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_teste_nunca_no_chat",
    "ADMIN_EMAIL": "admin@exemplo.com",
}
TOKEN = "token-de-teste-1234567890"


class TesteAdmin(unittest.TestCase):
    def test_so_o_email_do_admin(self):
        with mock.patch.dict("os.environ", AMBIENTE):
            self.assertTrue(contas.eh_admin({"id": "1", "email": "ADMIN@exemplo.com"}))
            self.assertFalse(contas.eh_admin({"id": "2", "email": "outra@exemplo.com"}))
            self.assertFalse(contas.eh_admin(None))
        with mock.patch.dict("os.environ", {"ADMIN_EMAIL": ""}):
            self.assertFalse(contas.eh_admin({"id": "1", "email": ""}))


class TesteRotasDeConta(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.dict("os.environ", AMBIENTE),
            mock.patch.object(contas, "pode_ver", return_value=True),
        ]
        for patch in self.patches:
            patch.start()
        self.cliente = TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})
        self.cliente.__enter__()

    def tearDown(self):
        self.cliente.__exit__(None, None, None)
        for patch in self.patches:
            patch.stop()

    def como(self, email):
        return mock.patch.object(contas, "usuario_de", return_value={"id": "u1", "email": email})

    def test_nao_admin_nao_cria_conta(self):
        with self.como("outra@exemplo.com"), mock.patch.object(contas, "criar_conta") as criar:
            resposta = self.cliente.post("/api/admin/contas", json={"email": "x@exemplo.com", "senha": "senha-boa-123"})
        self.assertEqual(resposta.status_code, 403)
        criar.assert_not_called()

    def test_admin_cria_conta_e_senha_nao_volta(self):
        with self.como("admin@exemplo.com"), mock.patch.object(contas, "criar_conta", return_value="criada") as criar:
            resposta = self.cliente.post("/api/admin/contas", json={"email": " Primo@Exemplo.com ", "senha": "senha-boa-123"})
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json(), {"ok": True, "email": "primo@exemplo.com"})
        criar.assert_called_once_with("primo@exemplo.com", "senha-boa-123")
        self.assertNotIn("senha-boa-123", resposta.text)
        self.assertEqual(resposta.headers["cache-control"], "private, no-store")

    def test_entrada_invalida_nao_ecoa_a_senha(self):
        with self.como("admin@exemplo.com"), mock.patch.object(contas, "criar_conta") as criar:
            curta = self.cliente.post("/api/admin/contas", json={"email": "a@exemplo.com", "senha": "curta"})
            sem_email = self.cliente.post("/api/admin/contas", json={"email": "nao-e-email", "senha": "senha-boa-123"})
            tipo_errado = self.cliente.post("/api/admin/contas", json={"email": "a@exemplo.com", "senha": 12345678})
        self.assertEqual((curta.status_code, sem_email.status_code, tipo_errado.status_code), (400, 400, 400))
        self.assertNotIn("curta", curta.text)
        criar.assert_not_called()

    def test_email_ja_existe(self):
        with self.como("admin@exemplo.com"), mock.patch.object(contas, "criar_conta", return_value="email_exists"):
            resposta = self.cliente.post("/api/admin/contas", json={"email": "a@exemplo.com", "senha": "senha-boa-123"})
        self.assertEqual(resposta.status_code, 409)

    def test_sou_admin(self):
        with self.como("admin@exemplo.com"):
            self.assertEqual(self.cliente.get("/api/admin/eu").json(), {"admin": True})
        with self.como("outra@exemplo.com"):
            self.assertEqual(self.cliente.get("/api/admin/eu").json(), {"admin": False})

    def test_sem_chave_secreta_responde_503(self):
        with mock.patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": ""}), self.como("admin@exemplo.com"):
            resposta = self.cliente.post("/api/admin/contas", json={"email": "a@exemplo.com", "senha": "senha-boa-123"})
        self.assertEqual(resposta.status_code, 503)


class TesteCriarConta(unittest.TestCase):
    def test_corpo_e_cabecalho_da_chamada(self):
        pedidos = []

        def abrir(pedido, timeout=None):
            pedidos.append(pedido)
            return io.BytesIO(b"{}")

        with mock.patch.dict("os.environ", AMBIENTE), mock.patch("urllib.request.urlopen", side_effect=abrir):
            self.assertEqual(contas.criar_conta("a@exemplo.com", "senha-boa-123"), "criada")
        pedido = pedidos[0]
        self.assertTrue(pedido.full_url.endswith("/auth/v1/admin/users"))
        corpo = json.loads(pedido.data.decode("utf-8"))
        self.assertEqual(corpo, {"email": "a@exemplo.com", "password": "senha-boa-123", "email_confirm": True})
        self.assertEqual(pedido.get_header("Apikey"), AMBIENTE["SUPABASE_SERVICE_ROLE_KEY"])

    def test_motivo_de_recusa(self):
        erro = urllib.error.HTTPError(
            "https://exemplo.supabase.co/auth/v1/admin/users", 422, "Unprocessable", {}, io.BytesIO(b'{"error_code":"email_exists"}')
        )
        with mock.patch.dict("os.environ", AMBIENTE), mock.patch("urllib.request.urlopen", side_effect=erro):
            self.assertEqual(contas.criar_conta("a@exemplo.com", "senha-boa-123"), "email_exists")

    def test_erro_do_supabase_nao_vaza_a_chave(self):
        erro = urllib.error.HTTPError("https://exemplo.supabase.co", 500, "Erro", {}, io.BytesIO(b"segredo"))
        with mock.patch.dict("os.environ", AMBIENTE), mock.patch("urllib.request.urlopen", side_effect=erro):
            with self.assertRaises(contas.ContaIndisponivel) as contexto:
                contas.criar_conta("a@exemplo.com", "senha-boa-123")
        self.assertNotIn(AMBIENTE["SUPABASE_SERVICE_ROLE_KEY"], str(contexto.exception))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from palpitefc import servico
from palpitefc.conferir_tabela import ARQUIVO as CONFERENCIA
from palpitefc.dados import carregar_calendario, validar_jogo_do_calendario
from palpitefc.model import Modelo
from palpitefc.simulacao import ESCALA_INCERTEZA


def jogo_do_calendario(casa, fora, rodada, data, hora=None, adiado=False):
    return {"rodada": rodada, "data": data, "hora": hora, "casa": casa, "fora": fora, "adiado": adiado}


def painel_de_teste(calendario, restantes, ultimo_jogo=datetime(2026, 10, 19, 22, 0)):
    """Um Painel só com o que a agenda e a próxima rodada usam."""
    painel = servico.Painel.__new__(servico.Painel)
    painel.calendario = {(jogo["casa"], jogo["fora"]): jogo for jogo in calendario}
    painel.restantes = restantes
    painel.ultimo_jogo = ultimo_jogo
    times = sorted({time for par in restantes for time in par})
    painel.modelo = Modelo(times=times, ataque=dict.fromkeys(times, 0.0), defesa=dict.fromkeys(times, 0.0), mando=0.3, rho=-0.05)
    painel.proxima_rodada = painel._qual_a_proxima_rodada()
    return painel


class TesteAgenda(unittest.TestCase):
    def test_jogo_da_rodada_em_andamento_nao_e_atrasado(self):
        # Rodada começou no sábado (data do openfootball); último resultado no domingo.
        painel = painel_de_teste(
            [jogo_do_calendario("Bahia", "Vasco", 31, "2026-10-17")], [("Bahia", "Vasco")]
        )
        self.assertFalse(painel.agenda("Bahia", "Vasco")["atrasado"])
        self.assertEqual(painel.proxima_rodada, 31)

    def test_jogo_antigo_pendente_e_atrasado(self):
        painel = painel_de_teste(
            [jogo_do_calendario("Bahia", "Vasco", 21, "2026-07-29"), jogo_do_calendario("Remo", "Santos", 31, "2026-10-17", adiado=True)],
            [("Bahia", "Vasco"), ("Remo", "Santos")],
        )
        self.assertTrue(painel.agenda("Bahia", "Vasco")["atrasado"])
        self.assertTrue(painel.agenda("Remo", "Santos")["atrasado"])
        self.assertIsNone(painel.proxima_rodada)

    def test_muitos_adiados_nao_escondem_a_proxima_rodada(self):
        calendario = [jogo_do_calendario(f"Time{numero}", f"Outro{numero}", 20, "2026-07-20") for numero in range(6)]
        calendario.append(jogo_do_calendario("Bahia", "Vasco", 32, "2026-10-24"))
        restantes = [(jogo["casa"], jogo["fora"]) for jogo in calendario]
        painel = painel_de_teste(calendario, restantes)
        self.assertEqual(painel.proxima_rodada, 32)

    def test_mando_invertido_nao_duplica_o_jogo(self):
        painel = painel_de_teste(
            [jogo_do_calendario("Bahia", "Vasco", 31, "2026-10-24")], [("Bahia", "Vasco"), ("Vasco", "Bahia")]
        )
        lista = [
            {"quando": datetime(2026, 10, 24, 18, 30), "casa": "Vasco", "fora": "Bahia", "odd_casa": 2.0, "odd_empate": 3.3, "odd_fora": 3.8}
        ]
        with mock.patch.object(servico, "carregar_proximos", return_value=lista):
            cartoes = painel._proximos(set())
        self.assertEqual([(cartao["casa"], cartao["fora"]) for cartao in cartoes], [("Vasco", "Bahia")])


class TesteCalendarioSeguro(unittest.TestCase):
    def test_recusa_campos_fora_do_formato(self):
        valido = jogo_do_calendario("Palmeiras", "Flamengo RJ", 31, "2026-10-17", "16:00")
        self.assertEqual(validar_jogo_do_calendario(valido), valido)
        for campo, ruim in (
            ("hora", "<img src=x onerror=alert(1)>"),
            ("data", "2026-10-17<script>"),
            ("data", None),
            ("data", "2026-02-30"),
            ("rodada", "31"),
            ("rodada", 0),
            ("casa", "<b>Time</b>"),
            ("adiado", "sim"),
        ):
            with self.assertRaises(ValueError, msg=campo):
                validar_jogo_do_calendario({**valido, campo: ruim})

    def test_arquivo_invalido_ou_de_outro_ano_e_ignorado(self):
        valido = jogo_do_calendario("Palmeiras", "Flamengo RJ", 31, "2026-10-17")
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "calendario.json"
            caminho.write_text(json.dumps({"temporada": "2026", "jogos": [valido]}), encoding="utf-8")
            self.assertEqual(len(carregar_calendario(caminho, "2026")), 1)
            self.assertEqual(carregar_calendario(caminho, "2027"), {})
            caminho.write_text(json.dumps({"temporada": "2026", "jogos": [{**valido, "data": None}]}), encoding="utf-8")
            self.assertEqual(carregar_calendario(caminho, "2026"), {})
            caminho.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(carregar_calendario(caminho, "2026"), {})


class TesteEscala(unittest.TestCase):
    def test_escala_e_a_escolhida_pela_conferencia(self):
        if not CONFERENCIA.exists():
            self.skipTest("Sem conferência da tabela")
        conferencia = json.loads(CONFERENCIA.read_text(encoding="utf-8"))
        self.assertEqual(ESCALA_INCERTEZA, conferencia["melhorEscala"])
        self.assertIn(conferencia["melhorChave"], conferencia["prova"])
        self.assertIn("0.0", conferencia["prova"])


if __name__ == "__main__":
    unittest.main()

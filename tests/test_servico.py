import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
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
    painel.jogos, painel.impacto_por_par, painel._formas, painel._confrontos = [], {}, {}, {}
    painel.temporada = "2026"
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


class TestePainelDeVerdade(unittest.TestCase):
    def test_time_fantasma_do_calendario_nao_entra_na_tabela(self):
        fantasma = {("Fantasma FC", "Palmeiras"): jogo_do_calendario("Fantasma FC", "Palmeiras", 31, "2026-10-17")}
        with mock.patch("palpitefc.dados.carregar_calendario", return_value=(fantasma, "openfootball")), \
             redirect_stdout(io.StringIO()):
            painel = servico.Painel()
        self.assertEqual(len(painel.times_temporada), 20)
        self.assertNotIn("Fantasma FC", painel.times_temporada)
        self.assertEqual((painel.calendario, painel.fonte_calendario), ({}, None))


class TesteHoraConfirmada(unittest.TestCase):
    def test_calendario_decide_a_madrugada_inglesa(self):
        painel = painel_de_teste([jogo_do_calendario("Santos", "Bahia", 32, "2026-10-24", "22:00")], [("Santos", "Bahia")])
        # O football-data publicaria 25/10 01:00, lido como 21:00 de Brasília.
        self.assertEqual(painel.hora_confirmada("Santos", "Bahia", "2026-10-24T21:00"), "2026-10-24T22:00")

    def test_fora_da_madrugada_vale_o_football_data(self):
        painel = painel_de_teste([jogo_do_calendario("Santos", "Bahia", 32, "2026-10-18", "17:00")], [("Santos", "Bahia")])
        self.assertEqual(painel.hora_confirmada("Santos", "Bahia", "2026-10-18T16:00"), "2026-10-18T16:00")


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
            jogos, fonte = carregar_calendario("2026", caminho)
            self.assertEqual((len(jogos), fonte), (1, "openfootball"))
            self.assertEqual(carregar_calendario("2027", caminho), ({}, None))
            caminho.write_text(json.dumps({"temporada": "2026", "jogos": [{**valido, "data": None}]}), encoding="utf-8")
            self.assertEqual(carregar_calendario("2026", caminho), ({}, None))
            caminho.write_text(json.dumps({"temporada": "2026", "fonte": "<script>", "jogos": [valido]}), encoding="utf-8")
            self.assertEqual(carregar_calendario("2026", caminho), ({}, None))
            caminho.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(carregar_calendario("2026", caminho), ({}, None))


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

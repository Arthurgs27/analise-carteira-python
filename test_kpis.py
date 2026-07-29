import unittest

import pandas as pd

from Kpis import calcular_retorno_carteira, retorno_anualizado


class CalculosTest(unittest.TestCase):
    def setUp(self):
        self.precos = pd.DataFrame(
            {"A": [100.0, 110.0, 121.0], "B": [100.0, 100.0, 100.0]},
            index=pd.date_range("2026-01-01", periods=3),
        )
        self.pesos = pd.Series({"A": 0.5, "B": 0.5})

    def test_rebalanceamento_diario(self):
        retorno = calcular_retorno_carteira(
            self.precos, self.pesos, "diario"
        )
        self.assertTrue((retorno.round(10) == 0.05).all())

    def test_comprar_e_manter(self):
        retorno = calcular_retorno_carteira(
            self.precos, self.pesos, "comprar_e_manter"
        )
        self.assertAlmostEqual(retorno.iloc[0], 0.05)
        self.assertAlmostEqual(retorno.iloc[1], 1.105 / 1.05 - 1)

    def test_anualizacao(self):
        retornos = pd.Series([0.01] * 252)
        self.assertAlmostEqual(retorno_anualizado(retornos), 1.01**252 - 1)

    def test_rebalanceamento_invalido(self):
        with self.assertRaises(ValueError):
            calcular_retorno_carteira(self.precos, self.pesos, "mensal")


if __name__ == "__main__":
    unittest.main()

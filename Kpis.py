"""Coleta e análise de uma carteira brasileira de ações.

O script baixa dados, calcula indicadores e grava CSVs e um banco SQLite.
Execute com: python Kpis.py
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


ATIVOS = [
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "WEGE3.SA",
    "MGLU3.SA",
    "ABEV3.SA",
    "BBAS3.SA",
    "RENT3.SA",
]
BENCHMARK = "^BVSP"
DATA_INICIAL = "2021-01-01"
DIAS_UTEIS_ANO = 252
PASTA_SAIDA = Path(__file__).resolve().parent

# "diario" mantém pesos iguais todos os dias. "comprar_e_manter" aplica os
# pesos somente no início e deixa cada posição variar com o mercado.
REBALANCEAMENTO = "diario"


def buscar_serie_bcb(
    codigo_serie: int,
    data_inicial: str,
    data_final: str,
    sessao=None,
) -> pd.Series:
    """Obtém uma série do SGS/BCB; datas devem estar em DD/MM/AAAA."""
    import requests

    cliente = sessao or requests.Session()
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados"
        f"?formato=json&dataInicial={data_inicial}&dataFinal={data_final}"
    )
    resposta = cliente.get(url, timeout=30)
    resposta.raise_for_status()
    dados = resposta.json()
    if not dados:
        raise ValueError(f"O BCB não retornou dados para a série {codigo_serie}.")

    tabela = pd.DataFrame(dados)
    tabela["data"] = pd.to_datetime(tabela["data"], dayfirst=True, errors="raise")
    tabela["valor"] = pd.to_numeric(tabela["valor"], errors="coerce") / 100
    serie = tabela.dropna(subset=["valor"]).set_index("data")["valor"].sort_index()
    serie.name = f"serie_{codigo_serie}"
    return serie


def baixar_precos(
    ativos: list[str], benchmark: str, inicio: str, fim: str
) -> tuple[pd.DataFrame, pd.Series]:
    """Baixa preços ajustados e valida se todos os ativos foram retornados."""
    import yfinance as yf

    precos = yf.download(
        ativos, start=inicio, end=fim, auto_adjust=True, progress=False
    )["Close"]
    ibov = yf.download(
        benchmark, start=inicio, end=fim, auto_adjust=True, progress=False
    )["Close"]

    if isinstance(precos, pd.Series):
        precos = precos.to_frame(name=ativos[0])
    if isinstance(ibov, pd.DataFrame):
        ibov = ibov.iloc[:, 0]

    ausentes = sorted(set(ativos) - set(precos.columns))
    if ausentes:
        raise ValueError(f"Ativos não retornados pelo Yahoo Finance: {ausentes}")

    # Não usa bfill: preencher o passado com um preço futuro cria dados artificiais.
    precos = precos[ativos].sort_index().ffill().dropna(how="any")
    ibov = ibov.sort_index().ffill().dropna()
    if precos.empty or ibov.empty:
        raise ValueError("Não há preços suficientes para realizar os cálculos.")
    return precos, ibov


def calcular_retorno_carteira(
    precos: pd.DataFrame, pesos: pd.Series, rebalanceamento: str
) -> pd.Series:
    """Calcula o retorno diário conforme a regra explícita de rebalanceamento."""
    retornos = precos.pct_change(fill_method=None).dropna(how="any")
    pesos = pesos.reindex(retornos.columns)

    if rebalanceamento == "diario":
        resultado = retornos.mul(pesos).sum(axis=1)
    elif rebalanceamento == "comprar_e_manter":
        patrimonio_relativo = precos.div(precos.iloc[0]).mul(pesos)
        resultado = patrimonio_relativo.sum(axis=1).pct_change(fill_method=None).dropna()
    else:
        raise ValueError(
            "REBALANCEAMENTO deve ser 'diario' ou 'comprar_e_manter'."
        )
    resultado.name = "retorno_carteira"
    return resultado


def retorno_anualizado(retornos: pd.Series) -> float:
    """Anualização geométrica de uma série de retornos diários."""
    if retornos.empty:
        return float("nan")
    return float((1 + retornos).prod() ** (DIAS_UTEIS_ANO / len(retornos)) - 1)


def calcular_analise(
    precos: pd.DataFrame,
    ibov: pd.Series,
    cdi_diario: pd.Series,
    selic_diaria: pd.Series,
    rebalanceamento: str = REBALANCEAMENTO,
) -> dict[str, pd.DataFrame | pd.Series]:
    """Alinha as séries e produz KPIs, evolução, macro e contribuições."""
    pesos = pd.Series(1 / len(precos.columns), index=precos.columns, name="peso")
    retorno_carteira = calcular_retorno_carteira(
        precos, pesos, rebalanceamento
    )
    retorno_ibov = ibov.pct_change(fill_method=None).rename("retorno_ibov")

    base = pd.concat(
        [
            retorno_carteira,
            retorno_ibov,
            cdi_diario.reindex(retorno_carteira.index).ffill().rename("cdi"),
            selic_diaria.reindex(retorno_carteira.index).ffill().rename("selic"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    if base.empty:
        raise ValueError("As séries não possuem datas em comum para análise.")

    acumulados = (1 + base[["retorno_carteira", "retorno_ibov", "cdi"]]).cumprod() - 1
    patrimonio = (1 + base["retorno_carteira"]).cumprod()
    drawdown = patrimonio.div(patrimonio.cummax()).sub(1)
    excesso_diario = base["retorno_carteira"] - base["cdi"]
    volatilidade = base["retorno_carteira"].std(ddof=1) * np.sqrt(DIAS_UTEIS_ANO)
    sharpe = (
        excesso_diario.mean() / excesso_diario.std(ddof=1) * np.sqrt(DIAS_UTEIS_ANO)
        if excesso_diario.std(ddof=1) > 0
        else float("nan")
    )

    retornos_ativos = precos.pct_change(fill_method=None).reindex(base.index).dropna()
    contribuicoes = (
        (1 + retornos_ativos).prod().sub(1).mul(pesos).rename("contribuicao_aproximada")
    )
    kpis = pd.DataFrame(
        [
            {
                "data_inicial": base.index.min().date().isoformat(),
                "data_final": base.index.max().date().isoformat(),
                "rebalanceamento": rebalanceamento,
                "retorno_acumulado_carteira": acumulados["retorno_carteira"].iloc[-1],
                "retorno_acumulado_ibov": acumulados["retorno_ibov"].iloc[-1],
                "retorno_acumulado_cdi": acumulados["cdi"].iloc[-1],
                "retorno_anualizado_carteira": retorno_anualizado(
                    base["retorno_carteira"]
                ),
                "volatilidade_anualizada": volatilidade,
                "indice_sharpe": sharpe,
                "drawdown_maximo": drawdown.min(),
            }
        ]
    )
    evolucao = acumulados.rename(
        columns={
            "retorno_carteira": "retorno_carteira",
            "retorno_ibov": "retorno_ibov",
            "cdi": "retorno_cdi",
        }
    ).reset_index(names="data")
    macro = base[["cdi", "selic"]].reset_index(names="data")
    return {
        "kpis": kpis,
        "evolucao": evolucao,
        "macro": macro,
        "contribuicoes": contribuicoes,
        "retornos_ativos": retornos_ativos,
    }


def exportar_resultados(
    resultados: dict[str, pd.DataFrame | pd.Series],
    precos: pd.DataFrame,
    pasta: Path = PASTA_SAIDA,
) -> None:
    """Grava os CSVs e atualiza o SQLite sem destruir suas restrições."""
    pasta.mkdir(parents=True, exist_ok=True)
    resultados["kpis"].to_csv(
        pasta / "kpis.csv", index=False, sep=";", decimal=","
    )
    resultados["evolucao"].to_csv(
        pasta / "evolucao_carteira.csv", index=False, sep=";", decimal=","
    )
    resultados["macro"].to_csv(
        pasta / "indicadores_macro.csv", index=False, sep=";", decimal=","
    )
    resultados["contribuicoes"].rename_axis("ticker").reset_index().to_csv(
        pasta / "contribuicoes.csv", index=False, sep=";", decimal=","
    )
    resultados["retornos_ativos"].to_csv(pasta / "retornos_diarios.csv")
    precos.to_csv(pasta / "carteira_tratada.csv")

    precos_longos = (
        precos.rename_axis("data")
        .reset_index()
        .melt(id_vars="data", var_name="ticker", value_name="preco_fechamento")
    )
    macro = resultados["macro"].copy()
    macro["data"] = pd.to_datetime(macro["data"]).dt.strftime("%Y-%m-%d")
    precos_longos["data"] = pd.to_datetime(precos_longos["data"]).dt.strftime(
        "%Y-%m-%d"
    )

    with sqlite3.connect(pasta / "atlas_capital.db") as conexao:
        conexao.executescript(
            """
            DROP TABLE IF EXISTS precos_diarios;
            DROP TABLE IF EXISTS indicadores_macro;
            CREATE TABLE precos_diarios (
                data TEXT NOT NULL,
                ticker TEXT NOT NULL,
                preco_fechamento REAL NOT NULL,
                PRIMARY KEY (data, ticker)
            );
            CREATE TABLE indicadores_macro (
                data TEXT PRIMARY KEY,
                cdi REAL,
                selic REAL
            );
            """
        )
        precos_longos.to_sql(
            "precos_diarios", conexao, if_exists="append", index=False
        )
        macro.to_sql("indicadores_macro", conexao, if_exists="append", index=False)


def main() -> None:
    data_final = date.today()
    # O parâmetro end do yfinance é exclusivo.
    fim_yahoo = (data_final + pd.Timedelta(days=1)).isoformat()
    fim_bcb = data_final.strftime("%d/%m/%Y")
    inicio_bcb = pd.Timestamp(DATA_INICIAL).strftime("%d/%m/%Y")

    print("Baixando preços e indicadores...")
    precos, ibov = baixar_precos(ATIVOS, BENCHMARK, DATA_INICIAL, fim_yahoo)
    try:
        cdi = buscar_serie_bcb(12, inicio_bcb, fim_bcb)
        selic = buscar_serie_bcb(11, inicio_bcb, fim_bcb)
    except Exception as erro:
        raise RuntimeError(f"Falha ao obter indicadores do BCB: {erro}") from erro

    resultados = calcular_analise(
        precos, ibov, cdi, selic, REBALANCEAMENTO
    )
    exportar_resultados(resultados, precos)
    print("Análise concluída. Arquivos gravados em:", PASTA_SAIDA)
    print(resultados["kpis"].to_string(index=False))


if __name__ == "__main__":
    main()

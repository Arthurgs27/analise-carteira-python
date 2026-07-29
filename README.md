# Análise de carteira

Projeto em Python para comparar uma carteira de oito ações brasileiras com o
Ibovespa e o CDI. A rotina calcula retorno acumulado e anualizado, volatilidade,
índice de Sharpe e drawdown máximo.

## Instalação

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

## Execução

```powershell
py Kpis.py
```

`Projetop1.py` permanece como uma entrada compatível e executa a mesma rotina.

## Premissas

- Os preços vêm do Yahoo Finance e usam ajuste para proventos e desdobramentos.
- CDI e Selic vêm do SGS do Banco Central.
- A carteira começa com pesos iguais.
- A constante `REBALANCEAMENTO`, em `Kpis.py`, aceita:
  - `diario`: restaura os pesos iguais a cada pregão;
  - `comprar_e_manter`: aplica os pesos apenas no início.
- São considerados 252 pregões por ano.

## Arquivos gerados

- `kpis.csv`: resumo dos indicadores e período efetivamente analisado;
- `evolucao_carteira.csv`: carteira, Ibovespa e CDI ao longo do tempo;
- `indicadores_macro.csv`: CDI e Selic alinhados aos pregões;
- `contribuicoes.csv`: contribuição aproximada de cada ativo;
- `retornos_diarios.csv`: retornos de cada ação;
- `carteira_tratada.csv`: preços tratados;
- `atlas_capital.db`: preços e indicadores macro em SQLite.

As chamadas dependem de internet. Se uma fonte não responder ou retornar dados
inválidos, a execução termina com uma mensagem de erro em vez de gerar resultados
parciais silenciosamente.

# Stihl × Vent — Análise de Confiabilidade de Ativos (Protótipo)

Protótipo Streamlit do dashboard de cálculo de vida útil dos ativos da Stihl.
Replica o relatório LCC-ZFM (Mar/2026) — Injetoras de Magnésio INJ001-INJ004.

## Como rodar

```bash
# 1. Criar venv (opcional, recomendado)
python -m venv venv
source venv/bin/activate   # Linux/Mac
# .\venv\Scripts\activate   # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Rodar o app
streamlit run app.py
```

O dashboard abrirá em `http://localhost:8501`.

## O que está dentro

- **Filtros:** Equipamento (TAG), Período, Tipo de Ordem, Status da Nota
- **KPIs globais:** MTBF, MTTR, β, Custo Corretivo Acumulado, Nº de Notas
- **6 abas:**
  1. **Visão Geral** — comparativo + recomendação automática (Monitorar/Reformar/Substituir)
  2. **MTBF** — mediana + IQR + tendência (por ano), violin por equipamento
  3. **MTTR** — mediana + média + IQR + alerta de outliers
  4. **Weibull & Hazard** — probabilidade Weibull 2P + curva da banheira
  5. **Custos** — custo anual, quebra por classe KOB1, corretivo vs preventivo
  6. **Detalhamento** — tabela join IW28+IW38+IW47+KOB1 + exportação CSV

## Para validar com o cliente (Diego / Fagner)

Pontos para discussão:
- Os filtros cobrem os recortes que vocês usam hoje?
- A recomendação automática (Monitorar/Reformar/Substituir) faz sentido na régua atual?
- Falta alguma visão que está no relatório atual em Excel?
- O DE-PARA de classe de custo está completo? (atualmente cobre Serviço, Material, Reforma, Horas)

## Dados

⚠️ Este protótipo usa **dados sintéticos** calibrados para reproduzir as métricas
do relatório real (β, MTBF, MTTR e picos de custo das 4 injetoras).
A versão produtiva consumirá os dados reais do pipeline ETL após a Fase 2.

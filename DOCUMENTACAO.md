# Stihl × Vent — Análise de Confiabilidade de Ativos
## Documento Detalhado do Produto

---

## 1. O que é

Este produto é um **dashboard interativo de engenharia de confiabilidade**, desenvolvido pela **Vent** para a **Stihl**, que substitui o atual relatório estático em Excel (**LCC-ZFM — Life Cycle Cost, Março/2026**) por uma ferramenta de exploração visual em tempo real.

O escopo inicial cobre as **4 Injetoras de Magnésio** da planta de motores da Stihl Brasil:

| TAG     | Denominação                  | Localização Física              |
|---------|------------------------------|---------------------------------|
| INJ001  | Injetora de Magnésio 1       | BR01-MOT-FMG-INJEC1-INJ001     |
| INJ002  | Injetora de Magnésio 2       | BR01-MOT-FMG-INJEC1-INJ002     |
| INJ003  | Injetora de Magnésio 3       | BR01-MOT-FMG-INJEC2-INJ003     |
| INJ004  | Injetora de Magnésio 4       | BR01-MOT-FMG-INJEC2-INJ004     |

O dashboard responde a três perguntas centrais da engenharia de manutenção:

1. **Em que fase de vida útil cada equipamento se encontra?** (falhas infantis, aleatórias ou desgaste)
2. **Qual é a tendência da confiabilidade ao longo do tempo?** (MTBF/MTTR estão piorando ou estabilizando)
3. **Qual a ação recomendada para cada ativo?** (Monitorar, Reformar ou Substituir)

---

## 2. Contexto e Motivação

A Stihl mantém um pipeline ETL que consolida dados das principais transações SAP de manutenção:

- **IW28** — Lista de notas de manutenção
- **IW38** — Lista de ordens de manutenção
- **IW47** — Lista de trabalhos reais (apontamento de horas)
- **KOB1** — Lançamentos de custo real por ordem

Hoje esses dados desembocam em um relatório Excel mensal (LCC-ZFM) cujo consumo é limitado: difícil filtrar, difícil cruzar variáveis, custoso para atualizar e impossível de explorar de forma interativa.

O protótipo entrega o mesmo conteúdo analítico em ambiente web, com filtros dinâmicos, gráficos interativos e exportação. É a primeira etapa antes da integração com o pipeline produtivo (Fase 2).

---

## 3. Stack Técnica

| Camada                | Tecnologia            |
|-----------------------|-----------------------|
| Frontend / Backend    | Streamlit ≥ 1.32      |
| Manipulação de dados  | pandas ≥ 2.0, numpy ≥ 1.24 |
| Visualização          | Plotly ≥ 5.17         |
| Estatística (Weibull) | SciPy ≥ 1.11          |
| Runtime               | Python 3              |

Arquitetura: **single-file app** ([app.py](app.py), ~1.040 linhas) — adequado a um protótipo, com geração de dados sintéticos cacheada via `@st.cache_data`.

Identidade visual: tema escuro corporativo com laranja Stihl (`#FF6600`) como cor primária e teal Vent (`#5EEAD4`) como cor secundária/de tendência.

---

## 4. Modelo de Dados

### 4.1 Tabela de Falhas (df_falhas)
Cada linha representa uma falha registrada (nota + ordem + tempo de operação até falhar + tempo de reparo).

| Campo                | Descrição                                        |
|----------------------|--------------------------------------------------|
| Equipamento          | TAG (INJ001..INJ004)                             |
| Ordem / Nota         | Identificadores SAP                              |
| Tipo_ordem           | PM01, PM02, …, ZPM1, ZPM2, ZPM3                  |
| Status_nota          | SOLA (encerrada) ou ABER (aberta)                |
| Data / Ano           | Data do evento                                   |
| MTBF_h               | Tempo de operação até a falha (horas)            |
| MTTR_h               | Tempo de reparo (horas)                          |
| Custo_total_reais    | Custo agregado da ordem                          |

### 4.2 Tabela de Custos (df_custos)
Cada linha é um lançamento KOB1 — 1 a 3 lançamentos por ordem.

| Campo            | Descrição                                                  |
|------------------|------------------------------------------------------------|
| Classe_custo     | Código SAP de classe de custo (ex.: 48400100)             |
| Categoria        | DE-PARA: Serviço / Material / Reforma / Horas             |
| Qtd_total        | Quantidade lançada                                         |
| Valor_MR         | Valor em R$                                                |

### 4.3 DE-PARA de Classes de Custo
Atualmente cobre 8 classes mapeadas em 4 categorias:

| Classe SAP   | Categoria  |
|--------------|------------|
| 48400100     | Serviço    |
| 48400105     | Material   |
| 42620510, 42620501, 42620502, 42620504 | Material |
| 48800100     | Reforma    |
| 94301200     | Horas      |

### 4.4 Origem dos Dados
**Atualmente sintéticos.** O gerador ([app.py:245](app.py:245)) cria amostras lognormais calibradas para reproduzir, por equipamento, os parâmetros reais do relatório LCC-ZFM: α, β, MTBF (média e mediana), MTTR (média e mediana), número de falhas e picos anuais de custo. Em produção (Fase 2) o `gerar_dados_mock` é substituído pela leitura do pipeline ETL.

---

## 5. Interface e Funcionalidades

### 5.1 Filtros (sidebar)
- **Equipamento (TAG)** — multi-seleção
- **Período** — slider de ano (range)
- **Tipo de Ordem** — multi-seleção (padrão PM01 + ZPM1 = corretivas, conforme LCC-ZFM)
- **Status da Nota** — SOLA / ABER (padrão SOLA)

Todos os filtros recalculam KPIs e gráficos em tempo real.

### 5.2 KPIs Globais (header)
Cinco cartões fixos no topo, recalculados a cada mudança de filtro:

1. **MTBF Global** — média do MTBF do recorte (horas)
2. **MTTR Global** — média do MTTR do recorte (horas)
3. **β (Weibull)** — parâmetro de forma agregado, com badge da fase de vida (Falhas Infantis / Aleatórias / Desgaste)
4. **Custo Corretivo** — soma dos custos do recorte (em milhares de R$)
5. **Nº de Notas** — contagem do recorte

### 5.3 Abas

#### Aba 1 — Visão Geral
- **Tabela comparativa** com N de falhas, MTBF (mediana e média), MTTR (mediana e média), β, fase de vida, pico de custo, ano do pico, custo médio e **recomendação automática** por equipamento.
- **Gráfico de barras β comparativo** com linha de referência β=1 e cores por faixa de risco.
- **Gráfico de barras de pico de custo histórico**.
- **Leitura técnica** automática (info box) destacando o equipamento mais crítico.

#### Aba 2 — MTBF
- **Série temporal anual** (mediana + faixa IQR P25–P75 + tendência linear) — seletor de equipamento.
- **Violin plot em escala log** comparando distribuição entre equipamentos.
- **Tabela estatística** (N, média, mediana, mín, máx).
- Nota didática sobre uso de mediana vs média em distribuições com cauda longa.

#### Aba 3 — MTTR
- Mesma estrutura da aba MTBF, com **mediana e média sobrepostas** para evidenciar assimetria.
- **Alerta automático de outliers** quando a média de MTTR estiver >30% acima da mediana — sinal de reparos excepcionalmente longos a investigar.

#### Aba 4 — Weibull & Hazard
- **Probability plot Weibull 2P** por equipamento — pontos observados + linha do modelo ajustado.
- **Curva da Banheira (Hazard Function)** com todos os equipamentos sobrepostos para comparação visual da fase de vida.
- Cartão de interpretação automática (β + significado de α como "vida característica" — 63,2% das falhas).

#### Aba 5 — Custos
- **Série temporal anual de custo corretivo** por equipamento.
- **Barras horizontais por categoria** (Serviço / Material / Reforma / Horas) — DE-PARA aplicado.
- **Donut Corretivo × Preventivo** com o split percentual.

#### Aba 6 — Detalhamento
- **Tabela raw** com join IW28+IW38+IW47+KOB1: equipamento, ordem, nota, tipo, status, data, MTBF, MTTR, custo, localização.
- Ordenação por qualquer coluna (Data, Custo, MTBF, MTTR).
- **Exportação para CSV** com nome timestamped.
- Top 500 registros exibidos por padrão.

---

## 6. Fundamentos Técnicos

### 6.1 MTBF — Mean Time Between Failures
Tempo médio de operação entre falhas. **Mediana** é preferida na maioria das comparações porque a distribuição é lognormal/Weibull (cauda longa) e a média fica inflada por outliers.

### 6.2 MTTR — Mean Time To Repair
Tempo médio de reparo. Análise dupla (mediana + média) permite detectar **reparos atípicos** que distorcem a média sem alterar a mediana.

### 6.3 Distribuição Weibull 2P
A função de densidade Weibull com parâmetros (α, β) modela tempos até falha de forma muito mais realista que uma distribuição normal:

- **α (escala / vida característica)** — tempo em que 63,2% das unidades já falharam.
- **β (forma)** — o que dá a interpretação física da fase de vida:

| β              | Fase de vida          | Interpretação                                  |
|----------------|----------------------|------------------------------------------------|
| β < 0,95       | Falhas Infantis      | Defeitos de fabricação/montagem (mortalidade)  |
| 0,95 ≤ β ≤ 1,05| Falhas Aleatórias    | Causas externas, eventos independentes do tempo|
| β > 1,05       | Desgaste / Aging     | Fim de vida útil — falhas dependem da idade    |

O ajuste é feito por **Máxima Verossimilhança** via `scipy.stats.weibull_min.fit` ([app.py:320](app.py:320)).

### 6.4 Curva da Banheira (Hazard Function)
Taxa de falha instantânea h(t) = (β/α)·(t/α)^(β−1). Mostra visualmente a taxa de falha esperada ao longo do tempo: curva descendente = falhas infantis; plana = aleatórias; ascendente = desgaste.

### 6.5 Régua de Recomendação Automática
Implementada em [`recomendacao_equipamento()`](app.py:366) — sistema de pontuação que combina três sinais:

| Sinal                              | +1 ponto     | +2 pontos    |
|------------------------------------|--------------|--------------|
| β (forma)                          | > 2,0        | > 2,5        |
| Tendência MTBF (h/ano)             | < −1         | < −2         |
| Pico de custo histórico (R$)       | > 130k       | > 180k       |

**Score → Recomendação:**
- 0–2 → **Monitorar** (verde)
- 3–4 → **Reformar** (amarelo)
- ≥ 5 → **Substituir** (vermelho)

Esta régua é um dos principais pontos de validação com o cliente.

---

## 7. Resultados Atuais do Recorte (Mar/2026)

Parâmetros calibrados a partir do relatório LCC-ZFM:

| TAG     | β     | MTBF méd | MTTR méd | Pico Custo  | Ano Pico | Observação                          |
|---------|-------|----------|----------|-------------|----------|-------------------------------------|
| INJ001  | 2,18  | 49,4 h   | 2,98 h   | R$ 176k     | 2023     | Crescimento progressivo             |
| INJ002  | 2,64  | 45,9 h   | 3,00 h   | R$ 124k     | 2022     | Oscilação forte e alto custo recente|
| INJ003  | 2,02  | 63,0 h   | 2,80 h   | R$ 205k     | 2022     | Maior pico entre todas as máquinas  |
| INJ004  | 2,19  | 56,6 h   | 2,83 h   | R$ 128k     | 2025     | Três anos seguidos de elevação      |

**Leitura agregada:** todas as 4 injetoras operam com β > 2 — todas em **fase de desgaste**. INJ002 lidera o indicador β (candidato natural a reforma/substituição). INJ003 carrega o maior pico histórico de custo.

---

## 8. Pontos de Validação com o Cliente

Conforme o [README.md](README.md), a versão atual está aberta para discussão com os interlocutores da Stihl (Diego e Fagner):

1. Os filtros cobrem todos os recortes usados hoje?
2. A régua de recomendação (Monitorar/Reformar/Substituir) e seus thresholds fazem sentido?
3. Existe alguma visão do relatório Excel que ainda falta no dashboard?
4. O DE-PARA de classes de custo está completo?

---

## 9. Como Executar Localmente

```bash
# 1. Ambiente virtual (opcional, recomendado)
python -m venv venv
source venv/bin/activate          # Linux/Mac
# .\venv\Scripts\activate         # Windows

# 2. Dependências
pip install -r requirements.txt

# 3. Subir o app
streamlit run app.py
```

App disponível em `http://localhost:8501`.

---

## 10. Estado Atual e Roadmap

### Fase 1 — Protótipo (atual, v0.1)
- App single-file em Streamlit
- Dados sintéticos calibrados
- 6 abas analíticas + filtros + exportação CSV
- Identidade visual Stihl × Vent
- Régua de recomendação automática

### Fase 2 — Produtivo (planejado)
- Substituição do `gerar_dados_mock` pela leitura do **pipeline ETL** corporativo
- Atualização automática conforme a cadência das transações SAP
- Possível expansão para outros centros de custo além de MOT-FMG
- Calibração da régua de recomendação a partir do feedback do time de engenharia

---

## 11. Estrutura do Repositório

```
stihlcalculo/
├── app.py              # Aplicação Streamlit completa (~1.040 linhas)
├── requirements.txt    # streamlit, pandas, numpy, plotly, scipy
├── README.md           # Instruções rápidas para rodar
├── DOCUMENTACAO.md     # Este documento
└── venv/               # Ambiente virtual (não versionado)
```

---

*Documento gerado em 2026-05-20 a partir do código-fonte do protótipo v0.1.*

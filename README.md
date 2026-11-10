# datasus-extractor

[![Testes](https://github.com/victorsimasdev/datasus-extractor/actions/workflows/testes.yml/badge.svg)](https://github.com/victorsimasdev/datasus-extractor/actions/workflows/testes.yml)

Pipeline automatizado que coleta dados de **Morbidade Hospitalar do SUS (SIH/SUS)** no [TabNet/DATASUS](https://tabnet.datasus.gov.br), preenche uma planilha Excel e guarda **evidência (PDF + print) de cada tabela consultada**.

A prioridade é a confiabilidade: nenhum valor da planilha pode divergir do que o site mostra. Por isso cada consulta é validada antes e depois de enviada, e há uma conferência independente que relê os PDFs e compara célula por célula com a planilha.

## O que o projeto coleta

- **Fonte:** TabNet → Morbidade Hospitalar do SUS → *Geral, por local de internação – a partir de 2008*
- **CID-10:** Transtornos de condução e arritmias cardíacas
- **Abrangência:** os 27 estados, as 5 regiões e o Brasil, mês a mês (Jul/2025 a Ago/2026)
- **Rodada 1 (`coletar_datasus.py`):** Internações, Valor médio da internação, Média de permanência e Óbitos
- **Rodada 2 (`coletar_perfil.py`):** Internações por perfil: sexo, faixa etária (20 a 80+ anos) e cor/raça

Cada consulta abre o formulário num Chrome real (Playwright, headless), seleciona os filtros como uma pessoa faria, **confere o formulário inteiro** antes de clicar em "Mostra", confere no resultado o estado, o CID e o período, lê a tabela e salva:

- um **PDF** com rodapé de URL e data/hora da consulta;
- um **PNG** com faixa de legenda (endereço, período, filtros);
- quando o site responde "Nenhum registro selecionado", também um print do formulário preenchido (a planilha recebe `SR`).

Os estados também são consultados pelo formulário nacional (por UF e por Região), para conferência cruzada.

## Estrutura

| Arquivo | Função |
|---|---|
| `coletar_datasus.py` | Coleta da rodada 1 e classe `Coletor` (navegação, validação, evidências). Retoma de onde parou. |
| `coletar_perfil.py` | Coleta por perfil (sexo, faixa etária, cor/raça), reutilizando o `Coletor`. |
| `preencher_planilha.py` | Gera a planilha preenchida da rodada 1 a partir do modelo (o original nunca é alterado) e a aba `EVIDÊNCIAS` com links. |
| `preencher_perfil.py` | Preenche as colunas por perfil e faz as checagens de consistência (soma das categorias × total etc.). |
| `conferir_evidencias.py` / `conferir_perfil.py` | Conferência **independente**: lê o texto dos PDFs e compara com cada célula da planilha entregue. |
| `rodar_noite.py` / `rodar_perfil.py` | Execução sem supervisão: impede a suspensão do Windows, reinicia após falhas, gera planilha, relatório e pasta de entrega. |
| `enviar_drive.py` | Copia a pasta de entrega para o Google Drive para Desktop quando a execução termina. |
| `progresso.py` | Janela de acompanhamento da coleta (somente leitura). |
| `comum.py` | Gravação atômica de JSON, leitura que detecta arquivo corrompido, conferência de cópias por SHA-256 e prevenção de suspensão do Windows. |
| `migrar.py`, `verificar_retomada.py` | Exportar a coleta em andamento e retomá-la em outro computador, conferindo os dados copiados. |
| `*.bat` | Atalhos de duplo clique para Windows (parar/exportar, continuar, abrir progresso). |
| `tests/` | Testes unitários (pytest), sem acesso ao site. |
| `docs/` | Guia para interromper a coleta e continuar em outro computador. |

## Requisitos

- Windows (os atalhos `.bat` e a prevenção de suspensão são do Windows; a coleta em si também roda em outros sistemas)
- Python 3.10+
- Google Chrome instalado

```bash
pip install -r requirements.txt
```

## Uso

As planilhas-modelo (`FA - INTERNAÇÕES.xlsx` e `FA - INTERNAÇÕES (modelo perfil).xlsx`) não estão no repositório e precisam estar na pasta do projeto.

Teste rápido com poucos casos:

```bash
python coletar_datasus.py --demo
```

```bash
python coletar_perfil.py --demo
```

Coleta completa (pode ser interrompida e retomada; o que já foi salvo é pulado):

```bash
python coletar_datasus.py
```

```bash
python coletar_perfil.py
```

Execução completa sem supervisão (coleta + planilha + conferências + pasta de entrega):

```bash
python rodar_perfil.py
```

Conferência independente de uma entrega:

```bash
python conferir_evidencias.py "ENTREGA - FA INTERNAÇÕES DATASUS"
```

## Garantias de robustez

- **Gravação atômica:** dados e status são gravados num arquivo temporário e trocados pelo definitivo; uma queda de energia no meio da gravação nunca deixa o JSON pela metade.
- **JSON corrompido não é tratado como vazio:** a coleta e a execução sem supervisão param com uma mensagem clara, em vez de recomeçar do zero por cima do que já existia.
- **Conferências que barram a entrega:** `preencher_*.py` e `conferir_*.py` saem com código 1 quando encontram qualquer problema, e as execuções sem supervisão só marcam `"concluido"` com 0 erros.
- **Cópias conferidas pelo conteúdo:** o envio ao Drive e a exportação para outro computador conferem cada arquivo por SHA-256, não só pelo tamanho.
- **Retomada:** cada consulta é salva assim que termina; rodar de novo continua de onde parou.

### Códigos de saída

| Script | 0 | 1 | 2 |
|---|---|---|---|
| `conferir_evidencias.py`, `conferir_perfil.py` | nenhum erro | algum erro (listado na saída) | uso incorreto |
| `preencher_planilha.py`, `preencher_perfil.py` | planilha gerada sem problemas | problema, diferença ou consulta faltando | — |

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
```

```bash
ruff check .
```

```bash
pytest
```

Os testes rodam no GitHub Actions a cada push, no Windows e no Ubuntu.

## Particularidades do TabNet tratadas

- `-` significa zero verdadeiro; `...` significa dado não disponível. Números em formato brasileiro (`6.252,36`).
- Sem dados, o site devolve só "Nenhum registro selecionado", sem título nem período: a evidência passa a ser o print do formulário conferido.
- O formulário nacional por UF/Região é o `niuf.def` (o `nibr.def` é por município).
- O servidor oscila bastante: cada consulta tem até 10 tentativas com espera crescente, e a execução sem supervisão reinicia a coleta após falhas.
- Estadual e nacional às vezes diferem em R$ 0,01 no valor médio (arredondamento do próprio TabNet). A planilha usa a estadual, as duas ficam como evidência e o caso aparece como aviso no relatório; qualquer outra diferença bloqueia a entrega.
- Dados dos últimos seis meses estão sujeitos a atualização no site.

## O que não vai para o repositório

Dados coletados (`dados_*.json`), evidências (PDF/PNG), planilhas, logs e pastas de entrega são gerados pela coleta e ficam fora do Git (ver `.gitignore`).

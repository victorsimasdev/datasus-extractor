# datasus-extractor

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
| `migrar.py`, `verificar_retomada.py` | Exportar a coleta em andamento e retomá-la em outro computador, conferindo os dados copiados. |
| `*.bat` | Atalhos de duplo clique para Windows (parar/exportar, continuar, abrir progresso). |
| `docs/` | Guia para interromper a coleta e continuar em outro computador. |

## Requisitos

- Windows (usa a fonte Arial do sistema e APIs do Windows para evitar suspensão)
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

## Particularidades do TabNet tratadas

- `-` significa zero verdadeiro; `...` significa dado não disponível. Números em formato brasileiro (`6.252,36`).
- Sem dados, o site devolve só "Nenhum registro selecionado", sem título nem período: a evidência passa a ser o print do formulário conferido.
- O formulário nacional por UF/Região é o `niuf.def` (o `nibr.def` é por município).
- O servidor oscila bastante: cada consulta tem até 10 tentativas com espera crescente, e a execução sem supervisão reinicia a coleta após falhas.
- Estadual e nacional às vezes diferem em R$ 0,01 no valor médio (arredondamento do próprio TabNet). A planilha usa a estadual e as duas ficam como evidência.
- Dados dos últimos seis meses estão sujeitos a atualização no site.

## O que não vai para o repositório

Dados coletados (`dados_*.json`), evidências (PDF/PNG), planilhas, logs e pastas de entrega são gerados pela coleta e ficam fora do Git (ver `.gitignore`).

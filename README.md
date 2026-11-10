# datasus-extractor

[![Testes](https://github.com/victorsimasdev/datasus-extractor/actions/workflows/testes.yml/badge.svg)](https://github.com/victorsimasdev/datasus-extractor/actions/workflows/testes.yml)

Extrai dados do [TabNet/DATASUS](https://tabnet.datasus.gov.br) a partir de um pedido montado numa janela: a base, o período, os filtros e o layout da planilha. Guarda **evidência (PDF + print) de cada tabela consultada** e confere a planilha, célula por célula, contra os PDFs.

A prioridade é a confiabilidade: nenhum valor da planilha pode divergir do que o site mostra. Cada consulta é conferida antes de ser enviada e depois, no resultado. Ao final, uma conferência independente relê cada valor no PDF.

## Bases disponíveis

| Base | Sistema | Período |
|---|---|---|
| Internações hospitalares | SIH/SUS, por local de internação | mensal, desde 2008 |
| Mortalidade | SIM, CID-10 | anual, desde 1996 |
| Nascidos vivos | SINASC | anual, desde 1994 |
| Produção ambulatorial | SIA/SUS, por local de atendimento | mensal, desde 2008 |

Em todas, a coleta pode ser no Brasil inteiro (linhas por região, estado...) ou dentro de estados escolhidos (linhas por município, região de saúde, estabelecimento...). As opções de cada campo são as reais do site, lidas dos 112 formulários (nacional e 27 estados de cada base).

## Requisitos

- Python 3.11+
- Google Chrome instalado (a coleta usa o Chrome do computador)
- Windows recomendado (a prevenção de suspensão durante a coleta é do Windows)

```bash
pip install -r requirements.txt
```

## Uso

Abrir a janela e montar um pedido:

```bash
python -m extrator
```

Os seis passos da janela:

1. **Base de dados** e abrangência (Brasil inteiro ou estados escolhidos).
2. **O que contar**, o que vai em cada linha da planilha e, se quiser, quebras em colunas.
3. **Período**: cada período separado, ou grupos somados (trimestre, ano).
4. **Filtros**: em cada campo, marque as opções e escolha se cada uma vira um resultado separado ou se entram somadas num grupo. Com 1 item, o campo limita o pedido inteiro; com 2 ou mais, vira um bloco de colunas na planilha (ex.: SEXO, IDADE, RAÇA), com nome editável.
5. **Saída**: pasta, formato da planilha, evidências e conferências.
6. **Revisar**: prévia da planilha e resumo.

Ao clicar em **Gerar pedido**, a janela salva `pedido.json` na pasta de saída e oferece iniciar a coleta, que roda numa janela própria. A coleta também pode ser iniciada (ou retomada) pela linha de comando:

```bash
python -m extrator rodar "caminho/do/pedido.json"
```

No fim, a pasta de saída do pedido tem:

| Arquivo | Conteúdo |
|---|---|
| `<nome do pedido>.xlsx` | a planilha, com as abas EVIDÊNCIAS (links dos PDFs e PNGs) e _MAPA (oculta, de onde veio cada célula) |
| `evidencias/` | PDF e PNG de cada consulta, uma pasta por período |
| `RELATÓRIO.txt` | resumo, avisos e o resultado da conferência independente |
| `dados.json`, `status.json`, `execucao.log` | texto exato de cada consulta, progresso e log |

Outros comandos:

```bash
python -m extrator planilha "pasta/da/coleta"
```

```bash
python -m extrator conferir "pasta/da/coleta/planilha.xlsx"
```

```bash
python -m extrator atualizar-opcoes
```

## Regras da planilha

- **SR (sem resultado)**: linha zerada (sempre exibida, nunca ocultada), "Nenhum registro selecionado", `-` (zero) e `...` (dado não disponível).
- **Nada é calculado**: cada célula é o texto exato do site, convertido em número. Grupos somados e totais são somados pelo próprio site, inclusive médias e taxas, que ele recalcula.
- **Formatos**: uma aba por período com blocos de colunas (como a planilha FA - INTERNAÇÕES), tudo numa aba só (uma linha por valor, para Power BI) ou série no tempo.

## Como a coleta funciona

O pedido vira um plano com a lista exata de consultas (`extrator/pedido.py`). Cada consulta (`extrator/tabnet.py`):

1. abre o formulário num Chrome real, sem janela, e seleciona linha, coluna, conteúdos, períodos e filtros;
2. marca "Exibir linhas zeradas" e **confere o formulário inteiro** antes de clicar em "Mostra";
3. confere no resultado o período e cada filtro com as opções pedidas (se não bate, refaz a consulta);
4. lê a tabela e registra se a soma das linhas não bate com o TOTAL do site;
5. salva o PDF (na largura da tabela, sem cortar colunas) e o PNG com legenda; sem registro, também o print do formulário.

Regras do site que o plano respeita (testadas no site):

- várias opções marcadas no mesmo filtro, ou vários períodos, viram um resultado só, somado;
- o mesmo campo pode ser coluna e filtro: as opções separadas de um campo que existe como coluna saem numa consulta só;
- com coluna ativa, o site aceita um conteúdo por consulta.

## Garantias de robustez

- **Retomada**: cada consulta é gravada assim que termina; rodar de novo continua de onde parou. Se o site cair, a execução espera e continua sozinha.
- **Gravação atômica**: um JSON nunca fica pela metade, e um JSON corrompido para a coleta em vez de recomeçar por cima.
- **Conferência que barra a entrega**: `status.json` só fica `"concluido"` com 0 erros na conferência independente pelos PDFs.

## Estrutura

| Caminho | Função |
|---|---|
| `extrator/janela.py` | Janela de pedido. |
| `extrator/formularios.py` | Opções dos formulários do TabNet (leitura no site e acesso). |
| `extrator/opcoes_formularios.json` | Opções de todos os campos dos 112 formulários. |
| `extrator/pedido.py` | Pedido → plano de consultas e layout da planilha. |
| `extrator/tabnet.py` | Uma consulta no site: preenchimento conferido, leitura, validação e evidências. |
| `extrator/coleta.py` | Execução do plano com retomada. |
| `extrator/planilha.py` | Planilha a partir dos resultados, com as abas EVIDÊNCIAS e _MAPA. |
| `extrator/conferencia.py` | Conferência independente pelos PDFs. |
| `extrator/rodar.py` | Execução completa e sem supervisão. |
| `extrator/comum.py` | Gravação atômica, conferência de cópias e prevenção de suspensão. |
| `ferramentas/` | Conferências contra o site: a janela mostra tudo o que os formulários têm, e como o site soma seleções múltiplas. |
| `tests/` | Testes (pytest), sem acesso ao site, com respostas reais do site guardadas em `tests/dados/`. |

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

Os testes rodam no GitHub Actions a cada push, no Windows e no Ubuntu. Os scripts de `ferramentas/` acessam o site e por isso rodam só à mão:

```bash
python ferramentas/verificar_formularios.py
```

## Particularidades do TabNet

- Números em formato brasileiro (`6.252,36`); `-` é zero e `...` é dado não disponível (os dois viram SR).
- Sem dados, o site devolve só "Nenhum registro selecionado", sem título nem período: a evidência passa a ser também o print do formulário conferido.
- O servidor oscila: cada consulta tem até 10 tentativas com espera crescente.
- O site devolve os conteúdos na ordem dele; a planilha casa cada coluna pelo nome.
- Dados dos últimos seis meses estão sujeitos a atualização no site.

## Versão anterior

A coleta fixa de internações por arritmia (rodada de Jul/2025 a Ago/2026) está na tag [`v1.0.0`](https://github.com/victorsimasdev/datasus-extractor/releases/tag/v1.0.0). O mesmo pedido agora se monta na janela; o arquivo `tests/dados/pedido_fa.json` é esse pedido.

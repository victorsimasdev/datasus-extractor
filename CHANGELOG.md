# Changelog

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [2.0.0] - não lançada

Coleta genérica: qualquer pedido montado na janela, em quatro bases do TabNet.

### Adicionado
- Pacote `extrator`, executado com `python -m extrator`: janela de pedido, plano de consultas, coleta com evidências e retomada, planilha e conferência independente pelos PDFs.
- Bases: internações (SIH), mortalidade (SIM), nascidos vivos (SINASC) e produção ambulatorial (SIA), no Brasil inteiro ou dentro de estados.
- Filtros e períodos com opções separadas, grupos somados pelo site e blocos de colunas na planilha.
- Planilha em três formatos, com as abas EVIDÊNCIAS e _MAPA (origem de cada célula).
- Validação de cada resultado no título da página (período e filtros) e registro de somas que não batem com o TOTAL do site.

### Alterado
- SR passa a valer também para `-` (zero) e `...` (dado não disponível); linhas zeradas são sempre exibidas.
- A coleta usa https.

### Removido
- Scripts da coleta fixa (rodada 1 e por perfil), atalhos `.bat`, envio ao Drive, migração entre computadores e janela de progresso antiga: o pacote faz o mesmo de forma genérica.

## [1.0.0] - 2026-11-10

Primeira versão publicada: coleta de Jul/2025 a Ago/2026 (rodada 1 e rodada por perfil), com as melhorias de robustez abaixo.

### Adicionado
- Módulo `comum.py` com gravação atômica de JSON, leitura que detecta arquivo corrompido, conferência de cópias por SHA-256 e prevenção de suspensão que só age no Windows.
- `rodar_noite.py` roda a conferência independente pelos PDFs (`conferir_evidencias.py`) antes de concluir.
- Testes unitários com pytest e lint com ruff, executados no GitHub Actions.
- `pyproject.toml`, `requirements-dev.txt` e todas as dependências com versão fixa.

### Corrigido
- A coleta da rodada 1 e a correção de `verificar_retomada.py` gravavam o JSON diretamente; uma interrupção podia corrompê-lo.
- `rodar_perfil.py` tratava um JSON corrompido como vazio e ficava em ciclo de tentativas até o limite de 120 h.
- `conferir_evidencias.py` e `conferir_perfil.py` saíam com código 0 mesmo encontrando erros.
- `conferir_evidencias.py` parava com exceção quando faltava o PDF nacional por Região.
- `preencher_planilha.py` saía com código 0 com problemas nas conferências, e a rodada 1 era marcada como concluída.
- O envio ao Drive e a exportação para outro computador conferiam as cópias só pelo tamanho.
- A legenda dos PNG dependia do caminho fixo `C:/Windows/Fonts/arial.ttf`.

[2.0.0]: https://github.com/victorsimasdev/datasus-extractor/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/victorsimasdev/datasus-extractor/releases/tag/v1.0.0

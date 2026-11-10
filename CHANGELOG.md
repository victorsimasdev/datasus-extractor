# Changelog

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Ao abrir, o executável verifica se há versão nova nas releases e pergunta se quer instalar agora: baixa, confere o SHA-256, troca o `ExtratorDATASUS.exe` e abre a versão nova sozinho. Não instala com coleta em andamento.

### Corrigido
- Atualização: a troca do executável não depende mais do PATH (um `find.exe` do Git fazia a versão nova abrir antes de a antiga fechar, com o aviso "já está aberto"), e a verificação não falha quando sobra o exe antigo em uso.

## [2.0.0] - 2026-11-10

Coleta genérica: qualquer pedido montado na interface, em quatro bases do TabNet.

### Adicionado
- Pacote `extrator`, executado com `python -m extrator`: interface de pedido, plano de consultas, coleta com evidências e retomada, planilha e conferência independente pelos PDFs.
- Bases: internações (SIH), mortalidade (SIM), nascidos vivos (SINASC) e produção ambulatorial (SIA), no Brasil inteiro ou dentro de estados.
- Filtros e períodos com opções separadas, grupos somados pelo site e blocos de colunas na planilha.
- Planilha em três formatos, com as abas EVIDÊNCIAS e _MAPA (origem de cada célula).
- Validação de cada resultado no título da página (período e filtros) e registro de somas que não batem com o TOTAL do site.
- Fila de coletas com histórico (tela "Minhas coletas" e comandos `fila` e `coletas`): uma coleta por vez, com progresso, parar, continuar e reordenar.
- Interface em HTML numa janela de desktop (pywebview): Painel, Novo pedido em 6 passos com prévia da planilha, Minhas coletas com registro ao vivo e Configurações. A janela Tkinter continua em `python -m extrator classica`.
- Temas claro, escuro e "seguir o Windows" (Ctrl+D alterna), com barra de título escura no Windows.
- Ícone do programa na janela e na barra de tarefas, e atalhos de teclado para os passos e as coletas.
- Só uma janela do programa aberta por vez.
- Executável do Windows (`ExtratorDATASUS.exe`) com `LEIA-ME.txt`, para usar sem instalar Python.
- A coleta usa o Microsoft Edge quando o Google Chrome não está instalado.
- Licença MIT, política de segurança e releases automáticas a cada merge na main (tag e release com o executável anexado).

### Alterado
- SR passa a valer também para `-` (zero) e `...` (dado não disponível); linhas zeradas são sempre exibidas.
- A coleta usa https.
- A janela abre centralizada e lembra o tamanho e o tema.
- Dependências: pypdf 7.0.0 e pywebview 6.2.1.

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

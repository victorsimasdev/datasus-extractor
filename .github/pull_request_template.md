## O que muda

<!-- O que este PR faz e por quê. Se resolve uma issue, escreva "Resolve #123". -->

## Tipo de mudança

<!-- O título do PR e cada commit seguem o padrão "tipo: descrição" em português.
     O tipo dos commits decide a próxima versão (release automática a cada merge na main):
     release: ou tipo!: -> X.0.0 · feat: -> x.Y.0 · fix: ou requirements.txt -> x.y.Z · o resto não gera versão -->

- [ ] `feat`: funcionalidade nova
- [ ] `fix`: correção de erro
- [ ] `release` / `feat!`: mudança incompatível (pedidos ou planilhas antigos deixam de funcionar)
- [ ] `docs`, `test`, `ci`, `refactor` ou `chore`: sem efeito para quem usa o programa

## Como testei

<!-- O que você rodou e o resultado. Para mudanças na coleta, uma coleta real pequena ajuda muito. -->

- [ ] `ruff check .` sem erros
- [ ] `pytest` passando
- [ ] Coleta real (se mexeu na coleta, na planilha ou na conferência): `python ferramentas/regressao.py`
- [ ] Abri a janela e conferi a tela (se mexeu na interface)
- [ ] Gerei o executável (se mexeu em `empacotamento/` ou nas dependências): `python empacotamento/gerar_exe.py`

## Antes do merge

- [ ] Commits no padrão `tipo: descrição`, em português
- [ ] README, LEIA-ME (`empacotamento/LEIA-ME.txt`) ou CHANGELOG atualizados, se a mudança aparece para quem usa
- [ ] Sem dados pessoais, senhas ou tokens nos arquivos

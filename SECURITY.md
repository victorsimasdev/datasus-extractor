# Segurança

## Versões com suporte

Só a versão mais recente (a da branch `main` e a última release) recebe correções.

## Como relatar uma vulnerabilidade

Não abra uma issue pública. Use o relato privado do GitHub: aba **Security** → **Report a vulnerability**.

Inclua, se possível:

- o que acontece e o impacto;
- os passos para reproduzir;
- a versão do programa e do Windows/Python.

A resposta inicial vem em até 7 dias. Quando a correção sair, o relato é publicado com o crédito para quem avisou (se quiser).

## Escopo

O programa roda na máquina de quem usa, acessa só o site público do TabNet/DATASUS e não guarda senhas nem dados pessoais. Interessam principalmente:

- execução de código a partir de um `pedido.json` ou de arquivos da pasta de saída;
- escrita de arquivos fora da pasta escolhida;
- dependências com vulnerabilidade conhecida.

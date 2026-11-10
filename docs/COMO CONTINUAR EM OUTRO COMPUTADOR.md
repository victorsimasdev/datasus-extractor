# Como interromper a coleta e continuar em outro computador

## ⭐ Jeito simples: 2 cliques

**No computador atual:**
1. Dê duplo clique em **`1 - PARAR E EXPORTAR.bat`**.
2. Escolha onde salvar (pendrive, HD externo...) e confirme.
   O programa para a coleta, confere os dados, copia tudo e confere a cópia arquivo a arquivo.
   Espere a mensagem **"Pronto"**.

**No computador novo:**
3. Copie para ele a pasta **`FA INTERNAÇÕES - DATASUS - CÓDIGO`** que foi salva no pendrive. Pode ficar em qualquer local.
4. Dentro dela, dê duplo clique em **`2 - CONTINUAR AQUI.bat`**.
   O programa instala o Python, o Chrome e as bibliotecas, se faltarem, confere a cópia (o que tiver perdido evidência volta para a fila), retoma a coleta de onde parou, arma o envio ao Drive e abre a janela de progresso.
   Espere a mensagem **"Coleta retomada"**.

Para acompanhar depois: **`ABRIR PROGRESSO.bat`**.

> ⚠️ Depois de exportar, **não** rode a coleta de novo no computador antigo. Nunca deixe dois computadores coletando ao mesmo tempo.

O restante deste guia é o passo a passo manual, para o caso de algo no jeito simples falhar.

---

Tudo o que já foi coletado fica gravado em **`dados_perfil.json`** (valores lidos do site) e na pasta **`evidencias_perfil/`** (PDF + PNG de cada consulta). O JSON é salvo a cada consulta concluída, e a gravação é segura: interromper no meio nunca deixa o arquivo corrompido. Uma consulta interrompida no meio simplesmente não é salva e é refeita na retomada.

> ⚠️ **Nunca rode a coleta em dois computadores ao mesmo tempo.** Cada um gravaria o seu próprio `dados_perfil.json`, e um sobrescreveria o outro.

---

## Parte 1: no computador atual (parar)

**1. Pare a coleta e o envio ao Drive.** Abra o **PowerShell** e cole:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'rodar_perfil|coletar_perfil|enviar_drive' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

**2. Confira se parou.** O comando abaixo não deve listar nada:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'rodar_perfil|coletar_perfil|enviar_drive' }
```

**3. Veja quanto já foi coletado** (opcional):

```powershell
cd "D:\FA INTERNAÇÕES - DATASUS - CÓDIGO"; python verificar_retomada.py
```

**4. Copie a pasta INTEIRA** `D:\FA INTERNAÇÕES - DATASUS - CÓDIGO` para um pendrive ou HD externo. Para ser mais rápido, compacte antes: botão direito → *Enviar para → Pasta compactada*.
O que **não pode faltar**:

| Item | Para quê |
|---|---|
| `dados_perfil.json` | tudo o que já foi lido do site (**o mais importante**) |
| `evidencias_perfil/` | PDF e PNG de cada consulta já feita |
| `ENTREGA ANTERIOR (Jul-2025 a Ago-2026)/` | planilha e evidências da rodada anterior (colunas B–E) |
| `FA - INTERNAÇÕES (modelo perfil).xlsx` | modelo da planilha (colunas H–U) |
| todos os arquivos `.py` e `requirements.txt` | o programa |

Se não quiser usar pendrive, dá para copiar pelo Google Drive. Nesse caso, copie para uma pasta **diferente** da pasta de entrega (por exemplo, `Meu Drive\BACKUP COLETA PERFIL`) e espere a sincronização terminar (ícone do Drive sem setas girando) antes de desligar.

---

## Parte 2: no computador novo (preparar, uma única vez)

**5. Instale:**
- **Python 3.12 ou 3.13** (python.org). Na instalação, marque **"Add python.exe to PATH"**.
- **Google Chrome**.
- **Google Drive para Desktop**, entrando na mesma conta do Google (necessário só para o envio automático no final).

**6. Cole a pasta** em qualquer local, por exemplo `D:\FA INTERNAÇÕES - DATASUS - CÓDIGO`. O caminho pode ser diferente do computador antigo, porque o programa usa caminhos relativos à própria pasta.

**7. Instale as bibliotecas.** No PowerShell, dentro da pasta:

```powershell
cd "D:\FA INTERNAÇÕES - DATASUS - CÓDIGO"
python -m pip install -r requirements.txt
```

---

## Parte 3: no computador novo (conferir e retomar)

**8. Confira a cópia:**

```powershell
python verificar_retomada.py
```

- Se aparecer **"OK: pode retomar a coleta."**, siga para o passo 9.
- Se aparecer **"Sem evidência (precisam ser refeitas): N"** (a cópia perdeu algum arquivo), rode o comando abaixo. Ele tira essas consultas do JSON (guardando um backup) para que sejam consultadas de novo:

  ```powershell
  python verificar_retomada.py --corrigir
  ```

**9. Teste rápido** (opcional, cerca de 5 minutos). Confirma que o Chrome e o site funcionam nesse computador:

```powershell
python coletar_perfil.py --demo
```

Ele deve terminar com `Concluído.` Esse teste grava em `dados_perfil_demo.json`, separado da coleta real.

**10. Retome a coleta** (em segundo plano, sem janela):

```powershell
$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath python -ArgumentList '-u','rodar_perfil.py' -WorkingDirectory (Get-Location) -WindowStyle Hidden
```

**11. Arme o envio automático ao Drive.** Ele só envia se a validação final der **0 erros**:

```powershell
$env:PYTHONIOENCODING='utf-8'; Start-Process -FilePath python -ArgumentList '-u','enviar_drive.py','--perfil' -WorkingDirectory (Get-Location) -WindowStyle Hidden
```

**12. Acompanhe** quando quiser:

```powershell
Get-Content status_perfil.json            # fase e quantas consultas já foram feitas
Get-Content execucao_perfil.log -Tail 10  # últimas linhas da coleta
Get-Content status_drive_perfil.json      # situação do envio ao Drive
```

O executor impede o Windows de suspender enquanto roda. Deixe o PC ligado e com internet.

---

## No final

- `status_perfil.json` com `"fase": "concluido"` significa que a coleta terminou, a planilha foi gerada e **as duas validações pelos PDFs deram 0 erros**. A entrega fica em `ENTREGA - FA INTERNAÇÕES POR PERFIL DATASUS/`, com o relatório `RELATÓRIO DE CONFERÊNCIA - PERFIL.txt`.
- `"fase": "erro"` significa que algo divergiu ou faltou. **Nada é enviado ao Drive.** Abra o relatório para ver exatamente o que foi.
- `status_drive_perfil.json` com `"fase": "concluido"` e `"com_problema": []` significa que o Drive foi atualizado e conferido arquivo a arquivo.

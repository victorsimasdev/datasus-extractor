"""
Confere, antes de retomar a coleta (ex.: depois de copiar a pasta para outro computador),
se tudo o que está em dados_perfil.json tem as suas evidências na pasta.

- Consulta salva com PDF/PNG (ou print do formulário, se "sem registro") presentes -> mantida.
- Consulta salva sem algum desses arquivos -> listada; com --corrigir, é retirada do JSON
  (cópia de segurança em dados_perfil.backup-AAAAMMDD-HHMMSS.json) para ser consultada de novo.
Nunca apaga evidências.

Uso:
  python verificar_retomada.py             -> só mostra o resultado
  python verificar_retomada.py --corrigir  -> retira do JSON as consultas sem evidência
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from coletar_perfil import chave, todos_casos, todos_nacionais

PASTA = Path(__file__).resolve().parent
ARQ = PASTA / "dados_perfil.json"


def main():
    if not ARQ.exists():
        sys.exit("dados_perfil.json não encontrado: a coleta começaria do zero. Confira se a pasta foi copiada inteira.")
    try:
        dados = json.loads(ARQ.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"dados_perfil.json corrompido ({e}). Use a cópia do computador anterior.")

    sem_evidencia = []
    for k, r in dados.items():
        arquivos = [r["pdf"], r["png"]] + ([r["png_formulario"]] if r.get("sem_registro") else [])
        faltam = [a for a in arquivos if not a or not (PASTA / a).is_file()]
        if faltam:
            sem_evidencia.append((k, faltam))

    total = len(todos_casos()) + len(todos_nacionais())
    validas = len(dados) - len(sem_evidencia)
    print(f"Consultas salvas: {len(dados)} de {total}")
    print(f"Com evidência completa: {validas}")
    print(f"Sem evidência (precisam ser refeitas): {len(sem_evidencia)}")
    for k, f in sem_evidencia:
        print(f"  {k}: falta {', '.join(f)}")
    print(f"Faltam coletar depois da retomada: {total - validas}")

    if sem_evidencia and "--corrigir" in sys.argv:
        backup = PASTA / f"dados_perfil.backup-{datetime.now():%Y%m%d-%H%M%S}.json"
        shutil.copy2(ARQ, backup)
        for k, _ in sem_evidencia:
            del dados[k]
        ARQ.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Retiradas do JSON: {len(sem_evidencia)} (cópia de segurança: {backup.name})")
    elif sem_evidencia:
        print("Rode com --corrigir para que essas consultas sejam feitas de novo.")
    else:
        print("OK: pode retomar a coleta.")


if __name__ == "__main__":
    main()

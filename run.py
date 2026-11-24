from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    print("🎓 Iniciando Assistente de Matrícula UFABC (BCC)")
    print("👉 Acesse no navegador: http://127.0.0.1:8000")
    print("🔒 Tudo roda 100% localmente na sua máquina.")
    uvicorn.run("src.web.app:app", host="127.0.0.1", port=8000, reload=False)

# 🎓 Assistente de Matrícula UFABC — BCC (PPC 2023)

Ferramenta **100% local** para facilitar a montagem da grade quadrimestral da UFABC (Bacharelado em Ciência da Computação — Matriz 2023), cruzando automaticamente:

- **Turmas Ofertadas** do quadrimestre ([PROGRAD Matrículas](https://prograd.ufabc.edu.br/matriculas))
- **Catálogo de Disciplinas** mais recente ([PROGRAD Catálogos](https://prograd.ufabc.edu.br/catalogos-de-disciplinas)) para checar **recomendações (pré-requisitos)**
- **Projeto Pedagógico do BCC 2023** + **Rol de Opções Limitadas** ([PROGRAD BCC](https://prograd.ufabc.edu.br/cursos/17))
- **Seu Histórico Escolar** (processado localmente, sem salvar dados pessoais)

## 🔒 Privacidade (CPF, RG, RA)
- Seu PDF do histórico **nunca** é enviado para a internet nem salvo na pasta do projeto.
- Ao importar pelo navegador (ou via `sanitizar_historico.py`), o PDF é lido apenas em memória, **descarta nome, CPF, RG, RA e cabeçalho** e salva somente um JSON anônimo com os códigos/nomes das matérias cursadas (e em curso) em `data/privado/materias_cursadas.json` (já ignorado no `.gitignore`).
- Também é possível colar apenas a lista de disciplinas do SIGAA, sem nem selecionar o PDF.

## 🚀 Como rodar (você ou seus amigos)

```bash
cd ufabc-matricula
python3 -m venv .venv
source .venv/bin/activate   # No Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 run.py
```

Depois abra no navegador: **http://127.0.0.1:8000**

## 🧭 Recursos
- Filtros dinâmicos por **Campus** (Santo André / São Bernardo / Todos), **Turno** (Matutino / Noturno / Todos), **Categoria** (Obrigatórias BCC, BC&T, Opções Limitadas, Livres) e busca por nome/código/professor.
- Opção **"Contar matérias em curso como feitas"** (ativa por padrão).
- Badges automáticos de recomendações (🟢 OK / 🟡 Parcial / 🔴 Pendente) mostrando exatamente qual recomendação falta.
- **Grade semanal visual (Seg–Sáb)** com detecção automática de conflito de horários (inclusive aulas quinzenais Q1/Q2).
- Botão **"Atualizar PDFs PROGRAD"** para baixar automaticamente os arquivos mais recentes nos próximos quadrimestres.
- Botão **"Copiar códigos"** para levar sua grade pronta para o portal de matrícula.

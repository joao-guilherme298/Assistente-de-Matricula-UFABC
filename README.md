# 🎓 Assistente de Matrícula UFABC — BCC (PPC 2023)

🌐 **Acesse direto no navegador (sem instalar nada):**
👉 **[https://joao-guilherme298.github.io/Assistente-de-Matricula-UFABC/](https://joao-guilherme298.github.io/Assistente-de-Matricula-UFABC/)**

Ferramenta **100% local e privada** para facilitar a montagem da grade quadrimestral da UFABC (Bacharelado em Ciência da Computação — Matriz 2023), cruzando automaticamente:

- **Turmas Ofertadas** do quadrimestre ([PROGRAD Matrículas](https://prograd.ufabc.edu.br/matriculas))
- **Catálogo de Disciplinas** mais recente ([PROGRAD Catálogos](https://prograd.ufabc.edu.br/catalogos-de-disciplinas)) para checar **recomendações (pré-requisitos)**
- **Projeto Pedagógico do BCC 2023** + **Rol de Opções Limitadas** ([PROGRAD BCC](https://prograd.ufabc.edu.br/cursos/17))
- **Seu Histórico Escolar** (processado localmente, sem salvar dados pessoais)

## 🔒 Privacidade (CPF, RG, RA)
- Seu PDF do histórico **nunca** é enviado para a internet nem salvo na pasta do projeto.
- Ao importar pelo navegador (ou via `sanitizar_historico.py`), o PDF é lido apenas em memória, **descarta nome, CPF, RG, RA e cabeçalho** e salva somente um JSON anônimo com os códigos/nomes das matérias cursadas (e em curso) em `data/privado/materias_cursadas.json` (já ignorado no `.gitignore`).
- Também é possível colar apenas a lista de disciplinas do SIGAA, sem nem selecionar o PDF.

## 🚀 Como rodar no seu computador

### Pré-requisitos
- **Python 3.9+** instalado ([python.org](https://www.python.org/downloads/))

### 1. Baixe o projeto
```bash
git clone https://github.com/joao-guilherme298/Assistente-de-Matricula-UFABC.git
cd Assistente-de-Matricula-UFABC
```

### 2. Instale as dependências e inicie

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

**Windows (PowerShell ou CMD):**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

### 3. Abra no navegador
Com o servidor rodando, acesse **[http://localhost:8000](http://localhost:8000)** (roda 100% no seu computador):
1. Clique em **"🔒 Importar Histórico"** e envie o PDF do seu histórico do SIGAA (ou cole o texto das disciplinas).
2. Selecione o seu **Campus** e **Turno** nos filtros.
3. Clique em **"+ Adicionar"** nas turmas para montar sua grade semanal sem conflitos de horário.

> **Dica para os próximos quadrimestres:** clique em **"🔄 Atualizar PDFs PROGRAD"** no topo da página para baixar automaticamente a nova lista de turmas ofertadas.

## 🧭 Recursos
- Filtros dinâmicos por **Campus** (Santo André / São Bernardo / Todos), **Turno** (Matutino / Noturno / Todos), **Categoria** (Obrigatórias BCC, BC&T, Opções Limitadas, Livres) e busca por nome/código/professor.
- Opção **"Contar matérias em curso como feitas"** (ativa por padrão).
- Badges automáticos de recomendações (🟢 OK / 🟡 Parcial / 🔴 Pendente) mostrando exatamente qual recomendação falta.
- **Grade semanal visual (Seg–Sáb)** com detecção automática de conflito de horários (inclusive aulas quinzenais Q1/Q2).
- Botão **"Atualizar PDFs PROGRAD"** para baixar automaticamente os arquivos mais recentes nos próximos quadrimestres.
- Botão **"Copiar códigos"** para levar sua grade pronta para o portal de matrícula.

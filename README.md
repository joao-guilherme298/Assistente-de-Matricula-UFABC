# 🎓 Assistente de Matrícula UFABC

[![CI](https://github.com/joao-guilherme298/Assistente-de-Matricula-UFABC/actions/workflows/ci.yml/badge.svg)](https://github.com/joao-guilherme298/Assistente-de-Matricula-UFABC/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

🌐 **Acesse direto no navegador (sem instalar nada):**
👉 **[https://joao-guilherme298.github.io/Assistente-de-Matricula-UFABC/](https://joao-guilherme298.github.io/Assistente-de-Matricula-UFABC/)**

Ferramenta **100% local e privada** para facilitar a montagem da grade quadrimestral da UFABC (suporte a todos os cursos da UFABC, com matriz curricular completa do BCC — PPC 2023 e BC&T), cruzando automaticamente:

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
- **Todos os cursos da UFABC**: seletor de curso, **Campus** (Santo André / São Bernardo / Todos), **Turno** (Matutino / Noturno / Todos), **Categoria**, **Dias da semana** (`Seg`–`Sáb`) e busca por nome/código/professor.
- **Turmas agrupadas por disciplina** com visualização de **Objetivos e Ementa oficial** ao clicar no nome da matéria.
- **Recomendações e Destravamento**: badges automáticos (🟢 OK / 🟡 Parcial / 🔴 Pendente) e selo `🔓 Destrava N` indicando quantas matérias futuras dependem dela.
- **Opção "Contar matérias em curso como feitas"** (ativa por padrão).
- **Grade semanal visual** com abas **Plano A / B / C**, alternância **Todas | Quinzenal I | Quinzenal II** e detecção automática de conflito de horários.
- **Sugestão automática (`✨ Sugerir grade`)** com opção de completar créditos restantes com livres/limitadas mais leves.
- **Exportação**: imagem **`.png`** (por semana Q1/Q2/Todas), calendário **`.ics`** (Google/Apple Calendar) e cópia rápida dos códigos de matrícula.

# Futebol Analytics

Projeto pessoal em desenvolvimento para coletar, armazenar e analisar dados de futebol com Python.

## O que este projeto demonstra

- Integração com APIs HTTP e arquivos CSV.
- Tratamento de dados e persistência em PostgreSQL.
- Análises estatísticas, modelos de probabilidade e avaliação histórica.
- Interface em Streamlit e testes automatizados no código-fonte.

## Conhecer a solução

| Etapa | Código |
| --- | --- |
| Coleta e validação | [Clientes de API](src/futebol_analytics/api/) |
| Armazenamento | [Persistência e migrações](src/futebol_analytics/database/) |
| Análises | [Módulos analíticos](src/futebol_analytics/analysis/) |
| Interface | [Aplicação Streamlit](src/futebol_analytics/web_app.py) |
| Verificação | [Testes](tests/) |

## Instalação no Windows

Requer Python 3.11 ou superior. Na raiz do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Preencha no editor somente as variáveis dos provedores e do banco que pretende usar.
Não versione o arquivo `.env`.

```powershell
.\.venv\Scripts\futebol-analytics.exe --help
.\.venv\Scripts\python.exe -m pytest
```

Algumas funcionalidades exigem banco configurado ou assinatura de um provedor.
A existência dos testes no repositório não substitui a verificação no ambiente de execução.

## Escopo e limitações

A disponibilidade e a atualização dos dados dependem das fontes e dos planos contratados.
As análises e probabilidades são experimentais; não representam garantia de acerto ou retorno financeiro.
A documentação técnica registra etapas históricas: datas, contagens de testes e resultados de coletas são registros daquela execução.

## Documentação

- [Guia técnico e histórico de implementação](docs/GUIA_TECNICO.md)
- [Fluxo de desenvolvimento](WORKFLOW.md)
- [Variáveis de ambiente de exemplo](.env.example)

O guia preserva as instruções técnicas e limitações anteriores. Os comandos nele apresentados devem ser executados a partir da raiz do repositório.

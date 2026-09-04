# Futebol Analytics

Projeto educacional para coletar dados da API Dados Futebol. Nesta primeira
etapa, o programa valida a API Key, lista campeonatos e localiza dinamicamente
o Brasileirão Série A de 2026.

## Estrutura atual

- `api/`: comunicação HTTP e erros da integração;
- `config/`: leitura e validação das variáveis de ambiente;
- `services/`: casos de uso que não pertencem ao transporte HTTP;
- `main.py`: interface de linha de comando;
- `tests/`: testes sem consumo da API real.

Pastas de banco de dados e análise serão adicionadas somente quando esses
recursos forem implementados.

## Preparação no Windows PowerShell

Requer Python 3.12 ou mais recente.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

## Configuração

O arquivo `.env` local já foi criado e está ignorado pelo Git. Preencha nele:

```dotenv
DADOS_FUTEBOL_API_KEY=sua_chave_aqui
DADOS_FUTEBOL_BASE_URL=https://api.dadosfutebol.com.br
```

Nunca publique ou envie o conteúdo do `.env`. O `.env.example` serve como
modelo seguro para outras instalações.

## Execução

Com o ambiente virtual ativado:

```powershell
futebol-analytics perfil
futebol-analytics campeonatos --temporada 2026
futebol-analytics brasileirao --temporada 2026
futebol-analytics rodadas --campeonato-id 3 --numero 38
futebol-analytics tabela --campeonato-id 3
futebol-analytics analisar-time --campeonato-id 3 --time-id 1 --jogos 5
futebol-analytics analisar-time --campeonato-id 3 --time-id 1 --jogos 10 --mando mandante
futebol-analytics analisar-time --campeonato-id 3 --time-id 1 --jogos 10 --mando visitante
```

O endpoint de rodadas devolve todas as rodadas em uma requisição. A opção
`--numero` é um filtro aplicado pelo programa depois que o JSON é recebido; ela
evita imprimir o campeonato inteiro no terminal e não representa um parâmetro
da API.

Também é possível executar o módulo diretamente:

```powershell
python -m futebol_analytics.main perfil
```

## Testes

```powershell
python -m pytest -q
```

Os testes usam respostas HTTP simuladas. Eles não enviam a API Key nem gastam
o limite de requisições.

## Interface web

Com o ambiente virtual ativado, execute:

```powershell
streamlit run src/futebol_analytics/web_app.py
```

A aplicação abrirá no navegador, normalmente em `http://localhost:8501`. A
navegação possui uma página de classificação e outra de análises, que identifica a próxima rodada,
lista suas partidas e compara o mandante em casa com o visitante fora. Os jogos
usados nos cálculos e os confrontos diretos disponíveis ficam visíveis para
auditoria da amostra. A comparação também inclui um simulador manual de odds
para 1X2, ambas marcam e totais de 1.5, 2.5 ou 3.5 gols. Ele calcula
probabilidades implícitas e a margem teórica do mercado, sem integração com
casas de apostas.
As respostas da API ficam em cache por 60 segundos para evitar consumo
desnecessário do limite do plano.

## Documentação consultada

- [Introdução](https://docs.dadosfutebol.com.br/introduction)
- [Autenticação e limites](https://docs.dadosfutebol.com.br/autenticacao)
- [Campeonatos](https://docs.dadosfutebol.com.br/campeonatos)
- [Perfil da API Key](https://docs.dadosfutebol.com.br/api-reference/perfil/perfil-da-api-key)

# Futebol Analytics

Plataforma de inteligência estatística aplicada ao futebol brasileiro, em construção.
A Fase 1 implementa a integração com a API Dados Futebol. A primeira entrega da
Fase 2 adiciona PostgreSQL para guardar capturas e consultá-las localmente.
A Fase 3 calcula estatísticas descritivas dos jogos normalizados, com filtros
e exclusões explícitos.
A Fase 4 começou com `poisson_v1` e agora inclui avaliações retrospectivas
experimentais e um painel Streamlit. O piloto de over 2,5 para Premier e
Brasileirão está documentado em `WORKFLOW.md`. Ainda não há modelo calibrado
para indicações de aposta, odds pré-jogo integradas ou IA interpretativa.

O caminho do produto será: dados → tratamento → estatística → modelos →
probabilidades → backtesting → IA para interpretação. Números deverão vir de
dados e cálculos verificáveis; a IA futura não será a origem das probabilidades.

## Instalação no Windows (PowerShell)

Requer Python 3.11 ou superior. Execute na raiz deste projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Preencha a chave apenas no editor local. Não a cole no chat nem em comandos.
Mantenha a URL `https://api.dadosfutebol.com.br`, sem `/v1`: o cliente acrescenta
o prefixo. O timeout padrão é 20 segundos. Não é necessário ativar o ambiente
virtual: os comandos abaixo usam seu executável diretamente.

`.env` é ignorado pelo Git. Variáveis do processo têm prioridade sobre o arquivo.
O arquivo carregado é `.env` da pasta atual, sem procurar em pastas superiores.
O programa não imprime a chave, headers ou corpos de erro; o comando de validação
também não imprime o perfil. Não habilite logs HTTP de depuração com credenciais reais.

## Consultas

```powershell
.\.venv\Scripts\futebol-analytics.exe --help
.\.venv\Scripts\futebol-analytics.exe validar-chave
.\.venv\Scripts\futebol-analytics.exe campeonatos --temporada 2026
.\.venv\Scripts\futebol-analytics.exe brasileirao --temporada 2026
.\.venv\Scripts\futebol-analytics.exe tabela
.\.venv\Scripts\futebol-analytics.exe partidas --status encerrado --por-pagina 10
.\.venv\Scripts\futebol-analytics.exe partidas --pagina 2 --por-pagina 10
```

Para consultar estatísticas, use um ID retornado em `data[].id` da consulta de
partidas. No exemplo abaixo, substitua o marcador por esse número:

```text
.\.venv\Scripts\futebol-analytics.exe estatisticas <ID_DA_PARTIDA>
```

`tabela` e `partidas` localizam a Série A 2026 quando não se fornece
`--campeonato-id`. Um ID explícito evita repetir a busca e define o campeonato
diretamente, independentemente de `--temporada`. Não há ID fixo no código.
A busca compara nome (ignorando acentos e caixa) e temporada, percorre as páginas
e exige um único resultado. Se o provedor mudar o nome, a busca falha claramente.

`campeonatos` e `partidas` retornam **uma página por comando**, mantendo `meta` para
você consultar a seguinte. Só a localização da Série A percorre automaticamente
as páginas, com limite defensivo de 100 páginas. Cada página consome uma requisição.
Filtros de partidas: `--rodada`, `--status`, `--time-id`, `--data-inicio`,
`--data-fim`; datas em `YYYY-MM-DD`. Parâmetros rejeitados pelo servidor geram erro.

Também é possível executar `python -m futebol_analytics.main` com o Python da
`.venv`. Sucesso retorna código 0; falha de configuração/API retorna 1; argumentos
inválidos da CLI retornam 2.

## Contrato consultado em 08/09/2026

Fontes oficiais:

- [Introdução e parâmetros](https://docs.dadosfutebol.com.br/introduction)
- [Autenticação, acesso e limites](https://docs.dadosfutebol.com.br/autenticacao)
- [Perfil da chave](https://docs.dadosfutebol.com.br/api-reference/perfil/perfil-da-api-key)
- [Campeonatos](https://docs.dadosfutebol.com.br/campeonatos)
- [Tabela](https://docs.dadosfutebol.com.br/api-reference/tabela/tabela-de-classifica%C3%A7%C3%A3o)
- [Partidas e estatísticas](https://docs.dadosfutebol.com.br/partidas)

Todas as consultas implementadas são GET, autenticadas com
`Authorization: Bearer {api_key}`, sobre HTTPS:

| Caminho após a origem | Uso | Resposta |
| --- | --- | --- |
| `/v1/me` | Validar chave; sem parâmetros | `data` objeto; não exibido |
| `/v1/campeonatos` | Temporada e paginação | `data` lista e `meta` |
| `/v1/campeonatos/{id}/partidas` | Partidas e filtros | `data` lista e `meta` |
| `/v1/campeonatos/{id}/tabela` | Classificação; sem query | `data` objeto com `classificacao` |
| `/v1/partidas/{id}/estatisticas` | Estatísticas; sem query | `data` objeto com `estatisticas` por lado |

Paginação: `pagina` começa em 1; `por_pagina` aceita 1–100 (padrão do servidor: 15).
O envelope paginado inclui `total`, `por_pagina`, `pagina_atual`, `ultima_pagina`.
O cliente valida a estrutura necessária e preserva os demais campos do provedor.

A página de autenticação informa Free: 100 requisições/dia e 3.000/mês;
Pro: 1.000/dia e 30.000/mês; Enterprise: limites personalizados. Free permite
campeonatos e tabela, mas bloqueia partidas e estatísticas. Os limites podem mudar:
consulte seu plano. O cliente expõe os headers `X-RateLimit-Limit` e
`X-RateLimit-Remaining` em `client.rate_limit`, quando presentes.

Não há repetição automática das chamadas, inclusive em HTTP 429, para evitar
consumir cota sem controle. Redirecionamentos não são seguidos. HTTP 401 indica
chave inválida/inativa; 403 indica acesso insuficiente; 404 indica recurso ou dados
indisponíveis; 422 indica parâmetros rejeitados; 429 indica cota atingida.
Timeout, conexão, JSON inválido e envelope inesperado também são tratados.

Estatísticas são exibidas como recebidas. `null` significa não informado e não
é convertido em zero. A documentação descreve finalizações, cartões, escanteios
e métricas avançadas como `gols_esperados`, dependentes da fonte. Um 404 pode
significar ausência de estatísticas para aquela partida.

Há divergências entre páginas da documentação: o índice descreve posse como
nula, enquanto a página de partidas mostra valores; o exemplo de `/me` apresenta
limites diferentes da página de autenticação. Não usamos exemplos para assegurar
cobertura, cota ou IDs reais. A confirmação operacional depende da resposta com
a chave e o plano do usuário.

## Estrutura e responsabilidades

```text
futebol_analytics/
├── src/futebol_analytics/
│   ├── __init__.py
│   ├── analysis/
│   │   ├── __init__.py
│   │   └── team.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── football_csv.py
│   │   └── exceptions.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── migrations.py
│   │   ├── normalized.py
│   │   ├── statistics.py
│   │   ├── forecast.py
│   │   ├── csv_store.py
│   │   └── store.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── poisson.py
│   ├── local_data.py
│   ├── sync.py
│   └── main.py
├── tests/
│   ├── test_client.py
│   ├── test_analysis.py
│   ├── test_poisson.py
│   ├── test_football_csv.py
│   ├── test_database.py
│   ├── test_local_data.py
│   ├── test_sync.py
│   └── test_settings.py
├── compose.yaml
├── reports/auditoria_local.json
├── reports/flamengo_serie_a_2026.json
├── reports/poisson_v1_partida_2973.json
├── reports/premier_csv_importacao.json
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
└── README.md
```

`.venv/` e o seu futuro `.env` são locais e não entram no versionamento.
`pyproject.toml` define o pacote, as dependências de execução e o comando.
`requirements.txt` instala o pacote em modo editável e o pytest para desenvolvimento.
As faixas de versões limitam atualizações maiores; ainda não há lockfile de todas
as dependências transitivas.

## Guia de aprendizado do código

1. **Módulos, pacotes e imports:** cada `.py` é um módulo; `__init__.py` identifica
   um pacote. `import httpx` carrega a biblioteca HTTP; `from ... import Settings`
   reutiliza a configuração. Só `api/client.py` realiza chamadas HTTP.
2. **Variáveis de ambiente:** `load_settings()` combina o `.env` com `os.environ`.
   São strings externas ao código. `float()` converte o timeout, e sua validação
   impede valores negativos, infinitos ou inválidos.
3. **Classe de configuração:** `Settings` usa `@dataclass(frozen=True)` para
   agrupar dados sem permitir alterações usuais após a criação. `repr=False`
   exclui a chave da representação do objeto. Isso não é criptografia.
4. **Classe e `__init__`:** `DadosFutebolClient` agrupa conexão e comportamento.
   `__init__` cria a conexão com URL, Bearer, headers e timeout. `self` é a instância.
   Escolhemos uma classe porque a conexão tem estado e precisa ser encerrada.
5. **Métodos, funções, parâmetros e retorno:** `consultar_tabela(id)` é um método;
   `load_settings()` é uma função independente. O ID é um parâmetro e o JSON
   convertido é o retorno. `*` exige parâmetros nomeados para evitar confusões.
6. **Type hints:** `int`, `str`, `float`, `dict[str, Any]` e `str | None` documentam
   os tipos esperados; não validam automaticamente os dados em execução.
   `-> None` indica que o método não retorna um resultado útil. Mantemos
   dicionários para evitar modelar prematuramente todo o contrato externo.
7. **HTTP e JSON:** GET solicita dados; headers transportam autenticação e formato;
   query parameters filtram a consulta. `response.json()` converte JSON em listas
   e dicionários Python. `json.dumps()` faz o caminho inverso para exibição.
8. **Exceptions:** `raise` sinaliza uma falha; `try/except` permite à CLI tratá-la.
   Erros da biblioteca viram erros da aplicação com mensagens controladas.
   `from None` evita exibir detalhes internos na cadeia de exceções.
9. **Context manager:** `with DadosFutebolClient(settings) as client` chama
   `__enter__` ao entrar e `__exit__` ao sair, inclusive com exceção. A saída fecha
   conexões. Não precisamos implementar hierarquias ou factories para isso.
10. **Testes e baixo acoplamento:** o parâmetro opcional `transport` permite passar
    `httpx.MockTransport`. O mesmo cliente recebe respostas simuladas sem internet.
    Testes conferem comportamento, erros e paginação. Fixtures preparam ambientes
    isolados; `pytest.mark.parametrize` aplica o mesmo teste a vários casos.

Escolhemos cliente síncrono em vez de async porque os comandos são sequenciais.
Escolhemos JSON preservado em vez de dezenas de classes de resposta porque ainda
estamos conhecendo a fonte. `main.py` coordena entrada e saída; `config/` configura;
`api/` se comunica com o provedor. Na Fase 2, `database/` concentra o SQL e
`sync.py` coordena coleta e persistência. Ainda não precisamos de uma hierarquia
de services ou repositories.

## Verificação e limite desta entrega

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Os testes são locais, com dados fictícios, e não demonstram acesso à produção.
Cobrem paginação, seleção única da Série A, filtros, erros HTTP/rede/JSON,
preservação de valores nulos, fechamento da conexão e configuração.

A chave configurada localmente foi validada pelo servidor. A primeira coleta real
gravou 5 campeonatos de 2026 e a tabela da Série A (ID 3 retornado pela API).
Partidas retornou HTTP 403: a credencial atual não permite acessar esse recurso.
Estatísticas não foram consultadas nesta validação. Nenhuma credencial é registrada
neste documento.

Na resposta real, campeonatos trouxe somente `meta.total`, sem os campos de
paginação documentados. O cliente aceita esse formato apenas na primeira página
e quando a quantidade recebida coincide com o total. Preserva os metadados originais
e continua rejeitando listas incompletas ou paginação inconsistente.

## Fase 2 — primeiras capturas no PostgreSQL

Esta entrega inicia a base histórica com JSONB. Uma captura guarda um recurso
completo, o escopo (temporada ou ID), a origem, horários com fuso e um UUID.
As páginas de listagens são mantidas em `conteudo.paginas`, incluindo seus
metadados. Tabela e estatísticas mantêm o envelope original em `conteudo`.
`null` continua sendo dado ausente. JSONB preserva o conteúdo estruturado,
mas não a formatação ou a ordem das chaves do texto JSON original.

A evolução local descrita ao final deste README acrescenta tabelas relacionais
de campeonatos por temporada, times e partidas com resultados. Escalações e os
demais recursos permanecem nas capturas quando disponíveis. Previsões e versões
de modelos ainda não são persistidas em tabelas próprias. Capturas são histórico de coleta,
não backtesting nem histórico completo
do futebol: só temos o que foi efetivamente sincronizado.

### Preparar o PostgreSQL local

Requer Docker Desktop iniciado com containers Linux, ou um PostgreSQL já disponível.
Atualize as dependências com `python -m pip install -r requirements.txt` usando a
`.venv`. Se já existe `.env`, acrescente as variáveis novas sem sobrescrever a chave.

No `.env`, configure `POSTGRES_USER=futebol`, `POSTGRES_DB=futebol_analytics`,
uma senha em `POSTGRES_PASSWORD` e `FUTEBOL_DATABASE_URL` no formato:

```text
postgresql://usuario:senha@127.0.0.1:5433/futebol_analytics
```

Use a mesma senha na URL e no Compose. Caracteres especiais da senha dentro da URL
precisam de percent-encoding. Para facilitar o ambiente local, uma senha aleatória
longa com letras e números evita essa conversão. Não exponha a URL completa em logs.
Os campos de credenciais são omitidos do `repr` da configuração.

```powershell
docker compose up -d --wait
.\.venv\Scripts\futebol-analytics.exe banco-iniciar
```

O Compose usa PostgreSQL 17, volume persistente e porta 5433 somente em loopback.
Usamos `127.0.0.1` explicitamente na URL para evitar tentativas IPv6 quando
`localhost` resolve primeiro para `::1` no Windows.
`banco-iniciar` cria a tabela e o índice dentro do banco existente; não cria o
servidor nem o database. É seguro repetir o comando: não apaga capturas.
Com servidor próprio, basta configurar `FUTEBOL_DATABASE_URL`; as variáveis
`POSTGRES_*` são usadas apenas pelo Compose. Em servidor remoto configure TLS
conforme as instruções do provedor, por exemplo `sslmode=verify-full` e a CA.

`docker compose stop` interrompe o serviço preservando o volume. Alterar a senha
no `.env` não muda a senha de um banco já inicializado: as variáveis de inicialização
do container só se aplicam a um volume novo. O volume fornece persistência local;
backups ainda precisam ser definidos antes de guardar histórico importante.

### Sincronizar e consultar

```powershell
.\.venv\Scripts\futebol-analytics.exe sincronizar campeonatos 2026
.\.venv\Scripts\futebol-analytics.exe local campeonatos 2026
.\.venv\Scripts\futebol-analytics.exe historico campeonatos 2026
```

Os demais comandos exigem IDs reais retornados pela API:

```text
futebol-analytics sincronizar tabela <ID_CAMPEONATO>
futebol-analytics sincronizar partidas <ID_CAMPEONATO> --max-paginas 10
futebol-analytics sincronizar estatisticas <ID_PARTIDA>
futebol-analytics local partidas <ID_CAMPEONATO>
futebol-analytics historico partidas <ID_CAMPEONATO> --limite 20
futebol-analytics local partidas <ID_CAMPEONATO> --captura-id <UUID>
```

Execute esses comandos pelo executável da `.venv`, como nos exemplos anteriores.
`sincronizar` consulta a API explicitamente; `local` e `historico` nunca a consultam,
mesmo que não haja captura. As consultas diretas da Fase 1 continuam acessando a API
e não gravam automaticamente. Não há cache com expiração nem agendador nesta versão.

Uma sincronização de campeonatos coleta a temporada inteira; partidas coleta todo
o campeonato, com 100 itens por página. Não são aceitos filtros parciais nesse fluxo.
O limite de páginas evita consumo inesperado; não é um limite global de requisições.
Se alguma página falhar, mudar de total ou tiver IDs duplicados, nenhuma captura
nova é gravada. A anterior permanece disponível. A API não oferece aqui uma
transação entre páginas: atualizações que mantêm o mesmo total podem ocorrer
durante a coleta. Os horários delimitam esse intervalo, sem prometer uma visão
instantânea perfeitamente consistente da fonte.

Cada sincronização bem-sucedida gera uma nova captura, mesmo que os dados sejam
iguais: registra uma nova observação. Não há deduplicação de capturas. A leitura
padrão ordena pelo fim da coleta, horário de gravação e UUID; o ID permite consultar
uma versão específica. O histórico mostra até 100 entradas por consulta.
O aplicativo não oferece edição nem exclusão de capturas, mas isso não constitui
um registro inviolável: administradores do PostgreSQL ainda podem alterá-las.

### Conceitos novos

- `psycopg.connect()` abre a conexão. O `with` confirma a transação em caso de
  sucesso, desfaz alterações em caso de erro e fecha a conexão.
- `@contextmanager` transforma `_connection()` em um contexto reutilizável;
  `yield` entrega a conexão ao código que a usa. Erros do driver são traduzidos
  sem imprimir detalhes potencialmente sensíveis.
- `execute(SQL, parametros)` envia valores separados do SQL. Isso permite tratar
  apóstrofos e outros caracteres sem montar consultas por concatenação.
- `Jsonb(payload)` adapta dicionários Python ao tipo JSONB do PostgreSQL.
- Chave primária identifica cada captura; o índice acelera a busca por recurso,
  escopo e data; `CHECK` protege regras essenciais dentro do banco.
- A gravação ocorre depois da coleta HTTP. Assim não mantemos uma transação de
  banco aberta durante várias requisições de rede.

O DDL inicial fica em `store.py`. As alterações posteriores ficam em
`database/migrations.py`, com versões registradas em `futebol_migracoes`.
A migração 2 amplia os recursos permitidos para incluir `rodadas` e `artilharia`.
`banco-iniciar` aplica a alteração e seu registro em uma única transação, preservando
as capturas existentes. Um advisory lock serializa inicializações concorrentes.
Repetir o comando não reaplica a migração. Ainda não há reversão automática.

Referências: [Psycopg e transações](https://www.psycopg.org/psycopg3/docs/basic/usage.html),
[JSONB](https://www.postgresql.org/docs/current/datatype-json.html) e
[imagem oficial PostgreSQL](https://hub.docker.com/_/postgres).

### Teste de integração

Na validação inicial da Fase 2, os **48 testes passaram**, incluindo o teste com
PostgreSQL 17 real em Docker. Após o ajuste ao formato real da API, a suíte ganhou
6 casos de regressão para listas sem paginação. O banco do projeto já contém as
primeiras capturas reais de campeonatos e classificação. Preserve o `.env` local,
que contém as credenciais configuradas. O banco `futebol_analytics_test` foi criado
separadamente para os testes.

`pytest -q` executa os testes locais. O teste PostgreSQL é marcado `integration`
e só executa se `FUTEBOL_TEST_DATABASE_URL` apontar para um banco de testes dedicado.
Ele verifica criação repetida do esquema, gravação, histórico, nulos e rollback.
Usa um escopo aleatório e remove somente os registros desse escopo ao terminar.
Não use uma base de produção para os testes.

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration -q
```

A normalização da Fase 2 e a primeira entrega da Fase 3 estão descritas abaixo.

## Coleta dos recursos disponíveis no plano atual

Foram adicionadas consultas GET sem parâmetros de query:
`/v1/campeonatos/{id}/rodadas` e `/v1/campeonatos/{id}/artilharia`.
Ambas são permitidas no Free conforme a
[documentação de autenticação](https://docs.dadosfutebol.com.br/autenticacao).
As respostas trazem `data` como lista e `meta.total`; preservamos o envelope.
Rodadas inclui os jogos em `data[].partidas`. Isso permite coletar os jogos
fornecidos nessa rota, embora o endpoint direto `/partidas` retorne 403.
Não significa acesso a estatísticas detalhadas nem cobertura completa de todas
as fases das competições. Consulte a
[referência de campeonatos](https://docs.dadosfutebol.com.br/campeonatos).

Resultado verificado no PostgreSQL após a coleta:

| Campeonato | Classificação | Rodadas | Jogos recebidos | Artilharia recebida |
| --- | --- | ---: | ---: | --- |
| Série A | 20 equipes | 38 | 380 | 50 registros |
| Série B | 20 equipes | 38 | 380 | 50 registros |
| Série C | 20 equipes | 19 | 214 | Lista vazia |
| Série D | Formato incompatível; não gravada | 13 | 504 | Pendente: HTTP 429 |
| Copa do Brasil | Não solicitada: mata-mata | Pendente | Pendente | Pendente |

São **1.478 registros de jogos**, com IDs únicos dentro de cada campeonato.
Incluem jogos encerrados, aguardando e adiados; não representam 1.478 resultados
finalizados. A lista vazia de artilharia da Série C indica o que a API retornou,
sem comprovar ausência de artilheiros. Os rankings de 50 registros são o conteúdo
recebido, sem garantia de que incluam todos os jogadores com gols.

Ao consultar artilharia da Série D, a API retornou **429**, então as chamadas
foram interrompidas sem tentativas automáticas. A resposta rejeitada da tabela
da Série D não foi gravada; seu formato precisa ser inspecionado quando houver
cota. A classificação já existente da Série A foi reutilizada.

Consultar os dados salvos **não consome API**:

```powershell
.\.venv\Scripts\futebol-analytics.exe local rodadas 3
.\.venv\Scripts\futebol-analytics.exe local artilharia 3
.\.venv\Scripts\futebol-analytics.exe local tabela 4
```

Quando a cota renovar, estas são as consultas pendentes (cada uma acessa a API):

```powershell
.\.venv\Scripts\futebol-analytics.exe sincronizar artilharia 61
.\.venv\Scripts\futebol-analytics.exe sincronizar rodadas 62
.\.venv\Scripts\futebol-analytics.exe sincronizar artilharia 62
```

Não há uma retomada agendada. O endpoint de rodadas pode retornar vazio para
mata-mata; esse resultado será preservado sem inventar jogos. A ampliação foi
validada com **62 testes passando**, incluindo PostgreSQL real, preservação dos
dados anteriores à migração e execução única da alteração do esquema.

## Fase 2 — organização e auditoria sem novas chamadas à API

A migração 3 cria uma projeção relacional das capturas já existentes:

| Tabela | Identificação | Conteúdo |
| --- | --- | --- |
| `futebol_campeonatos` | origem, ID, temporada | Nome, tipo e captura do catálogo |
| `futebol_times` | origem, ID | Nome, sigla e captura de origem |
| `futebol_partidas` | origem, campeonato, temporada, ID | Times, rodada, status, data/hora e placares |

Todas mantêm `captura_id` como chave estrangeira para `futebol_capturas`.
Os times e o campeonato referenciados por cada partida também são protegidos
por chaves estrangeiras. A origem faz parte das chaves para não misturar IDs
caso outra fonte seja adicionada. O ID de campeonato é combinado com temporada,
pois o provedor pode reutilizá-lo em anos diferentes.

```powershell
.\.venv\Scripts\futebol-analytics.exe banco-iniciar
.\.venv\Scripts\futebol-analytics.exe normalizar-local
.\.venv\Scripts\futebol-analytics.exe auditar-local
```

Nenhum desses comandos carrega a API Key ou acessa a API. `normalizar-local`
reconstrói somente as três tabelas derivadas em uma transação. Uma falha desfaz
as alterações, preservando a projeção anterior. As capturas não são editadas
nem excluídas. Não altere manualmente as tabelas derivadas: a próxima reconstrução
substituirá essas alterações. Não há duplicação ao repetir o comando.

`auditar-local` examina as capturas e produz o relatório no terminal, sem gravar
a projeção. O relatório desta execução está em
[reports/auditoria_local.json](reports/auditoria_local.json); ele não se atualiza
automaticamente quando o comando é executado novamente.

Resultado verificado após a normalização local:

- 5 campeonatos por temporada, 156 times e 1.478 partidas gravadas.
- Nenhuma duplicata de ID por origem/campeonato/temporada nas rodadas selecionadas.
- 12 partidas sem `data_hora_realizacao`; não foi inventado um horário.
- 1 partida da Série D (ID 9594) marcada encerrada sem placar completo.
- 1.212 partidas encerradas com ambos os placares; isso não garante que todas
  tenham data/hora disponível ou estejam livres de outros problemas.
- Copa do Brasil sem captura de rodadas, portanto sem partidas normalizadas.

As datas ausentes podem refletir falta de agendamento ou de cobertura; os placares
ausentes continuam SQL NULL. Não representam zero. Não usamos essas contagens
para afirmar completude do calendário ou qualidade perfeita da fonte.

### Como a transformação funciona

`local_data.py` contém uma função pura: recebe capturas, retorna registros e
ocorrências, sem rede ou SQL. `LocalDataset` é uma dataclass que agrupa esse retorno.
Dicionários indexados por chaves compostas permitem detectar IDs duplicados.
Uma repetição idêntica gera aviso e um único registro; duplicatas conflitantes
ficam fora da projeção e são indicadas no relatório.

A transformação usa a última captura de rodadas por origem/escopo. Associa a
temporada usando o catálogo mais recente coletado antes do início dessas rodadas;
se não existir, sinaliza a falta em vez de adivinhar o ano. Atualmente, a projeção
representa a última observação de cada escopo, e não todas as temporadas históricas
das rodadas. As observações anteriores continuam preservadas nos JSONs.

Somente times presentes nas rodadas são extraídos nesta versão; times exclusivos
de classificações ou artilharia ainda não são incorporados. Nomes e siglas refletem
a última observação processada. O relatório verifica identificação, duplicatas,
datas, status, placares e cobertura local; não reconcilia tabelas oficiais,
confrontos por fase ou estatísticas de jogadores. Classificação e artilharia
continuam disponíveis nos JSONs, sem novas tabelas específicas.

`database/normalized.py` concentra a persistência. SQL parametrizado mantém os
valores separados dos comandos. `REPEATABLE READ` fornece uma visão consistente
das capturas durante a operação e a transação publica as três tabelas em conjunto.
Em concorrência, uma falha de serialização pode exigir executar novamente; não há
repetição automática. A migração 3 cria as tabelas uma única vez.

A suíte passou com **71 testes**, incluindo banco real, preservação das capturas,
reconstrução repetida, rollback, nulos, fuso horário e duplicatas conflitantes.
A primeira entrega da Fase 3, autorizada após esta auditoria, está descrita abaixo.

## Fase 3 — estatística descritiva local

`analysis/team.py` calcula resultados e frequências sem banco, HTTP ou IA.
`database/statistics.py` lê as partidas normalizadas e seus metadados de coleta.
`main.py` reúne parâmetros, leitura e exibição. Nenhuma nova tabela ou dependência
é necessária para esta etapa.

Descubra os IDs disponíveis na base e consulte um time:

```powershell
.\.venv\Scripts\futebol-analytics.exe times-local --campeonato-id 3
.\.venv\Scripts\futebol-analytics.exe analisar-time 1 --campeonato-id 3
.\.venv\Scripts\futebol-analytics.exe analisar-time 1 --campeonato-id 3 --ultimos 5
.\.venv\Scripts\futebol-analytics.exe analisar-time 1 --campeonato-id 3 --ultimos 10
.\.venv\Scripts\futebol-analytics.exe analisar-time 1 --campeonato-id 3 --mando mandante
.\.venv\Scripts\futebol-analytics.exe analisar-time 1 --campeonato-id 3 --mando visitante
.\.venv\Scripts\futebol-analytics.exe analisar-time 1 --campeonato-id 3 --adversario-id 2
```

Os IDs 1 e 2 foram identificados no banco local como Flamengo e Palmeiras; não
são fixados nas funções. `--temporada` tem padrão 2026. O parâmetro `--origem`
seleciona a fonte dentro do banco; não faz requisições à URL. O confronto direto
fica restrito ao campeonato e à temporada escolhidos.

### Regras da amostra aprovadas

Primeiro selecionamos campeonato, temporada, time, mando e adversário. Depois:

1. Excluímos jogos não encerrados.
2. Excluímos placares incompletos, negativos ou inválidos.
3. Excluímos jogos com data posterior à coleta apesar de marcados encerrados.
4. Para `--ultimos`, excluímos também jogos sem data/hora.
5. Ordenamos os elegíveis por data e selecionamos os últimos 5 ou 10. Em empate
   exato de horário, o ID serve apenas como desempate determinístico.

Sem `--ultimos`, jogos encerrados com placar completo e data ausente podem
participar dos totais e médias. A quantidade aparece em `utilizados_sem_data`.
A sequência de forma retorna `null` se algum jogo utilizado não puder ser
ordenado. Quando disponível, a forma vai do mais antigo ao mais recente.

Cada excluído recebe o primeiro motivo aplicável, evitando contagens duplicadas.
O relatório lista os IDs utilizados, excluídos e fora da janela. Assim:

```text
encontrados_no_recorte = utilizados + excluidos_por_criterio + fora_da_janela
```

Os filtros de mando/adversário definem o recorte inicial; jogos fora desse recorte
não são considerados erros de qualidade. Uma janela com menos de N jogos válidos
mostra `janela_completa: false`. Nunca completamos a amostra com dados fictícios.
"Últimos" significa últimos jogos válidos disponíveis, podendo pular lacunas;
não garante os últimos jogos reais de um calendário externamente verificado.

### Métricas e fórmulas

- Vitórias, empates e derrotas: comparação dos gols a favor e contra do time.
- Médias de gols marcados/sofridos: respectiva soma dividida pelos jogos utilizados.
- Média total por jogo: soma dos gols dos dois lados dividida pelos jogos utilizados.
- Over 0.5/1.5/2.5/3.5: frequência de jogos cujo total de gols supera o limiar.
- Ambas marcam: os dois lados têm pelo menos um gol.
- Sem sofrer gols: o adversário tem zero gols, incluindo empates em 0 a 0.

Cada frequência traz ocorrências, denominador e percentual (`100 × ocorrências / N`).
Percentuais são arredondados para duas casas e médias para quatro. Com amostra
vazia, contagens são zero e médias/percentuais são `null`, não 0%.
Os placares utilizados são os campos disponíveis na projeção; não somamos
disputas de pênaltis nem inferimos separação de prorrogação ausente na fonte.

Essas são frequências históricas, **não probabilidades de jogos futuros**.
O identificador `estatistica_descritiva_v1` descreve a metodologia, não um modelo
preditivo. O relatório mostra as datas de coleta; não representa informação ao vivo.
Não há corte retrospectivo, versionamento de previsões nem backtesting nesta etapa.

### Exemplo calculado e validação

[reports/flamengo_serie_a_2026.json](reports/flamengo_serie_a_2026.json) contém os
recortes geral, últimos 5, últimos 10, mandante e visitante do Flamengo, calculados
com os dados coletados em 08/09/2026. O arquivo é um exemplo estático; use a CLI
para recalcular após novas normalizações.

No recorte geral, 26 jogos foram utilizados e 12 não encerrados foram excluídos:
16 vitórias, 6 empates, 4 derrotas, 51 gols marcados e 21 sofridos.
Nos últimos 5 válidos: 4 vitórias, 1 derrota, 12 gols marcados e 3 sofridos.
Esses resultados descrevem exclusivamente a captura local.

Foram aprovados **81 testes**, incluindo cálculos conferidos manualmente, inversão
de mando, amostra vazia, exclusões, janela recente e leitura do PostgreSQL real.
Conceitos novos: funções puras facilitam testes; `Counter` conta resultados;
compreensões selecionam valores; parâmetros nomeados explicitam filtros; SQL
parametrizado mantém a leitura separada dos cálculos.

Finalizações, posse, escanteios, cartões e xG ainda não são calculados porque não
foram coletados dados detalhados suficientes. A primeira versão matemática da
Fase 4, autorizada após esta etapa, está descrita abaixo.

## Fase 4 — modelo Poisson v1

`models/poisson.py` contém as funções matemáticas, sem SQL ou rede.
`database/forecast.py` lê uma partida futura e os jogos da mesma origem,
campeonato e temporada. São consultas exclusivamente locais, sem API Key.
Não há nova dependência: usamos `math.exp` e uma recorrência numérica.

```powershell
.\.venv\Scripts\futebol-analytics.exe proximas-locais --campeonato-id 3
.\.venv\Scripts\futebol-analytics.exe prever-partida 2973 --campeonato-id 3
```

A listagem retorna até 20 partidas futuras com status `aguardando` na captura.
O exemplo 2973 é Coritiba x Athletico Paranaense, agendado na base para
11/09/2026 às 21h de Brasília (12/09/2026 00h UTC). Quando o horário passar,
o comando recusará a previsão; selecione outro ID da listagem local. A agenda
não foi reconfirmada na API e pode mudar.

### Seleção dos dados

O modelo usa a temporada disponível inteira, por mando, com pesos iguais.
O jogo-alvo não entra na amostra. Só entram jogos encerrados, com placares
completos e não negativos, data/hora conhecida e anterior ao cálculo. A data
do jogo não pode estar depois da captura que o apresenta como encerrado;
capturas posteriores ao cálculo também são rejeitadas.

O alvo deve ser futuro, com data conhecida e status `aguardando` na base.
Exigimos ao menos 20 jogos válidos da liga, 5 do mandante em casa e 5 do visitante
fora. Esses limites são escolhas iniciais, não resultados de calibração.
Com amostra insuficiente ou médias de liga iguais a zero, o modelo não produz
probabilidades. A versão atual não realiza previsões retrospectivas pela CLI.

### Das médias aos gols esperados

Defina `L_casa` e `L_fora` como as médias de gols dos mandantes e visitantes
em todos os jogos válidos da liga. As forças relativas são:

```text
ataque_casa = média de gols marcados pelo mandante em casa / L_casa
defesa_casa = média de gols sofridos pelo mandante em casa / L_fora
ataque_fora = média de gols marcados pelo visitante fora / L_fora
defesa_fora = média de gols sofridos pelo visitante fora / L_casa

lambda_casa = L_casa × ataque_casa × defesa_fora
lambda_fora = L_fora × ataque_fora × defesa_casa
```

Aqui, defesa maior que 1 significa sofrer mais gols que a média de referência.
O mando já está incorporado nas médias e nos recortes; não acrescentamos um
segundo bônus arbitrário. As médias não têm regularização nesta primeira versão,
portanto podem ser instáveis em amostras pequenas ou gerar zero para equipes
sem gols no recorte.

`lambda` é a média esperada de gols do modelo. **Não é o xG de finalizações**
coletado por um provedor de eventos. A partir dela usamos:

```text
P(gols = k) = exp(-lambda) × lambda^k / k!
```

Referência da distribuição:
[documentação matemática do SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.poisson.html).
O programa não depende do SciPy: começa com `P(0)=exp(-lambda)` e calcula
`P(k)=P(k-1)×lambda/k`. Cada distribuição é expandida até a massa omitida ser
menor que aproximadamente 10⁻¹². A implementação aceita médias de 0 a 20;
valores maiores geram erro para revisão dos dados, sem truncar a média silenciosamente.

Assumimos gols independentes: `P(placar h:a) = P(casa=h) × P(fora=a)`.
Somamos as células correspondentes para vitória, empate, derrota, Over
0.5/1.5/2.5/3.5 e ambas marcam. A matriz finita é normalizada; a massa omitida
antes desse ajuste aparece em `precisao_numerica`. Os cinco placares de maior
probabilidade são exibidos como cenários, não como resultados garantidos.

### Transparência e limites

As probabilidades no JSON vão de 0 a 1; multiplique por 100 para obter percentual.
O relatório inclui versão, horário do cálculo, parâmetros, amostras por mando,
IDs dos jogos usados/excluídos, IDs das capturas e SHA-256 dos dados de treinamento.
O hash ajuda a identificar o conjunto utilizado; não prova autenticidade ou
imutabilidade. Alterações de fórmula ou critérios exigirão uma nova versão.

`confianca` é `null`: não confundimos probabilidade calculada com confiança no
modelo. Não há taxa de acerto, calibração ou comparação comprovada com outro
modelo. O modelo pressupõe forças constantes e não considera escalações,
lesões, mudanças de técnico, dependência entre gols ou correção de placares baixos.

Embora o filtro temporal proteja o cálculo atual, isso não é um backtest:
a projeção relacional contém a última observação local, e capturas posteriores
não devem ser usadas para simular conhecimento no passado. Esse tratamento
exigirá um fluxo específico na Fase 5.

### Exemplo e testes

[reports/poisson_v1_partida_2973.json](reports/poisson_v1_partida_2973.json) guarda
uma saída demonstrativa calculada com a captura local de 08/09/2026:

- 256 jogos válidos da liga; 13 do Coritiba em casa e 13 do Athletico fora.
- Gols esperados do modelo: aproximadamente 1,1391 e 1,2493.
- Probabilidades calculadas: mandante 33,48%, empate 27,69%, visitante 38,83%.

O arquivo é um artefato de demonstração. Não há registro imutável de previsões
no PostgreSQL nem auditoria de acertos nesta fase. O comando recalcula a saída
usando a projeção local disponível e o horário atual.

**101 testes passaram**, incluindo massa da distribuição, casos de média zero,
simetria, confronto com fórmulas analíticas, médias conferidas manualmente,
exclusões, amostra insuficiente e bloqueio de partidas passadas. O fluxo real
também foi executado no PostgreSQL local para a partida 2973.

A próxima fase é o registro e a avaliação das previsões. Antes de afirmar
qualidade preditiva, precisaremos medir desempenho e calibração com histórico
verificável. Nenhum modelo de machine learning ou IA foi acrescentado.

## Fonte gratuita adicional — Premier League com estatísticas

A [Football-Data.co.uk](https://football-data.co.uk/englandm.php) publica arquivos
CSV gratuitos para download. É uma fonte diferente da football-data.org e não
exige API Key. A importação usa os links publicados para a Premier League (E0):

- [2026/2027](https://football-data.co.uk/mmz4281/2627/E0.csv)
- [2025/2026](https://football-data.co.uk/mmz4281/2526/E0.csv)

Nesta coleta foram gravados **410 jogos** no PostgreSQL:

| Temporada | Jogos | Primeira data | Última data de jogo no arquivo |
| --- | ---: | --- | --- |
| 2026/2027 | 30 | 21/08/2026 | 06/09/2026 |
| 2025/2026 | 380 | 15/08/2025 | 24/05/2026 |

Todos os registros recebidos têm gols, escanteios, amarelos, vermelhos,
finalizações e finalizações no alvo para ambos os lados. Isso comprova preenchimento
dos campos recebidos, não valida a exatidão de cada estatística contra outra fonte.
A página consultada em 14/09/2026 indica atualização em 10/09/2026, mas o CSV atual
termina em 06/09/2026. Portanto, esta fonte **não oferece cobertura ao vivo ou
garantia de resultados do último fim de semana** nesta coleta.

| Colunas do CSV | Campos locais |
| --- | --- |
| FTHG / FTAG | gols_mandante / gols_visitante |
| HC / AC | escanteios_mandante / escanteios_visitante |
| HY / AY | amarelos_mandante / amarelos_visitante |
| HR / AR | vermelhos_mandante / vermelhos_visitante |
| HS / AS | finalizacoes_mandante / finalizacoes_visitante |
| HST / AST | finalizacoes_alvo_mandante / finalizacoes_alvo_visitante |

Os amarelos e vermelhos são preservados separadamente, sem criar uma regra de
liquidação de apostas ou presumir como cada provedor conta um segundo amarelo.
O CSV original completo permanece disponível no banco. Veja também o
[dicionário publicado pela fonte](https://football-data.co.uk/notes.txt).

### Consultar e atualizar

```powershell
.\.venv\Scripts\futebol-analytics.exe premier-local --temporada 2026/2027
.\.venv\Scripts\futebol-analytics.exe premier-local --temporada 2025/2026
```

Esses comandos usam somente o PostgreSQL e exibem jogos, estatísticas, origem,
datas de observação e cobertura por campo. O relatório da primeira importação
está em [reports/premier_csv_importacao.json](reports/premier_csv_importacao.json).

Para buscar uma nova versão, execute explicitamente:

```powershell
.\.venv\Scripts\futebol-analytics.exe importar-premier-csv --temporada 2026/2027
```

Esse comando acessa o CSV público, sem consumir a cota da API brasileira.
Não há polling, repetição automática em HTTP 429 nem busca automática de outras
ligas. O importador atual está limitado à Premier League e ao formato verificado.

### Organização da nova fonte

`api/football_csv.py` concentra download e interpretação: `csv.DictReader`
converte cada linha em dicionário; o mapa `FIELDS` traduz os campos verificados;
datas são interpretadas como dia/mês/ano. Campo vazio vira `None`, enquanto zero
permanece zero. Arquivos vazios, linhas duplicadas, colunas ausentes e números
inválidos são rejeitados antes da gravação.

`database/csv_store.py` grava a importação inteira em uma transação. A migração 4
acrescenta `futebol_csv_arquivos` (CSV original, SHA-256, origem e temporada) e
`futebol_csv_jogos` (data, nomes dos times e estatísticas em JSONB).
Arquivos idênticos não duplicam jogos; atualizam a última observação. Conteúdo
alterado gera outra versão, preservando a anterior. `premier-local` seleciona
a versão observada mais recentemente. O hash se refere ao texto UTF-8 decodificado,
não a uma assinatura de autenticidade da fonte.

Esses dados não são apagados por `normalizar-local`. Como o CSV não traz os mesmos
IDs da API brasileira, não inventamos equivalências de times e partidas. A chave
de cada jogo dentro da versão é data + mandante + visitante. Uma mudança de nome
ou data aparece na nova versão; ainda não há reconciliação entre versões/fontes.
Os comandos `analisar-time` e `prever-partida` continuam usando a projeção anterior;
a integração das estatísticas da Premier nesse motor será uma etapa posterior.
Não inferimos fuso horário a partir do campo Time: nesta projeção usamos a data.

**110 testes passaram**, incluindo importação no PostgreSQL, idempotência,
campos ausentes, preservação de zero e rejeição de duplicatas. Nenhuma chave da
API brasileira foi usada para coletar esses dados.

## Betano: diagnóstico e comparação experimental de odds

Em 14/09/2026, o acesso à página pública com Chromium/Playwright recebeu
**HTTP 403**. O registro está em `reports/betano_diagnostico.json`.
**A coleta de odds e o agendamento diário ainda não estão funcionando.**
O diagnóstico não possui extrator validado: mesmo HTTP 200 é insuficiente
para confirmar que odds foram obtidas. Não há login, uso do perfil pessoal,
tentativas de contornar bloqueios ou execução de apostas.

Instalação do componente opcional, conforme a
[documentação do Playwright](https://playwright.dev/python/docs/library):

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[browser]'
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\futebol-analytics.exe diagnosticar-betano --saida reports/betano_diagnostico.json
```

O diagnóstico faz uma tentativa, grava status, horário UTC e código HTTP e
retorna código de saída 2 enquanto a coleta não estiver validada. Isso permite
a um futuro agendador distinguir uma falha de uma análise sem candidatos.

O comando independente `analisar-odds-local` compara cotações fornecidas em JSON
com o Poisson da base brasileira. Não acessa a Betano nem a API paga. A fonte CSV
internacional ainda não está ligada a esse modelo. Exemplo **fictício de formato**,
que exige substituir IDs, nomes, datas, URL e cotação pelos dados conferidos:

```json
[
  {
    "partida_id": 1,
    "campeonato_id": 3,
    "temporada": "2026",
    "mandante": "Nome exato do mandante na base",
    "visitante": "Nome exato do visitante na base",
    "data_hora": "2026-09-14T20:00:00-03:00",
    "observado_em": "2026-09-14T10:00:00-03:00",
    "url": "https://www.betano.bet.br/",
    "periodo": "tempo_regulamentar",
    "mercado": "mandante",
    "odd": 1.5
  }
]
```

```powershell
.\.venv\Scripts\futebol-analytics.exe analisar-odds-local cotacoes.json --saida reports/analise_odds.json
```

Use `proximas-locais --campeonato-id 3 --temporada 2026` para consultar IDs e
nomes existentes. A ligação é explícita: IDs, nomes (ignorando acentos e caixa),
mando e horário devem corresponder. Não há associação aproximada de equipes.
Mercados aceitos: `mandante`, `empate`, `visitante`, `over_0.5`, `over_1.5`,
`over_2.5`, `over_3.5`, `ambas_marcam` (sim), sempre no tempo regulamentar.
Escanteios, cartões, períodos parciais e regras promocionais não são modelados.

A faixa inicial é 1,45–1,55, em torno da odd 1,50 solicitada. A triagem exige
partida futura no dia corrente de São Paulo, odd observada há até 15 minutos,
agenda e última coleta de resultados há até 24 horas. Duplicatas de um mesmo
mercado são rejeitadas. Datas futuras de observação também são rejeitadas.
Esses limites são critérios operacionais, não uma garantia de qualidade da fonte.

O valor esperado teórico por real é `probabilidade_modelo * odd - 1`.
Na odd 1,50, o ponto de equilíbrio é 66,67%; a odd sozinha não demonstra vantagem.
A saída guarda cotações, probabilidades e evidências da previsão, selecionando
até três jogos distintos com valor estimado positivo. Pode selecionar zero.
O ranking é experimental: o modelo ainda não foi calibrado nem validado por
backtesting. Não há recomendação de valor a apostar ou plano de alavancagem.

Verificação desta etapa: 127 testes passaram; três testes de integração com
PostgreSQL foram omitidos por falta da variável de banco de testes. O acesso
real pelo diagnóstico foi verificado separadamente e permaneceu recusado.


## Cinco ligas europeias ? amplia??o de 14/09/2026

O importador CSV agora aceita E0 (Premier League), SP1 (La Liga), I1 (Serie A
italiana), D1 (Bundesliga) e F1 (Ligue 1). Os comandos antigos da Premier
continuam funcionando. Cada liga tem sua pr?pria URL/versionamento; o parser
rejeita um arquivo cuja coluna Div n?o corresponda ? liga solicitada.
N?o foi necess?rio alterar o esquema do banco, pois a origem j? separa arquivos.

```powershell
.\.venv\Scripts\futebol-analytics.exe atualizar-ligas-csv --temporada 2026/2027 --saida reports/ligas_europeias_importacao.json
.\.venv\Scripts\futebol-analytics.exe importar-liga-csv --liga SP1 --temporada 2026/2027
.\.venv\Scripts\futebol-analytics.exe liga-local --liga SP1 --temporada 2026/2027
```

A atualiza??o em lote faz uma consulta por liga, sem repeti??o autom?tica.
Cada importa??o ? transacional e idempotente. Se uma liga falhar, o relat?rio
registra a falha e preserva as demais importa??es. HTTP 429 interrompe o lote;
ligas restantes aparecem em nao_processadas. O comando retorna erro se alguma
importa??o falhar. N?o h? agendamento instalado.

Coleta real de 14/09/2026: E0 30 jogos (at? 06/09), SP1 41 (at? 07/09), I1 30
(at? 07/09), D1 18 (at? 06/09) e F1 27 (at? 06/09): 146 jogos da temporada
2026/27. Todos os 12 campos estat?sticos est?o preenchidos. Veja
[relat?rio da importa??o](reports/ligas_europeias_importacao.json).
A data de consulta n?o ? a data de atualiza??o dos resultados. Os dados
brasileiros e a temporada anterior da Premier foram preservados.

Esta etapa amplia o hist?rico dispon?vel. Ainda n?o integra o CSV ao Poisson
ou ? compara??o de odds, n?o obt?m agenda atual e n?o coleta odds atuais da
Betano. O conte?do integral dos CSVs ? preservado, mas a proje??o de estat?sticas
continua limitada aos 12 campos documentados; odds hist?ricas n?o s?o tratadas
como cota??es atuais. A fonte publica arquivos para uso pessoal e imp?e restri??es
a produtos comerciais e de treinamento: consulte a
[p?gina da fonte](https://football-data.co.uk/data.php) antes de distribuir dados.

Verifica??o: 133 testes passaram, tr?s de integra??o foram omitidos sem a vari?vel
de banco de testes. A importa??o real das cinco ligas foi executada no PostgreSQL.


## APIs atuais: Football-data.org e Sportmonks

Integra??o preparada; valida??o online pendente das chaves pessoais. Fa?a o cadastro
gratuito em https://www.football-data.org/client/register e https://my.sportmonks.com/.
Preencha os campos j? adicionados ao `.env`, sem compartilhar os valores no chat:
`FOOTBALL_DATA_API_KEY` e `SPORTMONKS_API_TOKEN`. N?o s?o a chave de Dados Futebol.

```powershell
.\.venv\Scripts\futebol-analytics.exe coletar-atuais --provedor football-data --data 2026-09-14 --saida reports/football_data_2026-09-14.json
.\.venv\Scripts\futebol-analytics.exe coletar-atuais --provedor sportmonks --data 2026-09-14 --saida reports/sportmonks_2026-09-14.json
```

Substitua a data pela desejada. Cada comando consulta um dia UTC, grava JSON somente
ap?s completar a coleta e n?o altera as tabelas brasileiras ou os CSVs. Football-data
consulta PL, PD, SA, BL1, FL1, BSA e CL (cinco ligas europeias, Brasil e Champions).
Sportmonks consulta as ligas gratuitas 501 e 271, incluindo participantes, placares,
estado e estat?sticas com seus tipos. A disponibilidade real depende do plano.

Uma chamada no Football-data; at? dez p?ginas de 50 registros no Sportmonks.
HTTP 401/403/429 interrompe sem novas tentativas. Segredos eventualmente reproduzidos
na resposta s?o removidos antes da grava??o. URLs de pagina??o n?o s?o seguidas.
Datas de coleta e quantidade de jogos com estat?sticas constam no relat?rio;
lista vazia n?o comprova aus?ncia de jogos fora da cobertura da assinatura.

Ainda n?o h? agendamento, normaliza??o desses provedores no PostgreSQL ou liga??o
com o modelo de apostas. A compara??o entre fontes exige verificar hor?rios,
identidade das equipes e regras das estat?sticas ap?s receber dados reais.
Documenta??o utilizada:
https://docs.football-data.org/general/v4/match.html
https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/fixtures/get-fixtures-by-date


### Teste de navega??o assistida da Betano

```powershell
.\.venv\Scripts\python.exe -m futebol_analytics.api.betano_assisted
```

Abre um Chromium vis?vel com contexto descart?vel por at? dez minutos.
Navegue nas p?ginas p?blicas e clique em "Salvar p?gina para an?lise", no canto
inferior esquerdo. A a??o salva texto renderizado, imagem da ?rea vis?vel e
metadados em `.venv/betano_assistido/` (ignorado pelo Git). N?o fa?a login:
a captura visual pode conter qualquer informa??o que estiver na tela.
N?o coleta cookies ou armazenamento do navegador. Fechar a janela encerra o teste.
N?o contorna bloqueios nem executa apostas. Captura visual n?o significa extra??o
validada de odds; mercado, sele??o e hor?rio ainda precisam de confer?ncia.


O navegador assistido aceita `--url "https://www.betano.bet.br/..."` para abrir
diretamente um endere?o p?blico copiado do navegador habitual. Somente URLs HTTPS
da Betano s?o aceitas. Isso n?o contorna bloqueios nem garante o carregamento.
No diagn?stico sem bot?o injetado, o link Futebol navegou, mas quatro chamadas
XHR retornaram HTTP 403 e houve um erro de JavaScript. HTTP 200 da p?gina inicial
n?o demonstra funcionamento completo da aplica??o.

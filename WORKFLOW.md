# Fluxo diário do Futebol Analytics

Objetivo: consultar agenda e histórico, estimar mercados, selecionar até três
jogos futuros do dia, obter as odds desses mercados e comparar preço com probabilidade.

## Implementado nesta etapa

`python -m futebol_analytics.daily --data 2026-09-14 --saida reports/plano_diario_2026-09-14.json`

O comando consulta dois dias UTC no Football-data.org para abranger o dia em São
Paulo, preserva as respostas em `reports/agendas` e consulta os CSVs no PostgreSQL.
O argumento `--agenda arquivo1.json arquivo2.json` permite usar capturas locais de
até uma hora. O planejamento é operacional: não permite simular data passada como
se fosse uma previsão feita naquele momento.

O baseline novo calcula frequências por mando para gols, ambas marcam, resultado
1X2, escanteios e cartões amarelos. Usa até dez partidas da temporada para cada
equipe no respectivo mando, exclui a data do jogo e exige cinco observações válidas
por equipe e mercado. Dados ausentes não viram zero; confrontos repetidos nos dois
recortes contam uma única vez. A suavização de Laplace evita probabilidades zero
ou um. O intervalo de Wilson descreve a incerteza da frequência histórica.
Esse baseline não substitui o Poisson já existente e não tem acurácia validada.

As cinco ligas CSV estão integradas ao novo planejamento. A ligação entre nomes
é exata e pode ser complementada por `--mapa mapa_times.json`, objeto JSON com
chaves `codigoCSV:IDfootballData` e valores iguais aos nomes no CSV. Exemplo de
formato: `{"E0:123": "Nome conferido no CSV"}`. IDs desse exemplo são fictícios.
Não se usa aproximação de nomes para decidir apostas. Brasil e Sportmonks ainda
precisam de adaptadores próprios neste fluxo; os comandos anteriores continuam disponíveis.

A fila contém até três jogos ordenados pela maior probabilidade do baseline.
Ela não é indicação de aposta. Históricos com último resultado anterior a três
dias são rejeitados por critério operacional conservador, mesmo durante pausas
do campeonato. Esse limite não garante completude da fonte. Cartões amarelos
ficam fora da fila até haver equivalência explícita com a regra da casa.

## Pontos ainda necessários para a rotina completa

1. Conciliar IDs e nomes entre as APIs, os dados brasileiros, CSV e Betano.
2. Completar histórico recente por equipe e mercado; validar as estatísticas
   efetivamente retornadas pela assinatura Sportmonks.
3. Validar extração de odds em páginas de jogos da Betano. A captura assistida
   funciona, mas chamadas internas já retornaram 403. HTTP 200 não comprova leitura.
4. Alimentar a comparação com odd, mercado, período, jogo e horário confirmados.
   A fórmula é `probabilidade * odd - 1`; a maior probabilidade não garante a
   melhor aposta. Usar no máximo três jogos, podendo indicar nenhum.
5. Fazer backtesting temporal e calibração antes de chamar o ranking de vantagem
   comprovada. Nenhuma execução de apostas ou progressão de banca é prevista.

## Validação e comparação manual no painel

Na aba integrada, a avaliação cronológica de over 2,5 mostra Brier do baseline por
mando e da frequência geral da liga, além de faixas de probabilidade estimada contra
a frequência observada. O teste é retrospectivo sobre o arquivo atual: não reproduz
as versões do CSV disponíveis em cada data histórica. Na Premier 2025/26, 280 jogos
foram avaliados e o baseline por mando teve Brier 0,2624, pior que o 0,2484 da liga.
Esse resultado não sustenta usar a estimativa como vantagem comprovada.

Quando o planejamento traz uma fila ainda válida, o painel permite digitar uma odd
decimal para um jogo e mercado. Exibe o ponto de equilíbrio `1/odd`, a diferença
em pontos percentuais e o valor esperado teórico `probabilidade * odd - 1`.
A comparação não lê a Betano nem valida a odd ou a calibração do baseline; uma
diferença positiva não é indicação de aposta. Se a agenda tiver mais de uma hora ou
o jogo já tiver começado, é preciso atualizá-la antes da comparação.

## Execução de 14/09/2026

Às 16h05 de São Paulo, cinco jogos da agenda já haviam começado. Bahia × Remo
tinha início futuro, mas o campo de status recebido era incompatível com os
estados documentados. O sistema não inferiu o status e produziu fila vazia.
Veja `reports/plano_diario_2026-09-14.json`. Foram executados 148 testes com sucesso;
três testes de integração foram omitidos sem a configuração do banco de testes.

## Execução de 15/09/2026

Docker Desktop e PostgreSQL foram iniciados; o container está saudável e a avaliação
da Premier 2025/26 foi regenerada a partir dos 380 jogos no banco. Football-data.org
retornou 3 jogos no dia 15 UTC e 5 no dia 16 UTC; Sportmonks retornou 3 jogos no
15 UTC. O mapa local `reports/mapa_times_football_data_2026_2027.json` registra
14 associações explícitas entre IDs da API e nomes presentes no CSV da La Liga.
O painel integrado carrega esse mapa no planejamento.

O plano de 15/09 conciliou os três jogos locais da La Liga, mas produziu fila vazia:
o último resultado do CSV está além do limite operacional de três dias. A fila vazia
não é falha da conciliação.

## Coleta padrão das seis competições

O comando abaixo consulta APIs permitidas e usa o dia civil de São Paulo como padrão:

```powershell
.\.venv\Scripts\futebol-analytics.exe coletar-padrao --saida reports/coleta_padrao_hoje.json
```

Use `--data YYYY-MM-DD` para uma data específica. O preset inclui Brasileirão
Série A (`BSA`), Premier League (`PL`), Champions League (`CL`) e Libertadores
(`CLI`) no Football-data.org. Consulta dois dias UTC por competição e mantém
somente jogos que caem no dia pedido em São Paulo. Copa do Brasil usa a API
Dados Futebol, localizando o campeonato da temporada e filtrando suas partidas
pela data. Sul-Americana permanece `sem_fonte_validada`: não foi confirmado um
identificador e acesso no plano atual das APIs permitidas. O SoccerStats não é
coletado automaticamente, conforme seus termos.

O relatório JSON registra cada competição com `coletado`, `erro` ou
`sem_fonte_validada`. `coletado` com zero jogos significa que a API respondeu
sem jogos no recorte, não cobertura completa. Falhas em um provedor preservam
os resultados das outras competições. O comando retorna erro enquanto alguma
competição estiver incompleta, para que uma rotina agendada não trate a coleta
parcial como sucesso.

Validação real em 15/09/2026: Libertadores retornou Platense × Fluminense;
Brasileirão, Premier e Champions retornaram zero jogos para o dia local.
Copa do Brasil retornou HTTP 403 no plano atual da chave Dados Futebol.
A Sul-Americana ficou sem fonte validada. O relatório está em
`reports/coleta_padrao_2026-09-15.json`.

A tarefa `FutebolAnalyticsColetaPadrao` foi registrada no Agendador do Windows
para 08:00 no fuso local de Brasília. Ela executa
`scripts/coleta_padrao_diaria.ps1`, grava um JSON por dia em `reports` e um log
local. A tarefa usa a sessão interativa do usuário: o computador precisa estar
ligado e o usuário conectado. Uma execução de teste produziu o relatório e
retornou código 2, sinalizando Copa do Brasil bloqueada e Sul-Americana sem
fonte, sem ocultar a coleta parcial das outras competições.

## Auditoria Platense × Fluminense em 15/09/2026

O Football-data.org liberou 144 jogos encerrados da Libertadores 2026; 137 tinham
placar válido no tempo regulamentar. No recorte por mando, Platense tinha quatro
jogos em casa e Fluminense quatro fora. O baseline exige cinco por equipe e não
produziu mercados estimados. Seu backtest de over 2,5 nessa competição avaliou
zero partidas. A consulta à liga argentina (`ASL`) retornou HTTP 403 no plano
atual. A consulta do jogo confirmou status SCHEDULED para 22:00 UTC, mas o campo
odds informa que o Odds-Package precisa ser ativado. Por isso não há indicação
de aposta. Evidência: `reports/auditoria_platense_fluminense_2026-09-15.json`.

## Piloto Premier League + Brasileirão em 15/09/2026

O foco inicial é over 2,5 gols. O comando
`.\.venv\Scripts\futebol-analytics.exe avaliar-foco --saida reports/avaliacao_foco.json`
lê Premier 2025/26 do CSV e Brasileirão 2026 da projeção local da API Dados Futebol,
sem consumir API. A captura de rodadas do Brasileirão foi atualizada em 15/09 e
normalizada: 266 jogos encerrados com placar válido. O relatório conjunto de hoje
está em `reports/avaliacao_foco_premier_brasileirao_2026-09-15.json`.

Na avaliação cronológica, o baseline por mando ficou atrás da frequência histórica
da liga: Premier 280 jogos, Brier 0,2624 contra 0,2484; Brasileirão 161 jogos,
Brier 0,2669 contra 0,2517. Uma mistura com a taxa da liga e um Poisson de gols
com suavização fixa também não superaram o baseline da liga em ambas as amostras;
nenhum foi aprovado como motor de indicação. O painel integrado agora tem uma aba
para ver e baixar a avaliação das duas ligas.

A API Dados Futebol liberou rodadas e placares no plano atual, mas uma consulta ao
endpoint de estatísticas de partida encerrada retornou HTTP 403. Escanteios,
cartões e xG brasileiros exigem confirmar acesso real antes de entrar neste piloto.
A saída contém zero indicações enquanto faltam validação futura e odds pré-jogo
alinhadas com o mercado.

## Acompanhamento de gols com os dados disponíveis

O comando
`.\.venv\Scripts\futebol-analytics.exe acompanhar-foco --premier-ano 2026 --brasileirao-temporada 2026 --saida reports/acompanhamento_foco.json`
consulta uma vez a temporada atual da Premier no Football-data.org e lê o
Brasileirão local. Não usa o CSV antigo para a agenda atual: a API retornou
40 jogos encerrados até 14/09, enquanto o CSV local tinha 30 até 06/09.
Mantém uma agenda de até sete dias e calcula, em cada liga separadamente,
`(jogos_com_3_ou_mais_gols + 1) / (jogos_validos + 2)`. Exige ao menos 30
jogos válidos para mostrar a taxa e verifica captura nas últimas 24 horas e
último resultado nos últimos três dias. O intervalo de Wilson descreve a
frequência histórica; não é um intervalo de previsão para um jogo específico.

Em 15/09, o relatório `reports/acompanhamento_foco_2026-09-15.json` encontrou
10 jogos futuros da Premier e 11 do Brasileirão nos sete dias seguintes.
As taxas suavizadas do over 2,5 eram 52,38% em 40 jogos ingleses e 51,12% em
266 jogos brasileiros. A mesma taxa aparece para todos os jogos da respectiva
liga, pois é um benchmark que não considera as equipes. Há zero indicações:
não existem odds pré-jogo alinhadas nem evidência de vantagem contra preços
de mercado. O painel mostra esse acompanhamento somente após clique explícito
para atualizar a Premier; a avaliação histórica das duas ligas continua local.

## Cotações históricas da Premier

O comando
`.\.venv\Scripts\futebol-analytics.exe avaliar-odds-premier --temporada 2025/2026 --saida reports/avaliacao_odds_premier.json`
usa somente o CSV E0 já importado. Compara over 2,5 em `B365>2.5` e
`B365<2.5` (após abertura) e nas colunas `B365C>2.5` e `B365C<2.5`
(fechamento). Remove proporcionalmente a margem para obter a probabilidade
do mercado. A descrição das duas capturas está em
https://football-data.co.uk/downloadm.php.

Nos 280 jogos de 2025/26 em que o modelo gerou previsão, houve cotações
completas e alinhadas. O Brier do modelo foi 0,2624; o da taxa histórica da
liga, 0,2484; o do mercado após abertura, 0,2476; e o do fechamento, 0,2460.
Brier menor é melhor. O resultado reforça que o modelo atual não deve indicar
apostas. As cotações são de jogos passados e a avaliação usa a versão atual
do CSV, não capturas guardadas antes de cada partida. Evidência:
`reports/avaliacao_odds_premier_2025_2026.json`.

## Ambos marcam no piloto de gols

Os comandos `avaliar-foco` e `acompanhar-foco` agora incluem `ambas_sim`:
o mercado ocorre quando mandante e visitante marcam ao menos um gol cada.
O backtest mantém a regra cronológica de treino e compara o baseline por
mando à frequência anterior da liga no mesmo conjunto de jogos.

Na avaliação local de 15/09/2026, o Brier de ambos marcam foi 0,2603 para
o modelo e 0,2461 para a liga em 280 jogos da Premier 2025/26; no
Brasileirão 2026, 0,2481 e 0,2408 em 161 jogos. O modelo não superou a
referência em nenhuma das ligas. O acompanhamento da temporada atual
registrou 21 ocorrências em 40 jogos da Premier e 158 em 266 do Brasileirão;
as taxas suavizadas eram 52,38% e 59,33%. Essas são taxas da liga, iguais
para todos os jogos de sua agenda, sem diferenciar os times.

Os relatórios atualizados estão em
`reports/avaliacao_foco_premier_brasileirao_2026-09-15.json` e
`reports/acompanhamento_foco_2026-09-15.json`. O painel integrado exibe
ambos os mercados. Seguem zero indicações enquanto faltam validação futura,
probabilidades calibradas e odds pré-jogo do mesmo mercado.

## Interface do acompanhamento

A aba `Premier e Brasileirão` fica primeiro na Central integrada. Na abertura,
ela lê o último relatório salvo em `reports/` sem consultar a API e mostra
seis cartões com a taxa
histórica dos três mercados em cada liga, cobertura e atualização das fontes,
e uma agenda filtrável por liga com horários de São Paulo. A avaliação local
salva aparece abaixo, com uma linha por liga e mercado e Brier do modelo ao lado
da referência da liga. O painel deixa explícito que as taxas da agenda são
iguais para todos os jogos de uma liga e que não há indicação de aposta.
Relatórios com mais de 24 horas deixam de mostrar taxas para a agenda e pedem
atualização; jogos que já começaram saem da lista. O botão `Atualizar agenda
e taxas` continua disponível para consultar uma vez a temporada atual da
Premier e ler o Brasileirão local.

## Conferência de odds nos jogos previstos

Na agenda da aba `Premier e Brasileirão`, o detalhe `Conferir uma odd deste jogo`
permite escolher um confronto e um dos três mercados, informar a fonte e a odd
decimal pré-jogo. A tela calcula `1 / odd`, a probabilidade de equilíbrio da
cotação, e a compara com a taxa histórica da liga. A diferença é apenas
descritiva: a taxa da liga é igual para todos os confrontos e o modelo por
equipe não a superou em Brier. Mesmo uma diferença positiva não gera indicação
nem prova valor esperado positivo para aquele jogo. A cotação digitada fica
somente na sessão da tela e é descartada quando a agenda é atualizada.

## Over 1,5 gols

O piloto também acompanha `gols_mais_1.5`, que ocorre quando a partida termina
com dois ou mais gols no total. Usa os mesmos placares, a mesma regra de
treino anterior à data do jogo e a mesma conferência descritiva de odds dos
outros mercados. O painel mostra três taxas históricas em cada liga e inclui
over 1,5 na agenda e na avaliação local.

Em 15/09/2026, a temporada atual da Premier tinha 30 ocorrências em 40 jogos
encerrados, taxa suavizada de 73,81%; o Brasileirão tinha 208 em 266, taxa
suavizada de 77,99%. No backtest por mando, o Brier do modelo ficou atrás da
frequência anterior da liga: Premier 0,1737 contra 0,1671 em 280 jogos;
Brasileirão 0,1882 contra 0,1778 em 161 jogos. Menor Brier é melhor. O CSV
histórico local da Premier não traz cotações de over 1,5, e não temos odds
pré-jogo atuais alinhadas. Portanto, nenhuma taxa prova vantagem para um
confronto específico e continuam zero indicações.

## Registro datado do planejamento

O comando `python -m futebol_analytics.daily --data YYYY-MM-DD --saida reports/plano_diario_hoje.json`
agora cria um pacote novo em `reports/registros_diarios/` a cada execução. `--registro-dir`
permite escolher outra pasta. O pacote contém `agenda.json`, `historicos.json`,
`mapa_times.json`, `previsoes.json` e `manifesto.json`. O manifesto registra o horário
da execução e o SHA-256 dos quatro arquivos de dados. A consulta ao banco usa uma
única versão CSV por liga e temporada durante o planejamento e salva as linhas
efetivamente lidas. O caminho do pacote é impresso no terminal.

Esses pacotes começam a preservar entradas e previsões daqui para frente. Não
transformam avaliações retrospectivas antigas em backtests feitos com dados
disponíveis naquela época. Para uma avaliação futura, resultados posteriores devem
ser conciliados com a previsão preservada, sem reestimar o jogo usando um CSV novo.

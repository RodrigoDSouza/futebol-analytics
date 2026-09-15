import pytest

from futebol_analytics.api.football_csv import parse_csv, source_url

HEADER = 'Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HC,AC,HY,AY,HR,AR,HS,AS,HST,AST\n'
ROW = 'E0,21/08/2026,Arsenal,Coventry,3,0,8,2,1,1,0,0,20,4,6,1\n'


def test_field_mapping_and_zero():
    row = parse_csv(HEADER+ROW, '2026/2027')[0]
    assert row['escanteios_mandante'] == 8
    assert row['amarelos_visitante'] == 1
    assert row['vermelhos_mandante'] == 0
    assert row['data'] == '2026-08-21'


def test_missing_values_stay_missing():
    row = parse_csv(HEADER+ROW.replace(',8,2,', ',,2,'), '2026/2027')[0]
    assert row['escanteios_mandante'] is None


@pytest.mark.parametrize('content', [HEADER+ROW+ROW, HEADER, '<html>Error</html>',
    HEADER+ROW.replace(',8,2,', ',-1,2,'), HEADER+ROW.replace('E0,','E1,'),
    HEADER+ROW.replace('2026','2024')])
def test_invalid_csv_rejected(content):
    with pytest.raises(ValueError):
        parse_csv(content, '2026/2027')


def test_url_restricted_to_valid_season():
    assert source_url('2026/2027') == 'https://football-data.co.uk/mmz4281/2627/E0.csv'
    with pytest.raises(ValueError):
        source_url('../../other')


@pytest.mark.parametrize('league', ['E0', 'SP1', 'I1', 'D1', 'F1'])
def test_leagues_are_isolated(league):
    assert source_url('2026/2027', league).endswith(f'/2627/{league}.csv')
    assert len(parse_csv(HEADER + ROW.replace('E0,', league + ','), '2026/2027', league)) == 1
    other = 'I1' if league != 'I1' else 'E0'
    with pytest.raises(ValueError):
        parse_csv(HEADER + ROW.replace('E0,', other + ','), '2026/2027', league)


def test_unknown_league_rejected():
    with pytest.raises(ValueError):
        source_url('2026/2027', '../other')

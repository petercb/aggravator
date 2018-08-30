import aggravator
from click.testing import CliRunner

def test_show_groups():
    runner = CliRunner()
    result = runner.invoke(aggravator.cli, [
        '--uri=example/config.yml',
        '--env=dev',
        '--show'
    ])
    assert result.exit_code == 0
    assert 'app' in result.output
    assert 'windows' in result.output

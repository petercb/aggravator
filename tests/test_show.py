import aggravator
from click.testing import CliRunner

def test_show():
    runner = CliRunner()
    result = runner.invoke(aggravator.cli, [
        '--vault-password-file=/dev/null',
        '--uri=example/config.yml',
        '--show'
    ])
    assert result.exit_code == 0
    assert 'dev' in result.output
    assert 'prod' in result.output

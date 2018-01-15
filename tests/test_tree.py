import aggravator
import yaml
from click.testing import CliRunner

def test_tree():
    runner = CliRunner()
    result = runner.invoke(aggravator.cli, [
        '--vault-password-file=/dev/null',
        '--uri=example/config.yml',
        '--tree'
    ])
    assert result.exit_code == 0
    # data = yaml.load(result.output)
    # assert type(data) is dict
    # assert type(data['dev']) is dict
    # assert type(data['prod']) is dict

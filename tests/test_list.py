import aggravator
import json
from click.testing import CliRunner

def test_list():
    runner = CliRunner()
    result = runner.invoke(aggravator.cli, [
        '--vault-password-file=/dev/null',
        '--uri=example/config.yml',
        '--env=prod',
        '--list'
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert type(data) is dict
    assert type(data['all']) is dict
    assert type(data['all']['vars']) is dict
    assert data['all']['vars']['platform_name'] == 'prod'

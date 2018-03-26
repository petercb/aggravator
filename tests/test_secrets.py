import aggravator
import yaml
from click.testing import CliRunner

def test_list():
    runner = CliRunner()
    result = runner.invoke(aggravator.cli, [
        '--vault-password-file=example/vault_password.txt',
        '--uri=example/config.yml',
        '--env=prod',
        '--list'
    ])
    assert result.exit_code == 0
    data = yaml.load(result.output)
    assert type(data) is dict
    assert type(data['all']) is dict
    assert type(data['all']['vars']) is dict
    assert data['all']['vars']['platform_name'] == 'prod'
    assert data['all']['vars']['is_this_secret'] == 'yuppers'

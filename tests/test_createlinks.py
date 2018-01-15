import aggravator
import os.path
from click.testing import CliRunner

def test_createlinks():
    runner = CliRunner()
    conf_file = os.path.abspath('example/config.yml')
    with runner.isolated_filesystem():
        result = runner.invoke(aggravator.cli, [
            '--vault-password-file=/dev/null',
            '--uri=' + conf_file,
            '--createlinks=.'
        ])
        assert result.exit_code == 0
        assert os.path.islink('dev')
        assert os.path.islink('prod')

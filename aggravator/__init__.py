'''
Custom dynamic inventory script for Ansible, in Python.

This script will read in a configuration file either locally or fetched via HTTP and will
output a JSON data structure describing the inventory by merging the files as listed in
the config file.

Files can be in either YAML or JSON format
'''

# pylint: disable=wrong-import-order
# Support python 2 and 3
from __future__ import (absolute_import)
from future import standard_library
standard_library.install_aliases()
from builtins import object # pylint: disable=redefined-builtin

# stdlib
import json
import os
import sys

## This is the python3 name, formerly urlparse, install_aliases() above make
## this work under python2
from urllib.parse import (urlparse, urljoin) # pylint: disable=import-error

# extras from packages
import ansible
import click
import deepmerge
import dpath.util
import requests
import yaml

# Ansible stuff for Secrets
from ansible.parsing.vault import is_encrypted as is_vault_encrypted
from ansible.parsing.vault import VaultLib
# Ansible utils
from ansible.module_utils._text import to_text



def get_config():
    '''Determine location of root config file if none specified'''
    self_path = os.path.dirname(os.path.realpath(sys.argv[0]))
    check_paths = [
        os.path.abspath(os.path.join(self_path, '..', 'etc', 'config.yaml')),
        '/etc/aggravator/config.yaml',
        '/usr/local/etc/aggravator/config.yaml'
    ]
    for fp in check_paths:
        if os.path.isfile(fp):
            return fp
    return None


def get_environment():
    '''Determine the platform/environment name from name of called script'''
    if os.path.islink(sys.argv[0]):
        return os.path.basename(sys.argv[0])
    return None


def create_links(environments, directory):
    '''Create symlinks for platform inventories'''
    errcount = 0
    for ename in environments:
        try:
            os.symlink(
                os.path.relpath(__file__, directory),
                os.path.join(directory, ename)
            )
        except(OSError) as err:
            click.echo("This symlink might already exist. Leaving it unchanged. Error: %s" % (err))
            errcount += 1
    return errcount


class Vault(object):
    '''Read an Ansible vault'''
    def __init__(self, password):
        self._ansible_ver = float('.'.join(ansible.__version__.split('.')[:2]))
        self.secret = password.encode('utf-8')
        self.vault = VaultLib(self._make_secrets(self.secret))

    def _make_secrets(self, secret):
        '''make ansible version appropriate secret'''
        if self._ansible_ver < 2.4:
            return secret

        from ansible.constants import DEFAULT_VAULT_ID_MATCH
        from ansible.parsing.vault import VaultSecret
        return [(DEFAULT_VAULT_ID_MATCH, VaultSecret(secret))]

    def decrypt(self, stream):
        '''read vault stream and return decrypted'''
        return self.vault.decrypt(stream)


def fetch_data_remote(url, requestsobj=requests):
    '''fetch data from url and return as plaintext'''
    response = requestsobj.get(url)
    if response.status_code == 404:
        raise LookupError("Failed to find data at: {}".format(url))
    response.raise_for_status()
    return response.text


def fetch_data_local(localfile):
    '''Fetch data from local file and return as plaintext'''
    this_path = os.path.realpath(os.path.expanduser(localfile))
    if not os.path.exists(this_path):
        raise IOError("The file %s was not found" % this_path)
    try:
        f_obj = open(this_path, "rb")
        data = f_obj.read().strip()
        f_obj.close()
    except (OSError, IOError) as err:
        raise LookupError("Could not read file %s: %s" % (this_path, err))
    return to_text(data, errors='surrogate_or_strict')


def fetch_data(uri, requestsobj=requests, data_type=None, vault_password=None):
    '''Fetch data using either local or remote functions'''
    uriobj = urlparse(uri)
    loader = {
        'json': getattr(json, 'loads'),
        'yaml': getattr(yaml, 'load')
    }
    if data_type is None:
        # guess the data type from file extension
        if uriobj.path.endswith(('.yaml', '.yml')):
            data_type = 'yaml'
        else:
            data_type = os.path.splitext(uriobj.path)[1]
    data_type = data_type.lower()
    if data_type not in loader:
        raise AttributeError("Unsupported data type: {}".format(data_type))
    parser = loader[data_type]
    if uriobj.scheme in ['file', '']:
        data = fetch_data_local(uriobj.path)
    elif uriobj.scheme in ['http', 'https']:
        data = fetch_data_remote(uri, requestsobj)
    else:
        raise AttributeError("unsupported URI '{}'".format(uri))
    if is_vault_encrypted(data):
        if vault_password is None:
            data = '{}'
        else:
            vault = Vault(vault_password)
            data = vault.decrypt(data)
    return parser(data)


def raise_for_type(item, types, section):
    '''raise an AttributeError if `item` is not of `types`'''
    type_names = None
    if isinstance(types, tuple):
        type_names = [t.__name__ for t in types]
    elif isinstance(types, type):
        type_names = types.__name__
    else:
        raise AttributeError(
            "Invalid type '{}' for `types` parameter, must be type or tuple of types".format(
                type(types).__name__
            )
        )
    if not isinstance(item, types):
        if isinstance(types, tuple):
            ", ".join(types)
        raise AttributeError(
            "invalid type '{}' in section '{}', must be: {}".format(
                type(item).__name__,
                section,
                type_names
            )
        )


def convert_host_list_to_dict(inv):
    '''
    Iterate over the inventory data structure and convert any host groups that
    are lists into dictionary form
    '''
    for group in inv:
        if isinstance(inv[group], list):
            # needs converting
            inv[group] = {'hosts': inv[group]}


class Inventory(object):
    '''Retrieve Ansible inventory from available sources and return as JSON'''
    def __init__(self, uri, env=None, vault_password=None):
        self.session = requests.Session()
        self.config = fetch_data(uri, self.session)
        self.uri = uri
        self.env = env
        self.vault_password = vault_password

    def fetch_environments(self):
        '''Fetch a list of environments that are defined upstream'''
        return list(self.config.get('environments', {}))

    def fetch(self, uri, data_type=None):
        '''fetch the requested uri'''
        uriobj = urlparse(uri)
        # Check if it's an absolute uri, or a relative
        if uriobj.scheme == '':
            # Unspecified URI type, assume relative to config URI
            return fetch_data(
                urljoin(str(self.uri), uriobj.path),
                self.session,
                data_type,
                self.vault_password
            )
        elif uriobj.scheme in ['file', 'http', 'https']:
            # supported URI types
            if uriobj.path.startswith('/'):
                # Absolute path, fetch it
                return fetch_data(uri, self.session, data_type, self.vault_password)
            else:
                # Assume relative to config URI
                return fetch_data(
                    urljoin(self.uri, uriobj.path),
                    self.session,
                    data_type,
                    self.vault_password
                )
        else:
            # Unsupported type
            raise AttributeError("Unsupported type '{}'".format(uriobj.scheme))


    def generate_inventory(self):
        '''Generate inventory by merging hosts and variables'''
        # Set the basic structure
        my_merger = deepmerge.Merger(
            [
                (list, ["override"]),
                (dict, ["merge"])
            ],
            ["override"],
            ["override"]
        )
        invdata = {
            '_meta': {
                'hostvars': {}
            },
            'all': {
                'vars': {
                    'platform_name': self.env
                }
            }
        }
        # start merging
        for inc in self.config.get('environments', {}).get(self.env, {}).get('include', []):
            convert_host_list_to_dict(invdata)
            if isinstance(inc, str):
                # Just a plain file listed with no extra properties
                # Pull it in and hope there are proper sections
                # TODO: add some schema validation
                from_file = self.fetch(inc)
                invdata = my_merger.merge(invdata, from_file)
            elif isinstance(inc, dict):
                # Dictionary listing, fetch file in `path` into keyspace `key`
                from_file = self.fetch(inc['path'], inc.get('format'))
                if 'key' in inc:
                    # A key space is specified, load the file into it
                    key = inc['key']
                    try:
                        data = dpath.util.get(invdata, key)
                        data = my_merger.merge(data, from_file)
                    except KeyError:
                        dpath.util.new(invdata, key, from_file)
                else:
                    # No keyspace defined, load the file into the root
                    invdata = my_merger.merge(invdata, from_file)
            else:
                raise_for_type(inc, (str, dict), ':'.join(['', self.env, 'include']))

        return invdata


@click.command()
@click.option(
    '--env', default=get_environment(), envvar='INVENTORY_ENV', show_default=True,
    help='specify the platform name to pull inventory for'
)
@click.option(
    '--uri', envvar='INVENTORY_URI', show_default=True,
    default=get_config(),
    help='specify the URI to query for inventory config file, supports file:// and http(s)://'
)
@click.option(
    '--vault-password-file', 'vpfile', show_default=True,
    type=click.Path(exists=False, dir_okay=False, file_okay=True, readable=True, resolve_path=True),
    envvar='VAULT_PASSWORD_FILE', default=os.path.expanduser('~/.vault_pass.txt'),
    help='vault password file, if set to /dev/null secret decryption will be disabled'
)
@click.option(
    '--output-format', 'outformat', envvar='INVENTORY_FORMAT', show_default=True, default='yaml',
    type=click.Choice(['yaml', 'json']), help='specify the output format'
)
@click.option('--list', 'list_flag', is_flag=True, help='Print inventory information as a JSON object')
@click.option('--host', help='Retrieve host variables (not implemented)')
@click.option(
    '--createlinks', 'linkdir',
    type=click.Path(exists=True, dir_okay=True, file_okay=False, writable=True),
    help='Create symlinks in DIRECTORY to the script for each platform name retrieved'
)
@click.option('--show', 'show_flag', is_flag=True, help='Output a list of upstream environments (or groups if environment is set)')
def cli(env, uri, vpfile, outformat, list_flag, host, linkdir, show_flag):
    '''Ansible file based dynamic inventory script'''

    # Called with `--createlinks`
    if linkdir:
        return create_links(Inventory(uri).fetch_environments(), linkdir)

    else:
        if env is None:
            if show_flag:
                click.echo("Upstream environments:")
                click.echo("\n".join(sorted(Inventory(uri).fetch_environments())))
            else:
                click.echo("Error: Missing environment, use --env or `export INVENTORY_ENV`")
                return 1
        else:
            if show_flag:
                grouplist = list(Inventory(uri, env).generate_inventory())
                grouplist.remove('_meta')
                click.echo("\n".join(sorted(grouplist)))
            else:
                # If vault password file is /dev/null, disable secrets decryption
                if vpfile == '/dev/null':
                    vpfile = None

                # Read in the vault password if one was provided
                if vpfile is not None:
                    vault_password = fetch_data_local(vpfile)
                else:
                    vault_password = None

                data = None

                # Called with `--list`.
                if list_flag:
                    data = Inventory(uri, env, vault_password).generate_inventory()

                # Called with `--host [hostname]`.
                elif host:
                    # Not implemented, since we should return _meta info in `--list`.
                    data = {}

                # require either --list or --host
                else:
                    click.echo("Error: Missing parameter (--list or --host)?")
                    return 1

                dumper = {
                    'json': getattr(json, 'dumps'),
                    'yaml': getattr(yaml, 'dump')
                }
                if outformat not in dumper:
                    raise AttributeError("Unsupported output data type: {}".format(outformat))
                click.echo(dumper[outformat](data))

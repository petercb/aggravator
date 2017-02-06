#!/usr/bin/env python

'''
Custom dynamic inventory script for Ansible, in Python.

This script will read in a configuration file either locally or fetched via HTTP and will
output a JSON data structure describing the inventory by merging the files as listed in
the config file.

Files can be in either YAML or JSON format
'''

# pylint: disable=wrong-import-order
# Support python 2 and 3
from __future__ import (absolute_import, print_function)
from future import standard_library
standard_library.install_aliases()
from builtins import object # pylint: disable=redefined-builtin

# stdlib
import argparse
import json
import os
import sys

## This is the python3 name, formerly urlparse, install_aliases() above make
## this work under python2
from urllib.parse import (urlparse, urljoin) # pylint: disable=import-error

# extras from packages
import dpath.util
import requests
import yaml


def read_cli_args():
    '''Read the command line args passed to the script.'''
    parser = argparse.ArgumentParser(
        description='Ansible file based dynamic inventory script',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '--env', action='store', default=get_environment(),
        help='specify the platform name to pull inventory for'
    )
    parser.add_argument(
        '--uri', action='store',
        default=os.environ.get('INVENTORY_URI', 'config.yaml'),
        help='specify the URI to query for inventory config file, supports file:// and http(s)://'
    )
    mutual_ops = parser.add_mutually_exclusive_group(required=True)
    mutual_ops.add_argument(
        '--list', action='store_true',
        help='Print inventory information as a JSON object'
    )
    mutual_ops.add_argument(
        '--host', action='store',
        help='Retrieve host variables (not implemented)'
    )
    mutual_ops.add_argument(
        '--createlinks', action='store', dest='linkdir',
        help='Create symlinks in LINKDIR to the script for each platform name retrieved'
    )
    mutual_ops.add_argument(
        '--show', action='store_true',
        help='Output a list of upstream environments'
    )
    mutual_ops.add_argument(
        '--tree', action='store_true',
        help='Output a tree of what files will be loaded for an environment'
    )
    return parser.parse_args()


def get_environment():
    '''Determine the platform/environment name from system variable or name of called script'''
    myname = os.path.basename(__file__)
    envvar = os.environ.get('INVENTORY_ENV')
    if envvar:
        return envvar
    elif myname != 'inventory.py':
        return myname
    else:
        return None


def create_links(environments, directory):
    '''Create symlinks for platform inventories'''
    for ename in environments:
        os.symlink(
            os.path.relpath(__file__, directory),
            os.path.join(directory, ename)
        )


def fetch_data_remote(url, requestsobj=None):
    '''fetch data from url, parse and return as python dict'''
    if requestsobj is None:
        requestsobj = requests
    response = requestsobj.get(url)
    if response.status_code == 404:
        raise LookupError("Failed to find data at: {}".format(url))
    response.raise_for_status()
    if url.endswith('json'):
        return json.loads(response.text)
    elif url.endswith(('yaml', 'yml')):
        return yaml.load(response.text)
    else:
        raise AttributeError(
            "Unsupported data type: {}".format(os.path.splitext(urlparse(url).path)[1])
        )


def fetch_data_local(localfile):
    '''Fetch data from local file, parse and return as python dict'''
    if os.path.isfile(localfile):
        with open(localfile) as datafile:
            if localfile.endswith('json'):
                return json.load(datafile)
            if localfile.endswith(('yaml', 'yml')):
                return yaml.load(datafile)
            else:
                raise AttributeError(
                    "Unsupported data type: {}".format(os.path.splitext(localfile)[1])
                )
    raise LookupError("failed to parse {}".format(localfile))


def fetch_data(uri, requestsobj=None):
    '''Fetch data using either local or remote functions'''
    uriobj = urlparse(uri)
    if uriobj.scheme in ['file', '']:
        return fetch_data_local(uriobj.path)
    if uriobj.scheme in ['http', 'https']:
        return fetch_data_remote(uri, requestsobj)
    raise AttributeError("unsupported URI '{}'".format(uri))


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
    def __init__(self, uri, env=None):
        self.session = requests.Session()
        self.config = fetch_data(uri, self.session)
        self.uri = uri
        self.env = env

    def fetch_environments(self):
        '''Fetch a list of environments that are defined upstream'''
        return list(self.config.get('environments', {}).keys())

    def fetch(self, uri):
        '''fetch the requested uri'''
        uriobj = urlparse(uri)
        # Check if it's an absolute uri, or a relative
        if uriobj.scheme == '':
            # Unspecified URI type, assume relative to config URI
            return fetch_data(urljoin(self.uri, uriobj.path))
        elif uriobj.scheme in ['file', 'http', 'https']:
            # supported URI types
            if uriobj.path.startswith('/'):
                # Absolute path, fetch it
                return fetch_data(uri, self.session)
            else:
                # Assume relative to config URI
                return fetch_data(urljoin(self.uri, uriobj.path))
        else:
            # Unsupported type
            raise AttributeError("Unsupported type '{}'".format(uriobj.scheme))


    def generate_inventory(self):
        '''Generate inventory by merging hosts and variables'''
        # Set the basic structure
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
            if isinstance(inc, str) or (isinstance(inc, dict) and 'key' not in inc):
                # Just a plain file listed with no extra properties
                # Pull it in and hope there are proper sections
                # TODO: add some schema validation
                from_file = self.fetch(inc)
                dpath.util.merge(invdata, from_file, flags=dpath.util.MERGE_TYPESAFE)
            elif isinstance(inc, dict):
                # Dictionary listing, fetch file in `path` into keyspace `key`
                from_file = self.fetch(inc['path'])
                key = inc['key']
                try:
                    data = dpath.util.get(invdata, key)
                    dpath.util.merge(data, from_file, flags=dpath.util.MERGE_TYPESAFE)
                except KeyError:
                    dpath.util.new(invdata, key, from_file)
            else:
                raise_for_type(inc, (str, dict), ':'.join(['', self.env, 'include']))

        return invdata


def main():
    '''Entry point for running as a CLI'''
    args = read_cli_args()
    inv = Inventory(args.uri, args.env)

    # Called with `--createlinks`
    if args.linkdir:
        create_links(inv.fetch_environments(), args.linkdir)

    # Called with `--show`
    elif args.show:
        print("Upstream environments:")
        print("\n".join(sorted(inv.fetch_environments())))

    # Called with `--tree`
    elif args.tree:
        if args.env is None:
            print(yaml.dump(inv.config.get('environments', {}), default_flow_style=False))
        else:
            print(yaml.dump(
                inv.config.get('environments', {}).get(args.env),
                default_flow_style=False
            ))

    else:
        if args.env is None:
            print("Error: Missing environment, use --env or `export INVENTORY_ENV`")
            return 1
        else:
            data = None

            # Called with `--list`.
            if args.list:
                data = inv.generate_inventory()

            # Called with `--host [hostname]`.
            elif args.host:
                # Not implemented, since we should return _meta info in `--list`.
                data = {}

            # This should never happen since argparse should require either --list or --host
            else:
                data = {"_meta": {"hostvars": {}}}

            print(json.dumps(data))


if __name__ == '__main__':
    sys.exit(main())

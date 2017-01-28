#!/usr/bin/env python

'''
Custom dynamic inventory script for Ansible, in Python.
'''

# Support python 2 and 3
from __future__ import (absolute_import, print_function)
from future import standard_library
standard_library.install_aliases()
from builtins import object

# stdlib
import argparse
import json
import os
import sys
from urllib.parse import (urlparse, urljoin)

# extras from packages
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
        default=os.environ.get('INVENTORY_URL'),
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
        raise LookupError("Error: Failed to find data at: {}".format(url))
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
    raise LookupError("Error: failed to parse {}".format(localfile))


def fetch_data(uri, requestsobj=None):
    '''Fetch data using either local or remote functions'''
    uriobj = urlparse(uri)
    if uriobj.scheme in ['file', '']:
        return fetch_data_local(uriobj.path)
    if uriobj.scheme in ['http', 'https']:
        return fetch_data_remote(uri, requestsobj)
    raise AttributeError("Error: unsupported URI '{}'".format(uri))


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
            raise AttributeError("Error: '{}' type is unsupported".format(uriobj.scheme))

    def fetch_merge_hosts(self, section):
        '''Fetch and merge hosts'''
        data = {}
        for inc in self.config.get('environments', {}).get(self.env, {}).get(section, []):
            if isinstance(inc, str):
                # Just a plain file listed with no extra properties
                # Pull it in and assume there are sections
                temp = self.fetch(inc)
                for key in temp:
                    data[key] = data.get(key, [])
                    data[key] = list(set(data[key]) | set(temp[key]))
            elif isinstance(inc, dict):
                # Dictionary listing, fetch file in `path` into keyspace in `key`
                temp = self.fetch(inc['path'])
                key = inc['key']
                data[key] = data.get(key, [])
                data[key] = list(set(data[key]) | set(temp[key]))
            else:
                raise AttributeError(
                    "Error: unsupported entry in '{}' ({}), must be string or dict".format(
                        section,
                        type(inc).__name__
                    )
                )
        return data

    def fetch_merge_vars(self, section):
        '''Fetch and merge variables'''
        data = {}
        for inc in self.config.get('environments', {}).get(self.env, {}).get(section, []):
            if isinstance(inc, str):
                # Just a plain file listed with no extra properties
                # Pull it in and assume there are sections
                temp = self.fetch(inc)
                for key in temp:
                    data[key] = data.get(key, {})
                    data[key].update(temp[key])
            elif isinstance(inc, dict):
                # Dictionary listing, fetch file in `path` into keyspace in `key`
                temp = self.fetch(inc['path'])
                key = inc['key']
                data[key] = data.get(key, {})
                data[key].update(temp)
            else:
                raise AttributeError(
                    "Error: unsupported entry in '{}' ({}), must be string or dict".format(
                        section,
                        type(inc).__name__
                    )
                )
        return data

    def generate_inventory(self):
        '''Generate inventory by merging hosts and variables'''
        groupvars = self.fetch_merge_vars('include_group_vars')
        hostvars = self.fetch_merge_vars('include_host_vars')
        invdata = self.fetch_merge_hosts('include_hosts')

        # Make sure _meta with hostvars section exists, this prevents ansible calling this script
        # again with the --host param for every single host returned in --list
        invdata['_meta'] = invdata.get('_meta', {})
        invdata['_meta']['hostvars'] = invdata['_meta'].get('hostvars', {})
        if not isinstance(invdata['_meta']['hostvars'], dict):
            raise AttributeError("Error: hostvars must be a dictionary!")

        # Merge the group vars over top of any defined in the inventory
        # No vars should be defined in the hosts files, and if it was, oh well, smushed
        for key in groupvars:
            invdata[key] = invdata.get(key, {})
            gvtype = type(invdata[key])
            if gvtype is list:
                # convert it to a dict
                invdata[key] = {'hosts': invdata[key]}
            elif gvtype is not dict:
                raise AttributeError("Error: group '{}' is not list or dict!".format(key))
            invdata[key]['vars'] = invdata[key].get('vars', {})
            invdata[key]['vars'].update(groupvars[key])

        # Set the platform_name var if not already set
        invdata['all'] = invdata.get('all', {})
        invdata['all']['vars'] = invdata['all'].get('vars', {})
        invdata['all']['vars']['platform_name'] = invdata['all']['vars'].get(
            'platform_name', self.env)

        # Merge in host vars
        mhvars = invdata['_meta']['hostvars']
        for key in hostvars:
            mhvars[key] = mhvars.get(key, {})
            mhvtype = type(mhvars[key])
            if mhvtype is not dict:
                raise AttributeError(
                    "Error: '{}' hostvars is '{}', must be a dictionary!".format(
                        key,
                        mhvtype.__name__
                    )
                )
            mhvars[key].update(hostvars[key])

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
        print("\n".join(inv.fetch_environments()))

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

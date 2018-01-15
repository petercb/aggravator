from setuptools import setup, find_packages

setup(
    name='aggravator',
    version='0.3',
    description='Ansible inventory script to aggregate other inventory sources',
    author='Peter Burns',
    author_email='pcburns@outlook.com',
    packages=find_packages(exclude=['tests*']),
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    install_requires = [
        'ansible',
        'requests',
        'click',
        'pyyaml',
        'dpath',
        'future'
    ],
    entry_points={
        'console_scripts': [
            'inventory = aggravator:cli',
        ]
    }
)
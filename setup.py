from setuptools import setup, find_packages

setup(
    name='aggravator',
    version='0.4.3',
    description='Ansible inventory script to aggregate other inventory sources',
    long_description=open('README.rst').read(),
    license='MIT',
    url='https://github.com/petercb/aggravator',
    keywords='ansible',
    author='Peter Burns',
    author_email='pcburns@outlook.com',
    packages=find_packages(exclude=['tests*']),
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    install_requires = [
        'ansible>=2.0.0.0',
        'requests',
        'click',
        'pyyaml',
        'deepmerge',
        'dpath',
        'future'
    ],
    entry_points={
        'console_scripts': [
            'inventory = aggravator:cli',
        ]
    }
)

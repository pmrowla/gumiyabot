from setuptools import find_packages, setup
from codecs import open
from os import path


version = '0.1.4'


install_requires = ['aiohttp', 'irc3', 'osuapi']

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='gumiyabot',
    version=version,
    description='Standalone Twitch + Bancho IRC bot for handling osu! beatmap requests',
    long_description=long_description,
    url='https://github.com/pmrowla/gumiyabot',
    author='Peter Rowlands',
    author_email='peter@pmrowla.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Framework :: AsyncIO',
        'Intended Audience :: Developers',
        'Topic :: Games/Entertainment',
        'Topic :: Communications :: Chat :: Internet Relay Chat',
    ],
    keywords='osu twitch gumiya',
    packages=find_packages(exclude=['docs', 'tests']),
    include_package_data=True,
    entry_points={
        'console_scripts': ['gumiyabot = gumiyabot.__main__:main'],
    },
    install_requires=install_requires,
)

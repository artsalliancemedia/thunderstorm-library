from setuptools import find_packages, setup

import thunderstorm


def _read_requirements(requirements_filename):
    with open(requirements_filename) as reqs_file:
        return reqs_file.readlines()


REQUIREMENTS = _read_requirements('requirements.txt')
EXTRA_REQS = {'kafka': ['faust[statsd]==1.9.0', 'kafka-python==1.4.7']}

setup(
    name=thunderstorm.__title__,
    version=thunderstorm.__version__,
    packages=find_packages(),
    include_package_data=True,
    install_requires=REQUIREMENTS,
    extras_require=EXTRA_REQS
)

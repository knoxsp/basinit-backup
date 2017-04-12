
from setuptools import setup

setup(
        name='Hydra Web Interface',
        version='0.1',
        long_description=__doc__,
        packages=['hwi'],
        include_package_data=True,
        zip_safe=False,
        install_requires=['Flask']
)

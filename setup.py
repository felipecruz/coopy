from setuptools import find_packages
from distutils.core import setup

setup(name='coopy',
      version='0.4.5b',
      description='coopy - plain objects persistence/prevalence tool',
      author='Felipe Cruz',
      author_email='felipecruz@loogica.net',
      url='http://coopy.readthedocs.org',
      packages=find_packages(),
      install_requires=['six'])

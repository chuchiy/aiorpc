from setuptools import setup, find_packages

version = '0.0.1'

install_requires = open('requirements.txt').read().strip().split()
tests_requires = install_requires + ['pytest-asyncio']
setup(name='aiorpc',
      description='python3 asyncio based msgpack-rpc compliance rpc server and client',
      version=version,
      author='Chu-Chi Yang', 
      author_email='chuchiyang@outlook.com', 
      packages=find_packages(), 
      install_requires=install_requires,
      tests_require=tests_requires
)

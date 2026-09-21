import re

from setuptools import find_packages, setup

# get version from __version__ variable in bog_connector/__init__.py
with open("bog_connector/__init__.py", "rb") as f:
	version_match = re.search(
		r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', f.read().decode("utf-8")
	)
	version = version_match.group(1) if version_match else "0.0.1"

with open("requirements.txt") as f:
	install_requires = [line.strip() for line in f if line.strip()]

setup(
	name="bog_connector",
	version=version,
	description="Bank of Georgia Business Online API integration for ERPNext: syncs account statements into Bank Transaction records.",
	author="Talorim",
	author_email="shalva@talorim.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)

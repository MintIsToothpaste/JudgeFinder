from setuptools import find_packages, setup

setup(
    name="judgefinder",
    version="0.1.0",
    description="CLI-first recruitment notice collector for municipality judge panels.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.1",
        "requests>=2.31",
        "beautifulsoup4>=4.12",
        "sqlalchemy>=2.0",
        "tomli>=2.0; python_version < '3.11'",
        "tzdata>=2024.1",
    ],
    entry_points={"console_scripts": ["judgefinder=judgefinder.interfaces.cli.main:app"]},
)

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="glimpser",
    version="0.2.7",
    author="Kristopher Kubicki",
    author_email="kristopher@glimpser.net",
    description="A real-time monitoring application for capturing and analyzing live data from various sources",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/KristopherKubicki/glimpser",
    packages=find_packages(),
    install_requires=requirements,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "glimpser=main:main",
            "glimpser-clear=main:clear_console_cli",
        ],
    },
)

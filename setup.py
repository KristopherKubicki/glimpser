from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="glimpser",
    version="0.1.0",
    author="Kristopher Kubicki",
    author_email="kristopher@glimser.net",
    description="A real-time monitoring application for capturing and analyzing live data from various sources",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/glimpser",
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
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "glimpser=glimpser.main:main",
        ],
    },
)


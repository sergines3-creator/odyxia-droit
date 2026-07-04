# setup.py
# COR — Package Python installable
# Usage futur (phase 2, quand Cor v1.0 est stable) :
#   pip install -e .        ← développement local
#   pip install cor         ← depuis PyPI

from setuptools import setup, find_packages

setup(
    name             = "cor",
    version          = "0.1.0-dev",
    description      = "COR — Modèle de langage juridique africain (Decoder-Only)",
    long_description = open("README.md", encoding="utf-8").read(),
    author           = "ODYXIA",
    python_requires  = ">=3.10",
    packages         = find_packages(exclude=["tests*", "scripts*", "server*"]),
    install_requires = [
        "torch>=2.0.0",
        "flask>=3.0.0",
        "flask-limiter>=3.5.0",
        "numpy>=1.24.0",
        "python-dotenv>=1.0.0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3.10",
    ],
)
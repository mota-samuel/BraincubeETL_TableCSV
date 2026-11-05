"""Ponto de entrada. Delega para o CLI do pacote src."""
import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
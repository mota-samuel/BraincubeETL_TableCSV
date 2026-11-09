"""Configuração de log única para toda a aplicação."""
import logging
import sys
from pathlib import Path


def setup(level: int = logging.INFO, log_file: Path | None = None) -> None:
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(formato)
    root.addHandler(saida)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        arquivo = logging.FileHandler(log_file, encoding="utf-8")
        arquivo.setFormatter(formato)
        root.addHandler(arquivo)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
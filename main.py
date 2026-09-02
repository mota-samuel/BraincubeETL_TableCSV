""""
from Core.scheduler import start

if __name__ == "__main__":
    start()
"""

import sys
from Core.extractor import executar
from Core.scheduler import start
from Utils.logger import log
import logging
import http.client as http_client
"""
http_client.HTTPConnection.debuglevel = 1

logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)
"""
def main():
    if "run" in sys.argv:
        log("Execução manual iniciada...")
        executar()
        log("Execução finalizada.")
    else:
        log("Iniciando scheduler...")
        start()

if __name__ == "__main__":
    main()
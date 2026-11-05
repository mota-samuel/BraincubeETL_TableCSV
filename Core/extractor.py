from braincube_connector import client, braincube
from concurrent.futures import ThreadPoolExecutor
from Core.worker import processar_memory_base
from Utils.logger import log
import json

def executar():
    with open("config.json") as f:
        config = json.load(f)

    api = config["api"]

    cli = client.get_instance(config_dict={
        "api_key": api["api_key"],
        "domain": api["domain"]
    })

    bc = braincube.get_braincube(api["braincube"])

    memory_bases = bc.get_memory_base_list()

    # Filtra apenas a memory base configurada
    # mb_config = api.get("memory_base")
    # if mb_config is not None:
    #     memory_bases = [
    #         mb for mb in memory_bases
    #         if str(getattr(mb, "id", getattr(mb, "Id", ""))) == str(mb_config)
    #     ]

    log(f"Total de Memory Bases: {len(memory_bases)}")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
        for mb in memory_bases:
            futures.append(executor.submit(processar_memory_base, bc, mb))
        for f in futures:
            f.result()
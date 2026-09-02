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
    print(memory_bases)

    for mb in memory_bases:
        print("--------")
        print("\nOBJETO:", mb)
        print("\nDIR:", dir(mb))
        print("\nDICT:", getattr(mb, "__dict__", "Sem __dict__"))

    log(f"Total de Memory Bases: {len(memory_bases)}")

    # 🔥 paralelismo controlado
    log("CHEGUEI ANTES DO PROCESSAMENTO")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []

        for mb in memory_bases:
            futures.append(executor.submit(processar_memory_base, bc, mb))

        for f in futures:
            f.result()
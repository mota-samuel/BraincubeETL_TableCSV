from braincube_connector import braincube, client
import json
import pandas as pd
import os
import requests

original_request = requests.Session.request

def intercept(self, method, url, **kwargs):
    print("\n==============================")
    print("METHOD:", method)
    print("URL:", url)
    print("HEADERS:", kwargs.get("headers"))
    print("BODY:", kwargs.get("data") or kwargs.get("json"))
    print("==============================\n")

    return original_request(self, method, url, **kwargs)

requests.Session.request = intercept

# =========================================
# 🔐 CONFIG
# =========================================
with open("config.json") as f:
    config = json.load(f)

api = config["api"]

cli = client.get_instance(config_dict={
    "api_key": api["api_key"],
    "domain": api["domain"]
})

bc = braincube.get_braincube(api["braincube"])

print("Conectado com sucesso!")

# =========================================
# COLETAR DADOS
# =========================================
dados = []

mbs = bc.get_memory_base_list()

#,var = mbs[1].get_variable_list()
# inicio
for mb in mbs:
    mb_name = mb.get_name()
    mb_id = mb.get_bcid()

    varTag = mb.get_variable_list()

    for var in varTag:
        dados.append({
            "Memory Base": mb_name,
            "MB_ID": mb_id,
            "Variable_ID": var.get_bcid(),
            "Variable_Name": var.get_name(),
            "UUID": var.get_uuid()
        })

# =========================================
# CRIAR TABELA
# =========================================

df = pd.DataFrame(dados)

nome_arquivo = "braincube_variables.xlsx"
df.to_excel(nome_arquivo, index=False)

caminho_arquivo = os.path.abspath(nome_arquivo)

print(f"Arquivo salvo em: {caminho_arquivo}")

os.startfile(caminho_arquivo)

# fim

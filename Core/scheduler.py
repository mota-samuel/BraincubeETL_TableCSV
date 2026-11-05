import schedule
import time
import json
from Core.extractor import executar

def start():
    with open("config.json") as f:
        config = json.load(f)

    for job in config["agendamentos"]:
        if "intervalo_minutos" in job:
            intervalo = job["intervalo_minutos"]
            schedule.every(intervalo).minutes.do(executar)
            print(f"Agendado: a cada {intervalo} minutos")
        elif "horarios" in job:
            for h in job["horarios"]:
                schedule.every().day.at(h).do(executar)
                print(f"Agendado: diariamente às {h}")

    print("Scheduler rodando...")

    while True:
        schedule.run_pending()
        time.sleep(30)
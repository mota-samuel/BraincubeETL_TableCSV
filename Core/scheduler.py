import schedule
import time
import json
from Core.extractor import executar

def start():
    with open("config.json") as f:
        config = json.load(f)

    for job in config["agendamentos"]:
        for h in job["horarios"]:
            schedule.every().day.at(h).do(executar)

    print("Scheduler rodando...")

    while True:
        schedule.run_pending()
        time.sleep(30)
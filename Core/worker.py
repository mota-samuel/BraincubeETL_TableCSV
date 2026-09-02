import os
import pandas as pd
from Utils.state import load_state, save_state
from Utils.period import aplicar
from Utils.logger import log


def processar_memory_base(bc, mb):
    nome_mb = mb.get_name()
    id_mb = mb.get_bcid()

    log(f"🔵 Iniciando MB: {nome_mb}")

    state = load_state()

    try:
        variaveis = mb.get_variable_list()
    except Exception as e:
        log(f"❌ Erro ao listar variáveis {nome_mb}: {e}")
        return

    for var in variaveis:
        try:
            var_nome = var.get_name().replace("/", "_").replace("\\", "_")
            var_id = var.get_bcid()

            chave = f"{id_mb}_{var_id}"
            ultima = state.get(chave)

            # 🔥 consulta
            df = mb.get_data([var_id], dataframe=True)

            if df is None or df.empty:
                continue

            # 🔥 define path base
            base_path = f"data/raw/full/{nome_mb.replace(' ', '_')}"
            os.makedirs(base_path, exist_ok=True)

            path = f"{base_path}/{var_nome}.csv"

            # =====================================================
            # 🧠 CASO 1: TEM _order (dados temporais)
            # =====================================================
            if "_order" in df.columns:
                df["_order"] = pd.to_datetime(df["_order"])

                # 🔥 incremental
                if ultima:
                    df = df[df["_order"] > pd.to_datetime(ultima)]

                if df.empty:
                    continue

                modo = "a"
                header = not os.path.exists(path)

                df.to_csv(path, mode=modo, header=header, index=False)

                # 🔥 salva estado
                state[chave] = str(df["_order"].max())

                # 🔥 aplica períodos
                try:
                    df_full = pd.read_csv(path)
                    df_full["_order"] = pd.to_datetime(df_full["_order"])

                    periodos = aplicar(df_full)

                    for nome_periodo, dfp in periodos.items():
                        p_path = f"data/raw/{nome_periodo}/{nome_mb.replace(' ', '_')}"
                        os.makedirs(p_path, exist_ok=True)

                        dfp.to_csv(f"{p_path}/{var_nome}.csv", index=False)

                except Exception as e:
                    log(f"⚠️ Erro ao aplicar períodos {var_nome}: {e}")

            # =====================================================
            # 🔵 CASO 2: SEM _order (snapshot)
            # =====================================================
            else:
                log(f"⚠️ Snapshot (sem _order): {var_nome}")

                # 🔥 sobrescreve sempre (não incremental)
                df.to_csv(path, index=False)

        except Exception as e:
            log(f"❌ Erro MB {nome_mb} VAR {var_nome}: {e}")

    save_state(state)

    log(f"🟢 Finalizado MB: {nome_mb}")
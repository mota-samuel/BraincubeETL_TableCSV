from datetime import timedelta

def aplicar(df):
    max_data = df["_order"].max()

    return {
        "7d": df[df["_order"] >= max_data - timedelta(days=7)],
        "14d": df[df["_order"] >= max_data - timedelta(days=14)],
        "30d": df[df["_order"] >= max_data - timedelta(days=30)]
    }
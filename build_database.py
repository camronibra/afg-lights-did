import sqlite3
from pathlib import Path

import pandas as pd

csv_file = Path("data/viirs_monthly.csv")
schema_file = Path("sql/schema.sql")
database_file = Path("data/lights.sqlite")

def main():
    lights = pd.read_csv(csv_file)

    connection = sqlite3.connect(database_file)

    # 1. Build the empty table and the view (this wipes any old version first)
    connection.executescript(schema_file.read_text())

    # 2. Pour the CSV rows into the empty table - the CHECK rules are tested here
    lights.to_sql("viirs_monthly", connection, if_exists="append", index=False)

    connection.commit()
    connection.close()

    print(f"Built {database_file} with {len(lights)} rows")


if __name__ == "__main__":
    main()
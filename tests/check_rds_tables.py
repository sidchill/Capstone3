from dotenv import load_dotenv
import os
import psycopg2

load_dotenv()

connection = psycopg2.connect(
    host=os.environ["RDS_HOST"],
    port=os.getenv("RDS_PORT", "5432"),
    dbname=os.environ["RDS_DATABASE"],
    user=os.environ["RDS_USER"],
    password=os.environ["RDS_PASSWORD"],
    sslmode="require",
)

try:
    with connection.cursor() as cursor:
        for table in ("clients", "projects", "consultants", "invoices"):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"{table}: {cursor.fetchone()[0]} rows")
finally:
    connection.close()
import os
from google.cloud import bigquery
from google.oauth2 import service_account

cert = os.getenv("BACKEND_SERVICE_ACCOUNT")
credentials = service_account.Credentials.from_service_account_info(
    cert, scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
client = bigquery.Client(project=credentials.project_id, credentials=credentials)


def create_transactions_table():
    schema = [
        bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("amount", "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("date", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("balance", "FLOAT64", mode="REQUIRED"),
    ]
    table_ref = client.dataset("trans_dataset").table("user_transactions")

    try:
        client.get_table(table_ref)  # Returns table if exists
        print("Table already exists! Skipping creation.")
        return
    except Exception:
        pass

    table = bigquery.Table(table_ref, schema=schema)
    client.create_table(table)
    print("Fresh new table created! ✨")


try:
    datasets = list(client.list_datasets())
    print(f"Successfully connected to project {credentials.project_id}")
    print(f"Found {len(datasets)} datasets")
except Exception as e:
    print(f"Connection failed: {str(e)}")

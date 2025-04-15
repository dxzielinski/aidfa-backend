from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
import google.generativeai as genai
import os
import json
import uuid
from google.cloud import pubsub_v1
from dotenv import load_dotenv
from model import UserLogin, UserRegister, Transaction
import firebase_admin.auth as firebase_auth
from firebase import db
from bigquery import create_transactions_table, client, credentials
import requests
from auth import verify_token
from transactions import extract_transactions_from_pdf

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
firebase_api_key = os.getenv("FIREBASE_API_KEY")
genai.configure(api_key=api_key)
app = FastAPI()

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(credentials.project_id, "user_transactions")


@app.post("/register")
def register_user(user: UserRegister):
    try:
        firebase_user = firebase_auth.create_user(
            email=user.email, password=user.password
        )

        user_ref = db.collection("users").document(firebase_user.uid)
        user_ref.set(
            {
                "full_name": user.full_name,
                "email": user.email,
                "user_id": firebase_user.uid,
            }
        )

        return {"message": "User registered successfully", "user_id": firebase_user.uid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/login")
def login(user: UserLogin):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    payload = {
        "email": user.email,
        "password": user.password,
        "returnSecureToken": True,
    }

    response = requests.post(url, json=payload)
    print(response)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    user_info = response.json()
    uid = user_info.get("localId")  # Firebase UID

    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()

    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found in Firestore")

    return {"idToken": user_info["idToken"], "message": "Login successful"}


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), token: dict = Depends(verify_token)):
    user_id = token["user_id"]
    print(user_id)
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_path = f"temp_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())

    transactions = extract_transactions_from_pdf(file_path)

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions found")

    enriched_transactions = [
        {
            **txn,
            "transaction_id": str(uuid.uuid4()),
            "user_id": user_id,
        }
        for txn in transactions
    ]

    # table_ref = client.dataset("trans_dataset").table("user_transactions")
    # errors = client.insert_rows_json(
    #     table=table_ref,
    #     json_rows=enriched_transactions,
    #     ignore_unknown_values=True
    # )
    # if errors:
    #     raise HTTPException(400, f"BigQuery errors: {errors}")
    for txn in enriched_transactions:
        future = publisher.publish(topic_path, json.dumps(txn).encode("utf-8"))
        # future.result()  # Optional: waits for the publish to complete

    return {"transactions": transactions}


@app.get("/spending-trends")
async def upload_pdf(token: dict = Depends(verify_token)):
    user_id = token["user_id"]
    full_table = f"{credentials.project_id}.trans_dataset.user_transactions"
    query = f"""
     WITH base AS (
  SELECT
    EXTRACT(YEAR FROM date) AS year,
    EXTRACT(MONTH FROM date) AS month,
    category,
    SUM(amount) AS total_spent
  FROM `{full_table}`
  WHERE amount < 0
  GROUP BY year, month, category
),
ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY year, month
      ORDER BY total_spent ASC
    ) AS rank
  FROM base
)
SELECT *
FROM ranked
WHERE rank = 1
ORDER BY year, month
    """
    monthly_trends = client.query(query).to_dataframe()
    monthly_trends_json_str = json.dumps(
        monthly_trends.to_dict(orient="records"), indent=2
    )

    monthly_trends_json = monthly_trends.to_dict(orient="records")

    return monthly_trends_json


if __name__ == "__main__":
    create_transactions_table()
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)

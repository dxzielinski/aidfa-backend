from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
import tempfile
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
import datetime
from firebase_admin import firestore

load_dotenv()
raw_json = os.getenv("BACKEND_SERVICE_ACCOUNT")
with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
    tf.write(raw_json)
    tf.flush()
    temp_path = tf.name

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path

api_key = os.getenv("GEMINI_API_KEY")
firebase_api_key = os.getenv("FIREBASE_API_KEY")
genai.configure(api_key=api_key)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
        "https://aidfa-frontend-804472887420.europe-central2.run.app",
        "http://localhost:3000",
    ],  # or ["*"] for full access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

publisher = pubsub_v1.PublisherClient(credentials=credentials)
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
async def spending_trends(token: dict = Depends(verify_token)):
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
        WHERE amount < 0 AND user_id = '{user_id}'
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

    monthly_trends_json = monthly_trends.to_dict(orient="records")
    for record in monthly_trends_json:
        year = int(record["year"])
        month = int(record["month"])
        doc_id = f"{year:04d}-{month:02d}"  # 2025-05
        doc_ref = (
            db.collection("analysis_summaries")
            .document(user_id)
            .collection("spending_trends")
            .document(doc_id)
        )
        doc_ref.set(record)
    return monthly_trends_json


@app.get("/analysis/spending-trends")
def get_spending_trends_analysis(token: dict = Depends(verify_token)):
    user_id = token["user_id"]

    collection_ref = (
        db.collection("analysis_summaries")
        .document(user_id)
        .collection("spending_trends")
    )

    docs = collection_ref.order_by(
        "__name__", direction=firestore.Query.DESCENDING
    ).stream()

    trends = [doc.to_dict() | {"month_id": doc.id} for doc in docs]

    return {"user_id": user_id, "spending_trends": trends}


@app.get("/predictions/spending")
def get_user_predictions(token: dict = Depends(verify_token)):
    user_id = token["user_id"]
    full_model = f"{credentials.project_id}.trans_dataset.spending_forecast_model"
    query = f"""
    SELECT
      user_id,
      forecast_timestamp,
      forecast_value,
      prediction_interval_lower_bound,
      prediction_interval_upper_bound
    FROM ML.FORECAST(
      MODEL `{full_model}`,
      STRUCT(3 AS horizon, 0.8 AS confidence_level)
    )
    WHERE user_id = '{user_id}'
    """

    forecast = client.query(query).to_dataframe()

    readable_output = []
    history_doc_id = str(uuid.uuid4())

    for _, row in forecast.iterrows():
        entry = {
            "month": row["forecast_timestamp"].strftime("%B %Y"),
            "expected_spending": float(row["forecast_value"]),
            "range": {
                "lower": float(row["prediction_interval_lower_bound"]),
                "upper": float(row["prediction_interval_upper_bound"]),
            },
        }
        readable_output.append(entry)

    doc_ref = (
        db.collection("users")
        .document(user_id)
        .collection("prediction_history")
        .document(history_doc_id)
    )
    doc_ref.set(
        {
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "predictions": readable_output,
        }
    )

    return {"user_id": user_id, "predictions": readable_output}


@app.get("/predictions/history")
def get_prediction_history(token: dict = Depends(verify_token)):
    user_id = token["user_id"]

    history_ref = (
        db.collection("users").document(user_id).collection("prediction_history")
    )
    docs = history_ref.order_by(
        "created_at", direction=firestore.Query.DESCENDING
    ).stream()

    history = []
    for doc in docs:
        data = doc.to_dict()
        history.append(
            {
                "id": doc.id,
                "created_at": data.get("created_at"),
                "predictions": data.get("predictions", []),
            }
        )

    return {"user_id": user_id, "history": history}


if __name__ == "__main__":
    create_transactions_table()
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)

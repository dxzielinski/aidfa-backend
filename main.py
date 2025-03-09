from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from pydantic import BaseModel
import firebase_admin
from firebase_admin import auth, credentials
import google.generativeai as genai
import os
import os
import csv
import io
from dotenv import load_dotenv

# Initialize Firebase Admin SDK
# cred = credentials.Certificate("firebase_service_account.json")
# firebase_admin.initialize_app(cred)

# Dependency to verify Firebase ID token
# async def verify_token(authorization: str = Header(None)):
#     if not authorization or not authorization.startswith("Bearer "):
#         raise HTTPException(status_code=401, detail="Unauthorized")
#     id_token = authorization.split("Bearer ")[1]
#     try:
#         decoded_token = auth.verify_id_token(id_token)
#         return decoded_token
#     except Exception as e:
#         raise HTTPException(status_code=401, detail="Invalid token")

load_dotenv()

api_key=os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
print(api_key)
app = FastAPI()

class Transaction(BaseModel):
    date: str
    amount: float
    description: str
    category: str
    
def parse_csv(file):
    transactions = []
    csv_reader = csv.DictReader(io.StringIO(file.decode("utf-8")))
    for row in csv_reader:
        transactions.append({
            "date": row["date"],
            "amount": float(row["amount"]),
            "description": row["description"],
            "balance": float(row["balance"])
        })
    return transactions


def categorize_transaction(description):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    Categorize the following transaction description into one of these categories:
    - Food & Dining
    - Utilities
    - Shopping
    - Transportation
    - Entertainment
    - Income
    - Other

    Description: {description}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

@app.post("/process-transactions")
async def process_transactions(
    file: UploadFile = File(...),  
    # decoded_token: dict = Depends(verify_token)
):
    # user_id = decoded_token["uid"]
    # print(f"Processing transactions for user: {user_id}")

    try:
        file_content = await file.read()
        transactions = parse_csv(file_content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing CSV: {str(e)}")

    categorized_transactions = []
    for transaction in transactions:
        category = categorize_transaction(transaction["description"])
        categorized_transactions.append({
            **transaction,
            "category": category,
            "type": "income" if transaction["amount"] >= 0 else "expense"
        })

    prompt = "Analyze the following financial data and provide insights:\n"
    for transaction in categorized_transactions:
        prompt += f"- {transaction['date']}: {transaction['description']} (${abs(transaction['amount'])}, {transaction['type']}, {transaction['category']}, Balance: ${transaction['balance']})\n"

    prompt += """
    Insights should include:
    1. Spending trends over time.
    2. Budget recommendations.
    3. Savings tips.
    4. Balance trends and suggestions for improving savings.
    """

    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    return {"insights": response.text, "transactions": categorized_transactions}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
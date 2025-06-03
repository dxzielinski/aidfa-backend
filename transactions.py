import json
import re
from pypdf import PdfReader
import pandas as pd
from fastapi import FastAPI
from datetime import datetime
import csv
import io
import google.generativeai as genai

app = FastAPI()

TRANSACTION_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4})\s+([\w\s]+)\s+(-?\d+\.\d{2})")


def extract_transactions_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    lines = [line.strip() for line in full_text.split("\n") if line.strip()]

    transactions = []

    start_reading = False
    for line in lines:
        if "Transaction Date" in line:
            start_reading = True
            continue
        if not start_reading:
            continue

        match = re.match(
            r"(\d{2} \w+ \d{4})\s+(.+?)\s+([+-]?\d+\.\d{2})\s+(\d+\.\d{2})", line
        )
        if match:
            date_str, description, amount_str, balance_str = match.groups()
            try:
                date_obj = datetime.strptime(date_str, "%d %b %Y")
                amount = float(amount_str)
                balance = float(balance_str)
                transactions.append(
                    {
                        "date": date_obj.isoformat() + "Z",
                        "description": description.strip(),
                        "amount": amount,
                        "balance": balance,
                        "category": None,
                    }
                )
            except ValueError:
                pass
    descriptions = [tx["description"] for tx in transactions]
    categories = categorize_transaction(descriptions)
    print(len(categories))
    print(len(descriptions))

    for tx, cat in zip(transactions, categories):
        tx["category"] = cat
    filtered_transactions = [
        transaction
        for transaction in transactions
        if transaction["category"] not in [None, ""]
    ]
    return filtered_transactions


def categorize_transaction(descriptions):
    length = len(descriptions)
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = """
        Categorize the following transaction descriptions into one of these categories:
        - Food & Dining
        - Groceries
        - Utilities
        - Shopping
        - Transportation
        - Entertainment
        - Income
        - Rent
        - Travel
        - Transfers
        
        Keep in mind the data is for Poland and organizations may be Polish.
        Return a JSON array of the categories, in the same order as the input.
        The array should also have the same amount of entries as the input, there are {length} entries.

        Descriptions:
        """ + "\n".join(f"- {desc}" for desc in descriptions)

    response = model.generate_content(prompt)
    cleaned_text = re.sub(r"```json|```", "", response.text).strip()
    categories = json.loads(cleaned_text)

    return categories


def parse_csv(file):
    transactions = []
    csv_reader = csv.DictReader(io.StringIO(file.decode("utf-8")))
    for row in csv_reader:
        transactions.append(
            {
                "date": row["date"],
                "amount": float(row["amount"]),
                "transaction": row["description"],
                "balance": float(row["balance"]),
            }
        )
    return transactions

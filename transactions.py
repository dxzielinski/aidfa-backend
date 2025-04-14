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
    i = 0

    # Pattern to match lines like:
    # description possibly with numbers ... amount PLN balance PLN
    pattern = re.compile(
        r"(?P<desc>.+?)\s+(?P<sign>-)?(?P<amount>\d[\d\s.,]*)\s*PLN\s+(?P<balance>\d[\d\s.,]*)\s*PLN",
        re.IGNORECASE
    )

    while i < len(lines):
        # Look for a date
        if re.match(r"\d{2}\s\w+\s\d{4}", lines[i].lower()):
            date = lines[i]
            i += 1

            if i < len(lines) and "booking date" in lines[i].lower():
                i += 1

            # Description lines may span multiple lines
            desc_lines = []
            while i < len(lines) and not re.search(r"PLN\s+\d", lines[i]):
                desc_lines.append(lines[i])
                i += 1

            # Next line likely contains amount + balance
            if i < len(lines):
                line = " ".join(desc_lines + [lines[i]])
                match = pattern.search(line)
                if match:
                    description = match.group("desc").strip()
                    amount_raw = match.group("amount").replace(" ", "").replace(",", ".")
                    balance_raw = match.group("balance").replace(" ", "").replace(",", ".")
                    try:
                        amount = float(amount_raw)
                        if match.group("sign") == "-":
                            amount *= -1
                        balance = float(balance_raw)
                        date_object = datetime.strptime(date, "%d %b %Y")
                        transactions.append({
                            "date": date_object.timestamp(),
                            "description": re.sub(r'\S*\*{2,}\S*', '', description),
                            "amount": amount,
                            "balance": balance,
                            "category": None
                        })
                    except ValueError:
                        pass
                i += 1
        else:
            i += 1
    descriptions = [tx["description"] for tx in transactions]
    categories = categorize_transaction(descriptions)
    print(len(categories))
    print(len(descriptions))

    for tx, cat in zip(transactions, categories):
        tx["category"] = cat
    filtered_transactions = [transaction for transaction in transactions if transaction["category"] not in [None, ""]]
    return filtered_transactions

def categorize_transaction(descriptions):
    length = len(descriptions)
    model = genai.GenerativeModel('gemini-2.0-flash')
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
        transactions.append({
            "date": row["date"],
            "amount": float(row["amount"]),
            "transaction": row["description"],
            "balance": float(row["balance"])
        })
    return transactions

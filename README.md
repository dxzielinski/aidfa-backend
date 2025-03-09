# AI-Driven Financial Analyzer

ADFA is a project that lets you upload a CSV via an API endpoint to get an AI analysis of your transactions.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install the requirements.

```bash
pip install -r requirements.txt
```
## Environment Variables
Create a `.env` file in the root directory with the following variables:
```env
# .env
GEMINI_API_KEY=your_gemini_api_key_here
```
## Running

```bash
python main.py
```
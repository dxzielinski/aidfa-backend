import os
import firebase_admin
from firebase_admin import credentials, firestore

cert = os.getenv("BACKEND_SERVICE_ACCOUNT")
cred = credentials.Certificate(cert)
firebase_admin.initialize_app(cred)
db = firestore.client(database_id="proj")

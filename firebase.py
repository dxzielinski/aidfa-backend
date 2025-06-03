import os
import firebase_admin
from firebase_admin import credentials, firestore

cert = os.getenv("FIREBASE_SERVICE_ACCOUNT")
with open("cert-firebase.json", "w") as f:
    f.write(cert)

cred = credentials.Certificate("cert-firebase.json")
firebase_admin.initialize_app(cred)
db = firestore.client(database_id="proj")

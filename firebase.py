import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate(
    "steadfast-wares-453916-n8-firebase-adminsdk-fbsvc-168d7e9cf7.json"
)
firebase_admin.initialize_app(cred)
db = firestore.client(database_id="proj")

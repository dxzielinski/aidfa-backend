from fastapi import  HTTPException, Header
from firebase_admin import auth

from firebase import db

def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        token_type, id_token = authorization.split()
        if token_type.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid token format")

        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token["uid"]

        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found in Firestore")

        return user_doc.to_dict()  # Return user info

    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
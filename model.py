from pydantic import BaseModel


class UserRegister(BaseModel):
    email: str
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: str
    password: str

class Transaction(BaseModel):
    date: str
    amount: float
    description: str
    category: str

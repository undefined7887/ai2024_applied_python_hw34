import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_DATABASE = int(os.getenv("REDIS_DATABASE", default=0))

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", default="HS256")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_EXPIRATION_SECONDS = int(os.getenv("JWT_EXPIRATION_SECONDS", default=3600))

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# .env'i yükle
load_dotenv()

USER = os.getenv("DB_USER")
PASSWORD = os.getenv("DB_PASSWORD")
HOST = os.getenv("DB_HOST")
PORT = os.getenv("DB_PORT")
NAME = os.getenv("DB_NAME")
POOL_SIZE=int(os.getenv("POOL_SIZE"))
MAX_OVERFLOW=int(os.getenv("MAX_OVERFLOW"))

DATABASE_URL = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{NAME}"

engine = create_engine(DATABASE_URL, echo=True,pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()

from typing import List, Optional
from datetime import datetime

from sqlalchemy import create_engine, text, ForeignKey, String, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column, relationship

from app.config import DATABASE_URL
from app.utils import generate_short_code, generate_uuid4

Base = declarative_base()


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid4)
    nickname: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)

    links: Mapped[List["Link"]] = relationship(back_populates="user")


class Link(Base):
    __tablename__ = "link"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_short_code)
    user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("user.id"), nullable=True)
    url: Mapped[str] = mapped_column(String)

    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_access_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expire_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="links")


engine = create_engine(DATABASE_URL)

# Get session constructor
Session = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)

    # ping the database
    with Session() as session:
        try:
            session.execute(text("SELECT 1"))
        except Exception as e:
            print(f"Database connection error: {e}")
            raise
        else:
            print("Database connection successful")


def get_db():
    session = Session()
    try:
        yield session
    finally:
        session.close()

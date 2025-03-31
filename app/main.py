from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timedelta

from bcrypt import checkpw, hashpw, gensalt
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import Response, RedirectResponse
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from redis import Redis

from app.config import JWT_EXPIRATION_SECONDS, JWT_SECRET_KEY, JWT_ALGORITHM
from app.redis import get_redis
from app.sql import init_db, get_db, User, Link


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    yield


app = FastAPI(lifespan=lifespan)


#
# Auth
#

class AuthRegisterRequest(BaseModel):
    username: str
    password: str


class AuthRegisterResponse(BaseModel):
    id: str


@app.post("/auth/register")
async def auth_register(request: AuthRegisterRequest, db: Session = Depends(get_db)):
    password_hash = hashpw(request.password.encode(), salt=gensalt()).decode()

    user = User(nickname=request.username, password_hash=password_hash)

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()

        raise HTTPException(status_code=409, detail="User with this username already exists")

    return AuthRegisterResponse(id=user.id)


class AuthTokenRequest(BaseModel):
    username: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str


@app.post("/auth/token", response_model=AuthTokenResponse)
async def auth_token(request: AuthTokenRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.nickname == request.username).first()

    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    if not checkpw(request.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    claims = {
        "sub": user.id,
        "exp": int((datetime.now() + timedelta(seconds=JWT_EXPIRATION_SECONDS)).timestamp())
    }

    access_token = jwt.encode(claims, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    return AuthTokenResponse(access_token=access_token)


#
# Links
#

def get_user_id(request: Request, jwt_secret_key=JWT_SECRET_KEY, jwt_algorithm=JWT_ALGORITHM):
    header = request.headers.get("Authorization")

    if not header or not header.startswith("Bearer "):
        return None

    access_token = header.split(" ")[1]

    # Check access token
    try:
        claims = jwt.decode(access_token, jwt_secret_key, algorithms=[jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Access token malformed")

    return claims.get("sub")


def get_user_id_strict(request: Request):
    user_id = get_user_id(request)

    if user_id is None:
        raise HTTPException(status_code=401)

    return user_id


class LinksShortenRequest(BaseModel):
    url: str
    expire_at: datetime
    alias: Optional[str] = None


class LinksShortenResponse(BaseModel):
    id: str


@app.post("/links/shorten", response_model=LinksShortenResponse)
async def links_shorten(request: LinksShortenRequest,
                        user_id: Optional[str] = Depends(get_user_id),
                        db: Session = Depends(get_db)):
    if request.expire_at < datetime.now():
        raise HTTPException(status_code=400, detail="expire_at must be in the future")

    link = Link(user_id=user_id, url=request.url, expire_at=request.expire_at)

    if request.alias:
        link.id = request.alias

    try:
        db.add(link)
        db.commit()
        db.refresh(link)
    except IntegrityError:
        db.rollback()

        raise HTTPException(status_code=409, detail="Alias already exists")

    # noinspection PyTypeChecker
    return LinksShortenResponse(id=link.id)


class LinkDTO(BaseModel):
    id: str
    url: str
    access_count: int
    last_access_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    expire_at: datetime


def map_link_to_dto(link: Link) -> LinkDTO:
    return LinkDTO(
        id=link.id,
        url=link.url,
        access_count=link.access_count,
        last_access_at=link.last_access_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
        expire_at=link.expire_at
    )


class LinksListResponse(BaseModel):
    links: list[LinkDTO]


@app.get("/links", response_model=LinksListResponse)
async def links_list(user_id: str = Depends(get_user_id_strict), db: Session = Depends(get_db)):
    links = db.query(Link).filter(Link.user_id == user_id).all()

    # noinspection PyTypeChecker
    return LinksListResponse(links=list(map(map_link_to_dto, links)))


class LinksSearchResponse(BaseModel):
    links: list[LinkDTO]


@app.get("/links/search", response_model=LinksSearchResponse)
async def links_search(original_url: str,
                       user_id: str = Depends(get_user_id_strict),
                       db: Session = Depends(get_db)):
    if not original_url:
        raise HTTPException(status_code=400, detail="original_url query parameter is required")

    links = db.query(Link).filter(Link.user_id == user_id, Link.url.contains(original_url)).all()

    # noinspection PyTypeChecker
    return LinksSearchResponse(links=list(map(map_link_to_dto, links)))


@app.get("/links/{link_id}")
async def links_redirect(link_id: str, db: Session = Depends(get_db), redis: Redis = Depends(get_redis)):
    link_cache_key = f"link:{link_id}"

    cached_url = redis.get(link_cache_key)
    if cached_url:
        original_url = cached_url
    else:
        link = db.query(Link).filter(Link.id == link_id, Link.expire_at > datetime.now()).first()

        if link is None:
            raise HTTPException(status_code=404, detail="Link not found")

        original_url = link.url

        expire_secs = int((link.expire_at - datetime.now()).total_seconds())

        # noinspection PyAsyncCall,PyTypeChecker
        redis.setex(link_cache_key, expire_secs, original_url)

    # Update stats
    db.query(Link).filter(Link.id == link_id).update({
        Link.access_count: Link.access_count + 1,
        Link.last_access_at: datetime.now()
    })
    db.commit()

    # Redirect to the original URL with a 301 status code
    # noinspection PyTypeChecker
    return RedirectResponse(status_code=301, url=original_url)


@app.get("/links/{link_id}/stats", response_model=LinkDTO)
async def links_stats(link_id: str,
                      user_id: str = Depends(get_user_id_strict),
                      db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.id == link_id, Link.user_id == user_id).first()

    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")

    # noinspection PyTypeChecker
    return map_link_to_dto(link)


class LinkUpdateRequest(BaseModel):
    url: str


@app.put("/links/{link_id}")
async def links_update(link_id: str,
                       request: LinkUpdateRequest,
                       user_id: str = Depends(get_user_id_strict),
                       db: Session = Depends(get_db)):
    link = db.query(Link).filter(Link.id == link_id, Link.user_id == user_id).first()

    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")

    link.url = request.url
    link.updated_at = datetime.now()

    db.commit()

    return Response(status_code=204)


@app.delete("/links/{link_id}")
async def links_delete(link_id: str,
                       user_id: str = Depends(get_user_id_strict),
                       db: Session = Depends(get_db),
                       redis: Redis = Depends(get_redis)):
    link_cache_key = f"link:{link_id}"

    link = db.query(Link).filter(Link.id == link_id, Link.user_id == user_id).first()

    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)
    db.commit()

    # Drop cache
    # noinspection PyAsyncCall
    redis.delete(link_cache_key)

    return Response(status_code=204)

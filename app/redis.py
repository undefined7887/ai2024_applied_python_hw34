import redis

from app.config import REDIS_HOST, REDIS_PORT, REDIS_DATABASE


def get_redis():
    client = redis.Redis(host=REDIS_HOST,
                         port=REDIS_PORT,
                         db=REDIS_DATABASE,
                         decode_responses=True)
    try:
        yield client
    finally:
        client.close()

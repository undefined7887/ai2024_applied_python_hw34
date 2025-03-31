import random
import string
import uuid


def generate_uuid4():
    return str(uuid.uuid4())


def generate_short_code(k=10):
    alphabet = string.ascii_letters + string.digits

    return "".join(random.choices(alphabet, k=k))

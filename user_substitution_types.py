import random

def alphanumeric_random(params) :
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join([random.choice(chars) for I in range(params["len"])])

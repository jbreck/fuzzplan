import random

# REMEMBER: parameters set by the user could come in as strings,
#   so please convert them to the type that you expect.

def alphanumeric_random(params) :
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join([random.choice(chars) for I in range(int(params["len"]))])

def numeric_random(params) :
    return random.randint(int(params["min"]),int(params["max"]))

def float_random(params) :
    return random.uniform(float(params["min"]),float(params["max"]))

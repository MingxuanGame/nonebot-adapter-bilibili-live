# https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md

from __future__ import annotations

from functools import reduce
import hashlib
import time
from typing import Any
import urllib.parse

MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


def get_mixin_key(img_key: str, sub_key: str) -> str:
    mix = img_key + sub_key
    return reduce(lambda s, i: s + mix[i], MIXIN_KEY_ENC_TAB, "")[:32]


def get_key(key: str) -> str:
    return key.rsplit("/", 1)[1].split(".")[0]


def wbi_encode(params: dict[str, Any], img_key: str, sub_key: str) -> dict[str, Any]:
    # img_key = get_key(img_key)
    # sub_key = get_key(sub_key)
    mixin_key = get_mixin_key(img_key, sub_key)
    params["wts"] = round(time.time())
    params = dict(sorted(params.items()))
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params

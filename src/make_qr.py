#!/usr/bin/env python3
"""
The QR hunt codes hidden in cl_angkorwat (cubeLadder's /q/<token>, QrHunt). Writes private/qr_codes.json
with each code's token, address, hint and its module matrix (worn: a patch of modules broken off),
which gen_wat.py builds as 3D geometry. The file is the secret: it is in .gitignore here and never goes
to the public repository; without it gen_wat.py leaves the hidden codes out.

Needs segno (make) and zxing-cpp (check that every worn code still decodes):
    python3 make_qr.py              # new tokens (only when there is no private/qr_codes.json yet)
    python3 make_qr.py --check      # decode the stored matrices again
Register the tokens on cubeLadder: bin/cake qr_codes add cl_angkorwat "<label>" --token <token> --hint "<hint>"
"""
import json, os, random, secrets, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "private", "qr_codes.json")
# no look-alikes (0/O, 1/I/L): uppercase + digits keep the code in QR alphanumeric mode, so the address
# fits a 29 x 29 code (version 3) even at the highest error correction (H, about 30 % may be lost)
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODES = [
    {"key": "platform", "label": "great pillar platform, beside the lotus bud",
     "hint": "Not every secret is up high. Wade under the plank and look up."},
    {"key": "plank", "label": "underside of the plank over the flooded pool",
     "hint": "The brave climb the stones to the great pillar. Look down beside the lotus."},
]


def matrix(url, seed):
    import segno
    q = segno.make(url, error="h", mode="alphanumeric", boost_error=False)
    assert q.version == 3, q.version
    rows = [[bool(v) for v in row] for row in q.matrix]
    n = len(rows)
    # wear: a ragged patch of dark modules broken off, away from the three finder patterns and timing lines
    r = random.Random(seed)
    cx, cy = r.randint(12, 20), r.randint(14, 21)
    for y in range(n):
        for x in range(n):
            finder = (x < 9 and y < 9) or (x >= n - 9 and y < 9) or (x < 9 and y >= n - 9)
            if finder or x == 6 or y == 6:
                continue
            if (x - cx) ** 2 + (y - cy) ** 2 * 1.3 < r.uniform(5, 11):
                rows[y][x] = False
    return ["".join("1" if v else "0" for v in row) for row in rows]


def decodes(rows):
    import zxingcpp
    from PIL import Image
    n, q, s = len(rows), 4, 8
    im = Image.new("L", ((n + 2 * q) * s,) * 2, 255)
    px = im.load()
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v == "1":
                for dy in range(s):
                    for dx in range(s):
                        px[(x + q) * s + dx, (y + q) * s + dy] = 0
    r = zxingcpp.read_barcodes(im)
    return r[0].text if r else None


if __name__ == "__main__":
    if "--check" in sys.argv:
        for c in json.load(open(OUT)):
            got = decodes(c["matrix"])
            print(f'{c["key"]:9s} {"ok " if got == c["url"] else "FAIL"} {got}')
        sys.exit(0)
    if os.path.exists(OUT):
        sys.exit(f"{OUT} exists: delete it first for new tokens (and retire the old ones on cubeLadder)")
    out = []
    for i, c in enumerate(CODES):
        token = "".join(secrets.choice(ALPHABET) for _ in range(10))
        url = f"HTTPS://CUBELADDER.OVH/Q/{token}"
        rows = matrix(url, seed=secrets.randbits(32))
        got = decodes(rows)
        assert got == url, (c["key"], got)
        out.append(dict(c, token=token, url=url, matrix=rows))
        print(f'{c["key"]:9s} decodes ok  {url}')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print("written", OUT)

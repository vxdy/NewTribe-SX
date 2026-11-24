import json
from ecc_oracle import oracle
base=oracle(bytes(256))[0][:3]
b0=int.from_bytes(base,'big')
cols=[]
for i in range(256):
    row=[]
    for bit in range(8):
        t=bytearray(256); t[i]=1<<bit
        v=int.from_bytes(oracle(bytes(t))[0][:3],'big')^b0
        row.append(v)
    cols.append(row)
# linearity check on random data
import random
random.seed(5)
for _ in range(5):
    t=bytes(random.getrandbits(8) for _ in range(256))
    v=b0
    for i,b in enumerate(t):
        for bit in range(8):
            if b>>bit&1: v^=cols[i][bit]
    assert v==int.from_bytes(oracle(t)[0][:3],'big'),"not linear"
print("linear ok; base",hex(b0))
json.dump({"base":b0,"cols":cols},open("ecc_matrix.json","w"))

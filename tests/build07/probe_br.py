import sys; sys.path.insert(0,'.')
from reference_trend import *
from helpers import *

T=900
atr=0.0050

bars = [
    Bar(t=T*1,  o=1.0540,h=1.0560,l=1.0520,c=1.0545),
    Bar(t=T*2,  o=1.0550,h=1.0570,l=1.0535,c=1.0558),
    Bar(t=T*3,  o=1.0560,h=1.0580,l=1.0545,c=1.0568),
    Bar(t=T*4,  o=1.0565,h=1.0590,l=1.0552,c=1.0575),
    Bar(t=T*5,  o=1.0570,h=1.0582,l=1.0555,c=1.0565),
    Bar(t=T*6,  o=1.0575,h=1.0595,l=1.0562,c=1.0582),
    Bar(t=T*7,  o=1.0582,h=1.0600,l=1.0568,c=1.0590),  # R high candidate
    Bar(t=T*8,  o=1.0588,h=1.0595,l=1.0572,c=1.0580),
    Bar(t=T*9,  o=1.0578,h=1.0588,l=1.0565,c=1.0572),  # confirms R -> bav will be T*10
    Bar(t=T*10, o=1.0585,h=1.0615,l=1.0582,c=1.0612),  # break bar
    Bar(t=T*11, o=1.0608,h=1.0612,l=1.0595,c=1.0598),  # retest touch low=1.0595 in [1.0590,1.0610]
    Bar(t=T*12, o=1.0600,h=1.0615,l=1.0598,c=1.0610),  # acceptance close>R
    Bar(t=T*13, o=1.0608,h=1.0620,l=1.0602,c=1.0615),
]
for i,b in enumerate(bars):
    b.avail = bars[i+1].t if i+1<len(bars) else b.t+T

eng=Engine('TEST')
eng.set_h1(H1(src=0,avail=T,regime=REGIME.TREND_BULL,qual=RQUAL.NORMAL,valid=True))
for b in bars:
    c=eng.feed(b,atr)
    pend=eng.ctx.pend
    ps = f"p={pend.p} bav={pend.bav} age={pend.age} cons={pend.cons} exp={pend.exp}" if pend else None
    print(f't={b.t} avail={b.avail} pend=[{ps}] cand={c.why if c else None}')
    if c:
        print(f'  f={c.f.name} ent={round(c.ent,4)} inv={round(c.inv,4)}')

# Now check: why didn't eval_br fire at T*11 (acceptance bar)?
print()
print('--- manual eval_br at T*12 (avail=T*13) ---')
ctx = eng.ctx
print(f'pend={ctx.pend}')
# The pend is consumed (cons=True) at T*10 avail=T*11
# eval_br checks: pr.cons must be True -> OK
# acceptance bar scan: bar.avail > pr.bav=T*11, bar.c > pr.p=1.0600
# Let's trace manually
pr = None
for b2 in eng.ctx.breaks:
    if b2.cons: pr = b2; break
if pr:
    print(f'found consumed break: p={pr.p} bav={pr.bav} age={pr.age}')
    print('scanning for acceptance:')
    for bar in eng.completed:
        skip = bar.avail <= pr.bav
        hit = bar.c > pr.p
        print(f'  t={bar.t} avail={bar.avail} c={bar.c} skip={skip} hit={hit}')

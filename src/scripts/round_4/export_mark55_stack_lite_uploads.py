"""Export size-safe Mark55 passive interposition probes.

The first Mark55 stack probes were validator-clean but roughly 107 KB. These
lighter probes keep the high-signal test (one-tick passive VELVET
interposition around Mark55-style flow) while dropping the explicit lot ledger
so the files remain under a 100 KB practical upload ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUB_DIR = REPO_ROOT / "outputs" / "submissions" / "r4"
BASE = SUB_DIR / "submission_r4_exp_stack_hydhardlong80_60k.py"


@dataclass(frozen=True)
class Spec:
    label: str
    gate: str
    side: str

    @property
    def out(self) -> Path:
        return SUB_DIR / f"submission_r4_lite_stack80_m55_interpose_{self.label}.py"


def specs() -> list[Spec]:
    return [
        Spec("bidonly_markgate_s1", "markgate", "bid"),
        Spec("periodic_s1_control", "periodic", "both"),
        Spec("markgate_s1_twosided", "markgate", "both"),
        Spec("always_s1_control", "always", "both"),
        Spec("askonly_markgate_s1", "markgate", "ask"),
    ]


def _rename_final_trader(source: str, new_name: str) -> str:
    marker = "\nclass Trader:"
    index = source.rfind(marker)
    if index < 0:
        raise ValueError("base bundle does not contain a final top-level class Trader")
    return source[:index] + f"\nclass {new_name}:" + source[index + len(marker) :]


APPENDIX = r'''

# R4 lite Mark55 interposition probe. Size-safe execution test only.
_R4M_BASE=_R4MBaseTrader
_R4M_P='VELVETFRUIT_EXTRACT'
_R4M_GATE='__GATE__'
_R4M_SIDE='__SIDE__'
_R4M_SIZE=1

class Trader:
    def __init__(self):
        self.i=_R4M_BASE();self.a=[];self.b=[];self.c=[];self.d=[];self.s=set();self.t=None
    def _p(self,l,t,w):
        return [(x,q) for x,q in l if x>=t-w]
    def _q(self,l):
        r=0
        for _,q in l:r+=q
        return r
    def _ing(self,state):
        t=int(state.timestamp)
        if self.t is not None and t<self.t:
            self.a=[];self.b=[];self.c=[];self.d=[];self.s=set()
        self.t=t
        self.a=self._p(self.a,t,30000);self.b=self._p(self.b,t,5000);self.c=self._p(self.c,t,5000);self.d=self._p(self.d,t,30000)
        for tr in (state.market_trades or {}).get(_R4M_P,[]) or []:
            q=int(getattr(tr,'quantity',0) or 0)
            if q<=0:continue
            tt=int(getattr(tr,'timestamp',t) or t);p=int(getattr(tr,'price',0) or 0)
            by=getattr(tr,'buyer',None);se=getattr(tr,'seller',None);k=(tt,p,q,by,se)
            if k in self.s:continue
            self.s.add(k)
            if by=='Mark 67':self.a.append((tt,q))
            if se=='Mark 55':self.b.append((tt,q))
            if by=='Mark 55':self.c.append((tt,q))
            if se=='Mark 22':self.d.append((tt,q))
    def _g(self,t,side):
        if _R4M_GATE=='always':return True
        if _R4M_GATE=='periodic':return t%10000<1100
        if side=='bid':return len(self.a)>=3 or len(self.b)>0 or self._q(self.d)>=7
        return len(self.c)>0
    def _shift(self,ex,buy,px):
        out=[];done=0
        for o in ex:
            q=int(o.quantity)
            if not done and ((buy and q>0) or ((not buy) and q<0)):
                aq=abs(q);n=min(_R4M_SIZE,aq);r=aq-n
                if r:out.append(Order(_R4M_P,int(o.price),r if buy else -r))
                out.append(Order(_R4M_P,int(px),n if buy else -n));done=1
            else:out.append(o)
        return out,done
    def _ov(self,state,orders):
        depth=state.order_depths.get(_R4M_P)
        if depth is None or not depth.buy_orders or not depth.sell_orders:return orders
        bid=max(depth.buy_orders);ask=min(depth.sell_orders)
        if ask-bid<=1:return orders
        pos=int(state.position.get(_R4M_P,0));t=int(state.timestamp)
        o=dict(orders or {});ex=list(o.get(_R4M_P,[]) or []);ch=False
        if _R4M_SIDE in ('both','bid') and pos<200 and self._g(t,'bid'):
            ex,done=self._shift(ex,True,bid+1)
            if not done and not any(int(x.quantity)>0 for x in ex):ex.append(Order(_R4M_P,int(bid+1),_R4M_SIZE))
            ch=True
        if _R4M_SIDE in ('both','ask') and pos>-200 and self._g(t,'ask'):
            ex,done=self._shift(ex,False,ask-1)
            if not done and not any(int(x.quantity)<0 for x in ex):ex.append(Order(_R4M_P,int(ask-1),-_R4M_SIZE))
            ch=True
        if ch:o[_R4M_P]=ex;return o
        return orders
    def run(self,state):
        self._ing(state)
        o,c,td=self.i.run(state)
        return self._ov(state,o),c,td
'''


def export() -> list[Path]:
    base = _rename_final_trader(BASE.read_text(), "_R4MBaseTrader")
    outputs: list[Path] = []
    for spec in specs():
        text = (
            base
            + APPENDIX.replace("__GATE__", spec.gate).replace("__SIDE__", spec.side)
        )
        spec.out.write_text(text)
        outputs.append(spec.out)
    return outputs


def main() -> None:
    for path in export():
        print(path)


if __name__ == "__main__":
    main()

"""Offline synthetic inference only; never writes financial facts."""
import json
import numpy as np
from services.forecaster import chronos_adapter
ok,reason=chronos_adapter.status()
if not ok:raise RuntimeError(reason)
model=chronos_adapter.load()
if model is None:raise RuntimeError('Chronos model did not load')
y=100+np.arange(48,dtype=float)*2+10*np.sin(np.arange(48)*2*np.pi/12)
median,lower,upper=model.predict(y,6,.8)
assert all(v.shape==(6,) and np.isfinite(v).all() for v in (median,lower,upper))
assert (lower<=median).all() and (median<=upper).all()
print(json.dumps({'model':model.name,'version':model.version,'horizon':6,'finite':True,'intervals_ordered':True}))

# Lane W2 on B2 b2e8e29c3: the server-side block after an unknown outcome (scenario PATH-01 stores orders). The unknown outcome = an OPEN order_attempts row, exactly what a crashed request leaves.
import httpx, subprocess, uuid, time, os
B = 'http://127.0.0.1:4178/api'
ENV = {**os.environ, 'PGPASSWORD': 'postgres_ci_dummy_pw', 'PGUSER': 'postgres', 'PGHOST': 'localhost'}
def sql(q): return subprocess.run(['psql', '-d', 'ofo_dev', '-Atc', q], capture_output=True, text=True, env=ENV).stdout.strip()
def orders(): return sql("select count(*) from paper_orders where strategy_id=1")
def post(sid, kind='exit', cid=65, side='SELL', qty=65, key=None, extra=None):
    body = {'orders': [{'contract_id': cid, 'side': side, 'quantity': qty, 'price': '0' if kind == 'exit' else '10.00', 'kind': kind}], 'client_request_id': key or str(uuid.uuid4())}
    if extra: body.update(extra)
    r = httpx.post(f'{B}/paper/strategies/{sid}/orders', json=body, timeout=30); return r
def brief(r):
    try: j = r.json(); return f"{r.status_code} {j.get('code')} {str(j.get('what_happened'))[:110]}" if 'code' in j else f'{r.status_code} (stored reply)'
    except Exception: return str(r.status_code)
print('orders before', orders(), '| open attempts', sql("select count(*) from order_attempts where state='open'"))
sql("insert into order_attempts (user_ref, strategy_id, door, state) values ('owner', 1, 'paper', 'open')")
print('simulated unknown outcome: open attempt for strategy 1;', sql("select id, state, started_at from order_attempts where state='open'"))
n0 = orders()
for tag, kw in [('exit, new key, new body', dict(kind='exit', cid=65, side='BUY', qty=65)), ('exit, other leg', dict(kind='exit', cid=57, side='BUY', qty=65)), ('open (add), new key', dict(kind='open', cid=36, side='BUY', qty=65)), ('add kind with prices_not_live_confirmed toggled', dict(kind='open', cid=36, side='BUY', qty=65, extra={'prices_not_live_confirmed': True}))]:
    print('(1)', tag, '->', brief(post(1, **kw)))
tr = httpx.post(f'{B}/paper/strategies/1/triggers', json={'kind': 'leg_stop', 'contract_id': 44, 'direction': 'above', 'level': '100.00'}); print('(1) stop change (POST triggers) ->', brief(tr), '| trigger rows', sql("select count(*) from paper_triggers where strategy_id=1"))
print('(1) orders stored while blocked:', int(orders()) - int(n0))
print('(2) other strategy 2 ->', brief(post(2, kind='exit', cid=1)))
print('(3) wait for the window (SETTLE 120 s) ...'); time.sleep(125)
r = post(1, kind='exit', cid=65, side='BUY'); print('(3) after the window (nothing stored -> not_stored):', brief(r), '| orders', orders(), '| attempts:', sql("select state, count(*) from order_attempts group by 1"))
# stored case: open attempt, then a stored order since it began
sql("insert into order_attempts (user_ref, strategy_id, door, state) values ('owner', 1, 'paper', 'open')")
r2 = post(1, kind='exit', cid=57, side='BUY'); print('(3b) open attempt then a request: ', brief(r2))

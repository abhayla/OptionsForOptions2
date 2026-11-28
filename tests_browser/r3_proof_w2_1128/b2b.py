import sys, time
sys.argv = ['x']
exec(open('/tmp/w2/c/b2.py').read().split("print('orders before'")[0])
print('open attempts now:', sql("select count(*) from order_attempts where state='open'"), '(the 3b one, <120 s old at start)'); time.sleep(122)
r = post(1, kind='exit', cid=57, side='BUY'); print('(3c) valid exit after the window ->', brief(r), '| orders', orders(), '| attempts', sql("select state, count(*) from order_attempts group by 1"))
r = post(1, kind='exit', cid=65, side='SELL'); print('(3d) immediately a second valid exit (first outcome known: stored) ->', brief(r), '| orders', orders(), '| attempts', sql("select state, count(*) from order_attempts group by 1"))

"""Lane W3 item 1 core, server half: the order request key on the build. Scenario PATH-10 API (8001), database ofo_dev. Reads the count of paper_orders before and after each call."""
import json, subprocess, sys, uuid, httpx
BASE = "http://127.0.0.1:8001"
def n():
    return int(subprocess.run(["psql", "-h127.0.0.1", "-Atc", "select count(*) from paper_orders"], capture_output=True, text=True, env={"PGUSER": "postgres", "PGPASSWORD": "postgres_ci_dummy_pw", "PGDATABASE": "ofo_dev", "PATH": "/usr/bin:/bin"}).stdout.strip())
def body(qty, cid=61):
    return {"orders": [{"contract_id": cid, "side": "SELL", "quantity": qty, "price": "0", "kind": "exit"}]}
def post(key, b):
    before = n(); r = httpx.post(f"{BASE}/paper/strategies/1/orders", json={**b, "client_request_id": key}, timeout=30)
    after = n(); print(f"  POST key={key[:8]} qty={b['orders'][0]['quantity']} -> {r.status_code} orders {before}->{after} :: {r.text[:420]}"); return r
k1, k2 = str(uuid.uuid4()), str(uuid.uuid4())
print("1 first order, key K1, exit 65 of contract 61"); post(k1, body(65))
print("2 SAME key K1, DIFFERENT body (exit 130): must be refused, nothing stored"); post(k1, body(130))
print("3 SAME key K1, SAME body (a repeat): must answer with the first result, nothing new stored"); post(k1, body(65))
print("4 NEW key K2, same exit 65 again (what a second Confirm with a new key would send)"); post(k2, body(65))

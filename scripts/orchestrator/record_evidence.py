"""Orchestrator records verifier output as evidence files: record_evidence.py <worktree> <W-id> <builder> <verifier> <json-file>"""
import json, os, sys, datetime


def _refuse_if_verifier_in_flight(target):
    """Shared check from the in-flight hook module (no copy of its logic); fails open when it cannot be loaded."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
        from verifier_inflight_gate import inflight_block_reason  # noqa: PLC0415 - path is set just above
        why = inflight_block_reason(target, "evidence write by " + os.path.basename(__file__))
    except Exception:  # noqa: BLE001 - a missing or broken hook module fails open
        return
    if why:
        sys.stderr.write(why + "\n")
        sys.exit(2)


wt, wid, builder, verifier, jf = sys.argv[1:6]
_refuse_if_verifier_in_flight(wt)
blocks = json.load(open(jf, encoding="utf-8"))
d = os.path.join(wt, "evidence", wid)
os.makedirs(d, exist_ok=True)
today = datetime.date.today().isoformat()
for b in blocks:
    def q(s):
        return json.dumps(str(s), ensure_ascii=False)
    text = (f"---\nwork_item: {wid}\nac: {b['ac']}\nresult: {b['result']}\nverified_by: {q(verifier)}\n"
            f"builder: {q(builder)}\ndate: '{today}'\ncommands: {q(b['commands'])}\n---\n\n"
            f"AC: {b['ac']}\nresult: {b['result']}\ncommands: {b['commands']}\nobserved: {b['observed']}\n"
            f"attack: {b['attack']}\n\nRecorded by the orchestrator from the verifier's returned block.\n")
    open(os.path.join(d, f"{b['ac']}.md"), "w", encoding="utf-8").write(text)
    print(wid, b["ac"], b["result"])

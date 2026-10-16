"""record_evidence_fp.py <agent-id | path> <W-id> <builder> <verifier> <json-file>

Like record_evidence.py, but writes the `requirement:` and quoted `ac_fp:` lines every NEW evidence file needs (deliver
skill step 5; trace_check fails new evidence without them). Each verifier block must carry "requirement" and "ac_fp";
check them first with `python tools/ac_fp.py <REQ> <AC>` - if it differs, re-verify instead of writing.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def main():
    target, wid, builder, verifier, jf = sys.argv[1:6]
    wt = target if os.path.isdir(target) else os.path.join(ROOT, "." + "claude", "worktrees", "agent-" + target)
    _refuse_if_verifier_in_flight(wt)
    blocks = json.load(open(jf, encoding="utf-8"))
    d = os.path.join(wt, "evidence", wid)
    os.makedirs(d, exist_ok=True)
    today = datetime.date.today().isoformat()

    def q(s):
        return json.dumps(str(s), ensure_ascii=False)

    for b in blocks:
        text = (f"---\nwork_item: {wid}\nac: {b['ac']}\nrequirement: {b['requirement']}\nac_fp: \"{b['ac_fp']}\"\n"
                f"result: {b['result']}\nverified_by: {q(verifier)}\nbuilder: {q(builder)}\ndate: '{today}'\n"
                f"commands: {q(b['commands'])}\n---\n\n"
                f"AC: {b['ac']}\nresult: {b['result']}\ncommands: {b['commands']}\nobserved: {b['observed']}\n"
                f"attack: {b['attack']}\n\nRecorded by the orchestrator from the verifier's returned block.\n")
        with open(os.path.join(d, f"{b['ac']}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(wid, b["ac"], b["requirement"], b["ac_fp"], b["result"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

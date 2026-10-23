"""kill_by_name_guard: a shell command that stops processes by NAME is refused before it runs.

Finding process-kill-by-name-hits-others (third occurrence, 2026-10-23 09:47): `taskkill //F //IM python.exe` run by a
process agent killed the owner's live API. The hook is an allow-list: only PID-based stop forms pass.
Answer states of the hook input: a Bash command, a PowerShell command, an empty command, another tool, a non-string
command, malformed JSON, empty stdin, a crash inside the decision -> each is covered below."""
import base64
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = REPO / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import kill_by_name_guard as kbn  # noqa: E402

REASON = "stop only the PIDs you started (kill by PID; finding process-kill-by-name-hits-others)"
ENCODED = base64.b64encode("Stop-Process -Name python".encode("utf-16-le")).decode()

REFUSED = [
    # attack 1: the exact command that killed the owner's API, and its siblings
    "taskkill //F //IM python.exe",
    "taskkill /IM node.exe /F",
    'taskkill /F /FI "IMAGENAME eq python.exe"',
    "taskkill /F /T /IM python.exe /PID 12",
    "taskkill",
    "taskkill /PID abc",
    "taskkill /PID",
    "taskkill /F",
    # attack 3: PowerShell and POSIX name-based forms
    "Stop-Process -Name python",
    "Stop-Process -Name python -Force",
    "Get-Process python | Stop-Process",
    "Get-Process python | Stop-Process -Force",
    "gps python | spps",
    "Stop-Process python",
    "Stop-Process -InputObject $p",
    "Stop-Process -Id 12 -Name python",
    "pkill -f uvicorn",
    "killall python",
    "kill %1",
    "kill",
    "kill -9",
    "kill -9 -1",
    "wmic process where name='python.exe' delete",
    'wmic process where "name=\'x\'" call terminate',
    "Get-Process python | ForEach-Object { $_.Kill() }",
    "Get-CimInstance Win32_Process | Invoke-CimMethod -MethodName Terminate",
    # attack 4: hidden after separators, inside substitutions, wrappers and nested shells
    "echo ok; taskkill /IM a.exe",
    "git status && pkill -f x",
    "false || killall x",
    "echo ok\ntaskkill /IM a.exe",
    "echo $(pkill -f x)",
    'echo "$(pkill -f x)"',
    "echo `killall x`",
    "bash -c 'pkill -f x'",
    'powershell -Command "Stop-Process -Name python"',
    "cmd /c taskkill /IM python.exe /F",
    "timeout 5 taskkill /IM a.exe",
    "sudo pkill x",
    "FOO=1 killall x",
    "ls | xargs kill",
    "find . -exec pkill x {} \\;",
    "Get-Process python | ForEach-Object { Stop-Process -Name $_.Name }",
    f"pwsh -EncodedCommand {ENCODED}",
    # fix round 1 (CRITICAL): a word after a shell keyword or a loop header starts a command
    "for p in $(pgrep python); do kill $p; done",
    'for p in $(pgrep python); do kill -9 "$p"; done',
    "for /f \"tokens=2\" %i in ('tasklist ^| findstr python') do taskkill /PID %i /F",
    "if true; then pkill python; fi",
    "while true; do pkill python; done",
    "! pkill python",
    "then taskkill /IM python.exe",
    "do Stop-Process -Name python",
    "if x; then echo a; else killall node; fi",
    "pgrep python | xargs kill -9",
    "$ids = (Get-Process python).Id; Stop-Process -Id $ids",
    "foreach ($p in Get-Process python) { Stop-Process -Id $p.Id }",
    # fix round 1 (MAJOR): a process-selecting pipeline may only flow into read-only sinks
    "Stop-Process -InputObject (Get-Process python)",
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Invoke-CimMethod -Name Terminate",
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Remove-CimInstance",
    "Get-WmiObject Win32_Process -Filter \"Name='python.exe'\" | Remove-WmiObject",
    "Get-Process python | ForEach-Object Kill",
    "Get-Process python | % Kill",
    "gps python | % { $_.Kill() }",
    "[System.Diagnostics.Process]::GetProcessesByName('python') | % { $_.Kill() }",
    "Get-Process python | Stop-Process -Id 1234",
    "Get-Process python | kill",
    "Get-Process python | Where-Object { $_.CPU -gt 1 } | Stop-Process",
    "Get-Process | Where-Object Name -eq python | Stop-Process",
    "ps aux | grep python | xargs kill",
    "$p = Get-Process python; $p.Kill()",
    "Stop-Process -Force",
    "Stop-Process -WhatIf",
    "$p = Get-CimInstance Win32_Process; Invoke-CimMethod -InputObject $p -MethodName Terminate",
    "Get-Process python | Where-Object Name -eq \"$(echo x)\" | Remove-CimInstance",
    # fix round 1 (MINOR): group kill, fuser -k, kill-port
    "kill 0",
    "kill -9 0",
    "kill -KILL 0 5",
    "fuser -k 8000/tcp",
    "fuser -km /tmp",
    "npx kill-port 8000",
    "kill-port 8000",
    # unterminated quotes fail closed (R09): the rest of the line is judged as command text
    "echo 'pkill python",
    'echo "pkill python',
    "echo ok; echo 'taskkill /IM python.exe /F",
]

ALLOWED = [
    # attack 2: PID-based stop forms
    "taskkill /PID 1234 /F",
    "taskkill //PID 1234 //F",
    "taskkill /F /T /PID 12 /PID 34",
    "Stop-Process -Id 4956 -Force",
    "Stop-Process -Id 12,34",
    "Stop-Process -Id:12 -Force",
    "Stop-Process -Id 12 -ErrorAction SilentlyContinue",
    "kill 1234",
    "kill -9 1234 5678",
    "kill -KILL 99",
    "echo ok; kill 77",
    # fix round 1: a variable holding a recorded PID is a PID form
    "Stop-Process -Id $p.Id",
    "Stop-Process -Id $pid -Force",
    "Stop-Process -Id $x",
    "kill $pid",
    "kill $!",
    'kill -9 "$pid"',
    "$p = Start-Process python -PassThru; Stop-Process -Id $p.Id",
    "server & pid=$!; sleep 1; kill $pid",
    "for p in 12 34; do kill $p; done",
    "ps -p $pid -o comm=; kill $pid",
    # read-only pipelines on process selections, and quoted text that only mentions a call
    "Get-Process python | Select-Object Id",
    "Get-Process python | Select Id; echo \".Kill()\"",
    "Get-Process | Where-Object { $_.CPU -gt 1 } | Sort-Object CPU | Format-Table Name, Id",
    "gps python | Measure-Object | Out-String",
    "Get-CimInstance Win32_Process | Select-Object ProcessId, Name | ConvertTo-Json",
    "tasklist | findstr python",
    "pgrep python | head -3",
    "echo \".Kill()\"",
    "$msg = @'\nit's done\nStop-Process -Name python\n'@\ngit commit -m $msg",
    "fuser 8000/tcp",
    "npm run kill-server",
    # everything that does not stop a process, including text that only mentions the verbs
    "git status",
    "python -m pytest -q",
    "grep -n taskkill scripts/orchestrator/mutation_gate.py",
    "echo pkill",
    "git commit -m 'document taskkill /IM and pkill'",
    'python -c "print(\'killall\')"',
    "cat <<EOF\ntaskkill /IM a.exe\nEOF",
    "echo $(date)",
    "Get-Process python",
    "Get-Process -Id 12",
    "ps aux | grep uvicorn",
    "",
]


def test_an_unterminated_quote_is_judged_as_command_text_not_skipped() -> None:
    for text in ("echo 'pkill python", 'echo "taskkill /IM a.exe'):
        reason = kbn.decide("Bash", {"command": text})
        assert reason is not None and REASON in reason
    assert kbn.decide("Bash", {"command": "echo 'it is fine"}) is None


def test_a_variable_pid_beside_a_name_selection_is_refused_but_alone_passes() -> None:
    assert kbn.decide("Bash", {"command": "kill $p"}) is None
    assert kbn.decide("Bash", {"command": "pgrep python; kill $p"}) is not None
    assert kbn.decide("PowerShell", {"command": "Stop-Process -Id $p.Id"}) is None
    assert kbn.decide("PowerShell", {"command": "Get-Process python | Out-Null; Stop-Process -Id $p.Id"}) is not None


def _encoded_layers(command: str, layers: int) -> str:
    for _ in range(layers):
        command = "pwsh -EncodedCommand " + base64.b64encode(command.encode("utf-16-le")).decode()
    return command


def test_a_stop_command_hidden_in_nested_encodings_is_refused_at_any_depth() -> None:
    for layers in (1, 3, 6):
        assert kbn.decide("PowerShell", {"command": _encoded_layers("Stop-Process -Name python", layers)}) is not None


def test_nesting_beyond_the_depth_limit_fails_closed_even_for_a_harmless_command() -> None:
    reason = kbn.decide("PowerShell", {"command": _encoded_layers("Get-Date", 6)})
    assert reason is not None and "too deeply" in reason
    assert kbn.decide("PowerShell", {"command": _encoded_layers("Get-Date", 2)}) is None


def hook(payload: dict | str) -> subprocess.CompletedProcess:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(HOOKS / "kill_by_name_guard.py")], input=text,  # noqa: S603
                          capture_output=True, text=True, cwd=REPO, timeout=60, check=False)


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
@pytest.mark.parametrize("command", REFUSED)
def test_name_based_stop_is_refused(command: str, tool: str) -> None:
    reason = kbn.decide(tool, {"command": command})
    assert reason is not None and REASON in reason


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
@pytest.mark.parametrize("command", ALLOWED)
def test_pid_based_and_unrelated_commands_pass(command: str, tool: str) -> None:
    assert kbn.decide(tool, {"command": command}) is None


def test_the_09_47_command_is_refused_as_a_real_hook_process() -> None:
    done = hook({"tool_name": "Bash", "tool_input": {"command": "taskkill //F //IM python.exe"}})
    assert done.returncode == 2 and REASON in done.stderr  # noqa: PLR2004 - the hook's refusal exit code


def test_a_pid_stop_passes_as_a_real_hook_process() -> None:
    done = hook({"tool_name": "PowerShell", "tool_input": {"command": "taskkill /PID 1234 /F"}})
    assert (done.returncode, done.stderr) == (0, "")


@pytest.mark.parametrize("payload", [
    {"tool_name": "Read", "tool_input": {"command": "pkill x"}},
    {"tool_name": "Bash", "tool_input": {"command": 123}},
    {"tool_name": "Bash", "tool_input": {"command": None}},
    {"tool_name": "Bash", "tool_input": {}},
    {"tool_name": "Bash"},
    {"tool_name": "Bash", "tool_input": {"command": "pkill x" * 40_000}},
    [],
    {},
])
def test_other_tools_and_odd_inputs_are_allowed(payload: object) -> None:
    assert hook(payload if isinstance(payload, dict) else json.dumps(payload)).returncode == 0


@pytest.mark.parametrize("text", ["", "{not json", "null", "[1, 2]", "\x00\xff"])
def test_malformed_input_fails_open(text: str) -> None:
    assert hook(text).returncode == 0


def test_a_crash_inside_the_decision_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object) -> None:
        raise RuntimeError("bug in the hook")

    monkeypatch.setattr(kbn, "decide", boom)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(
        json.dumps({"tool_name": "Bash", "tool_input": {"command": "pkill x"}})))
    assert kbn.main() == 0


def test_a_missing_helper_module_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "_route_common", None)  # an import of it now raises ImportError
    assert kbn.main() == 0


def test_the_hook_is_wired_for_bash_and_powershell_and_skips_a_missing_script() -> None:
    hooks = json.loads((REPO / ".claude" / "project" / "hooks.json").read_text(encoding="utf-8"))
    entries = [e for e in hooks["hooks"]["PreToolUse"]
               if any("kill_by_name_guard.py" in h["command"] for h in e["hooks"])]
    assert len(entries) == 1 and set(entries[0]["matcher"].split("|")) == {"Bash", "PowerShell"}
    command = next(h["command"] for h in entries[0]["hooks"] if "kill_by_name_guard.py" in h["command"])
    assert '[ -f "$f" ] || exit 0' in command


PORT_OWNER_KILLS = [
    "Get-NetTCPConnection -LocalPort 8000 | Select-Object -ExpandProperty OwningProcess"
    " | ForEach-Object { Stop-Process -Id $_ }",
    "$c = Get-NetTCPConnection -LocalPort 8000; Stop-Process -Id $c.OwningProcess -Force",
]


@pytest.mark.parametrize("command", PORT_OWNER_KILLS)
def test_killing_whatever_holds_a_port_is_refused(command):
    """Tier A round 2 (2026-10-23): killing a port's owner can kill the owner's live API (:8765) - refused like
    `fuser -k` and `lsof | xargs kill`."""
    assert kbn.decide("PowerShell", {"command": command}) is not None


def test_listing_port_owners_without_stopping_them_is_allowed():
    listing = "Get-NetTCPConnection -LocalPort 8765 | Select-Object OwningProcess"
    assert kbn.decide("PowerShell", {"command": listing}) is None

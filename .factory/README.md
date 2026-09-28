# .factory

This project's Factory config: authority.yaml (this project's authority
matrix, starting as a copy of the Core production block), routing.yaml
(optional overrides to Core routing), factory.lock (Factory + capability
versions this project depends on), authorizations/ (owner-only production
authorization records — never written by the agent directly), and
deploy-ledger.jsonl (append-only log of production deploy attempts).

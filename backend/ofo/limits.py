"""The one home of the database column limits that request models and stores both bound by.

A leaf module: it imports nothing, so a route that only needs the bound (a request ``seq``, a ``revision``) does not
pull the order path in through the store that happens to define the column.
"""

INTEGER_MAX = 2**31 - 1  # PostgreSQL INTEGER: plan_number, leg_index, quantity, strategy_history.seq, revision

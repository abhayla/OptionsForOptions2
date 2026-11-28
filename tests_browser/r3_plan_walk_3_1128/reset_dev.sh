#!/bin/bash
# Lane W3: stop the scenario API and worker, recreate ofo_dev from the migrated template ofo_tpl, reload the catalogue, seed the scenario ($1, default PATH-10), restart both.
cd /home/user/wt-build; W=/home/user/OptionsForOptions2/tests_browser/r3_plan_walk_3_1128; source $W/env.sh
for f in api-dev worker-dev; do [ -f /tmp/claude-0/$f.pid ] && kill $(cat /tmp/claude-0/$f.pid) 2>/dev/null; done; sleep 2
SC=${1:-PATH-10}
psql -q -d postgres -c "DROP DATABASE IF EXISTS ofo_dev WITH (FORCE)" -c "CREATE DATABASE ofo_dev TEMPLATE ofo_tpl" -c "GRANT CONNECT ON DATABASE ofo_dev TO ofo_app"
export APP_ENV=test TD_ADMIN_DB_URL=postgresql+asyncpg://postgres:$PGPASSWORD@127.0.0.1:5432/ofo_dev
python $W/load_cat.py PATH-01 PATH-10 2>&1 | tail -1
export DATABASE_URL=postgresql+asyncpg://ofo_app:$APP_ROLE_PW@127.0.0.1:5432/ofo_dev REDIS_URL=redis://127.0.0.1:6379/1
redis-cli -n 1 flushdb >/dev/null
python scripts/seed_scenario.py $SC 2>&1 | tail -1
export OFO_SCENARIO=$SC
bash $W/api_start.sh dev; bash $W/worker_start.sh dev; sleep 8; curl -s -m5 -o /dev/null -w "api %{http_code}\n" http://127.0.0.1:8001/paper/strategies/1

#!/bin/bash
# usage: api_start.sh tg|dev  -> API on 8000 (ofo_app role) ; logs in /tmp/claude-0/api-$1.log
source "$(dirname "$0")/env.sh"
DB=ofo_$([ "$1" = dev ] && echo dev || echo tg)
export DATABASE_URL=postgresql+asyncpg://ofo_app:$APP_ROLE_PW@127.0.0.1:5432/$DB
export APP_ENV=test TEST_CATALOGUE_DATE=2026-11-28 FEED_MODE=bus REDIS_URL=redis://127.0.0.1:6379/$([ "$1" = dev ] && echo 1 || echo 0)
if [ "$1" = dev ]; then export PORT=8001 OFO_SCENARIO=${OFO_SCENARIO:-PATH-01}; export TEST_CATALOGUE_DATE=2026-11-06; else export LIVE_MARKET=1 KITE_WS_URL=ws://127.0.0.1:9; fi
cd $BUILD
nohup python -m uvicorn --factory ofo_app.main:create_app --app-dir backend --loop ofo_app.event_loop:selector_loop --host 127.0.0.1 --port ${PORT:-8000} > /tmp/claude-0/api-$1.log 2>&1 &
echo $! > /tmp/claude-0/api-$1.pid

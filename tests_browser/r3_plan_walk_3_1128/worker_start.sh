#!/bin/bash
source "$(dirname "$0")/env.sh"
DB=ofo_$([ "$1" = dev ] && echo dev || echo tg)
export DATABASE_URL=postgresql+asyncpg://ofo_app:$APP_ROLE_PW@127.0.0.1:5432/$DB
export APP_ENV=test FEED_MODE=bus REDIS_URL=redis://127.0.0.1:6379/$([ "$1" = dev ] && echo 1 || echo 0)
if [ "$1" = dev ]; then export OFO_SCENARIO=${OFO_SCENARIO:-PATH-01}; else export TEST_CATALOGUE_DATE=2026-11-28; fi
cd $BUILD
nohup python -m ofo_app.background > /tmp/claude-0/worker-$1.log 2>&1 &
echo $! > /tmp/claude-0/worker-$1.pid

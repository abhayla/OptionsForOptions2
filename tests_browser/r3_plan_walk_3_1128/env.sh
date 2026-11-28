# Lane TG2 environment (throwaway local databases; placeholders only; nothing talks to Kite). source this file.
export PGUSER=postgres PGPASSWORD=postgres_ci_dummy_pw PGHOST=127.0.0.1
export APP_ROLE_PW=ofo_app_test_pw
export BUILD=/home/user/wt-build
export KITE_API_KEY=ci_placeholder_key KITE_API_SECRET=ci_placeholder_secret
export KITE_REDIRECT_URL=http://127.0.0.1:8000/kite/callback FRONTEND_ORIGIN=http://127.0.0.1:4173
export KITE_EXPECTED_USER_ID=ZZ0000
export BROKER_TOKEN_KEY=$(cat /tmp/claude-0/broker_key 2>/dev/null)
export PYTHONPATH=$BUILD/backend:$BUILD
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost

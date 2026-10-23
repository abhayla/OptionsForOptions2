"""Feature-code lines that may name the broker (REQ-117 AC-3 allow-list; see test_no_broker_name_in_feature_code.py).

Key: (file path, the line's stripped text). Value: the one-line reason. A line that is not here and names a broker is a
finding; an entry whose line no longer exists is a finding too. Reasons are per file: V1 is Zerodha only (ADR-002), so
the route modules that talk to the Zerodha adapter and the pages that say "Zerodha"/"Kite" to the user name it; what
must never appear is a BRANCH on the broker, and none of these lines is one.
"""
# ruff: noqa: E501 - a data file: each entry is a verbatim source line
from __future__ import annotations

UI = 'user-facing wording or a fixed broker URL: V1 is Zerodha only and its texts/links name Zerodha/Kite (ADR-002, REQ-073 wording); no branch on the broker'
REASONS: dict[str, str] = {
    'backend/ofo_app/routes/broker.py':
        'Zerodha login/callback route: it is the broker connection endpoint itself, with its own fix and refusal codes (REQ-015)',
    'backend/ofo_app/routes/broker_capabilities.py':
        'serves the flag file for the one V1 broker; the flag loader is named by its source, features read the flags',
    'backend/ofo_app/routes/broker_status.py':
        "fix code 'connect_zerodha' is a closed word the Settings page maps to its reviewed text (REQ-015 AC-4)",
    'backend/ofo_app/routes/execute.py':
        "V1 single-broker wiring: the Execute route builds Zerodha's basket and margin reads through the Kite adapter (ADR-002, REQ-054)",
    'backend/ofo_app/routes/execution_return.py':
        "V1 single-broker wiring: the return check reads Zerodha's orders and positions through the Kite adapter; 'zerodha_units' is the reply field the page shows",
    'backend/ofo_app/routes/positions.py':
        "V1 single-broker wiring: the positions read goes through the Kite adapter; 'zerodha_units' is the reply field the page shows",
    'backend/ofo_app/routes/strategies.py':
        'imports the Zerodha eligibility loader (data layer) by its module name; no broker comparison',
    'backend/ofo/strategy/modification.py':
        'type name of the eligibility table handed in (data layer class); no broker comparison',
    'backend/ofo/outcome/service.py':
        "looks up the catalogue's Zerodha symbol by the broker-ref key (data layer ref), no branch on the name",
}
LINES: dict[str, tuple[str, ...]] = {
    'backend/ofo_app/routes/broker.py': (
        'from ofo.broker.kite_auth import KiteAuthPort, login_url',
        'from ofo_app.kite_client import HttpKiteAuth, KiteExchangeError',
        'from ofo_app.kite_http import kite_async_client',
        'LOGIN_PATH = "/broker/zerodha/login"',
        'STATE_COOKIE = "ofo_kite_login"',
        '"kite_no_user_id", "kite_token_exception", "kite_input_exception", "kite_no_access_token", "kite_refused",',
        '"kite_unavailable", "kite_busy", "broker_store_failed",',
        '"kite_busy": Failure.UPSTREAM_BUSY,',
        '"kite_unavailable": Failure.UPSTREAM_BAD_GATEWAY,',
        'redirect: Literal["zerodha_login", "connected", "refused", "basket_returned"]',
        'return RedirectCookie(STATE_COOKIE, rt.config.callback_path, value=nonce,',
        'async def get_kite_auth(request: Request) -> AsyncIterator[KiteAuthPort]:',
        'async with kite_async_client() as client:',
        'yield HttpKiteAuth(rt.config.api_key, rt.config.api_secret.get_secret_value(), client)',
        '@router.get(LOGIN_PATH, response_model=BrokerRedirectOut, status_code=302)',
        'async def zerodha_login(request: Request, user_ref: str = Depends(current_user_ref)) -> object:  # noqa: FAST002',
        'return typed_redirect(BrokerRedirectOut(redirect="zerodha_login"), login_url(rt.config.api_key, state), cookie)',
        'async def kite_callback(  # noqa: PLR0911, PLR0913',
        'kite: KiteAuthPort = Depends(get_kite_auth),  # noqa: B008',
        'user_ref = rt.states.consume(state, request.cookies.get(STATE_COOKIE))',
        'session = await kite.exchange(request_token)',
        'except KiteExchangeError as exc:',
        'code = exc.code if exc.code in REFUSAL_CODES else "kite_refused"',
        'return _refused_redirect(request, rt, "kite_unavailable")',
        'app.add_api_route(config.callback_path, kite_callback, methods=["GET"], include_in_schema=True,',
    ),
    'backend/ofo_app/routes/broker_capabilities.py': (
        'from ofo.broker import kite_flags',
        'flags = flags_or_off(kite_flags.load_zerodha_flags)',
    ),
    'backend/ofo_app/routes/broker_status.py': (
        'Fix = Literal["connect_zerodha", "session_expired", "live_feed_off", "live_feed_not_running", "live_feed_session_ended",',
        'fix: Fix = "session_expired" if session is not None else "connect_zerodha"',
    ),
    'backend/ofo_app/routes/execute.py': (
        'from ofo.execution.basket import BasketRefused, KiteOrder, parse_tag, zerodha_exchange',
        'from ofo.instruments.models import ZERODHA, InstrumentId',
        'from ofo_app import eligibility_from_zerodha as elig',
        'from ofo_app.kite_margin import BasketOrder, KiteMargin',
        'from ofo_app.kite_reads import KiteReadError, KiteReads, unconfirmed_template',
        'from ofo_app.kite_replies import ContractIndex, KiteReplyError, PositionsRead, log_ignored, positions_from_reply',
        'BASKET_PRODUCT = Product(KiteOrder.__dataclass_fields__["product"].default)',
        'class KiteSession(Protocol):',
        'reads: KiteReads',
        'margin: KiteMargin',
        'async def get_kite_session() -> Optional[KiteSession]:  # noqa: UP045',
        'reads = await live_market.owner_kite_reads()',
        'session: KiteSession',
        'session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045',
        'except (KiteReadError, ValueError) as exc:',
        'names[want.instrument_id] = (f"{zerodha_exchange(entry.id.exchange_segment)}:"',
        'f"{entry.ref(ZERODHA).broker_symbol}")',
        'except KiteReadError:',
        'except (KiteReadError, KiteReplyError, ValueError):',
        '(entry,) = catalogue.entries_for_broker_symbol(ZERODHA, p.contract)',
        'out.append(BasketOrder(zerodha_exchange(entry.id.exchange_segment), p.contract, p.leg.action.value,',
        'async def _zerodha_margin(req: _Request, priced: ep.PricedPlan,',
        'available = await asyncio.to_thread(KiteMargin.fetch_available_funds, req.session.margin)',
        'basket = await asyncio.to_thread(KiteMargin.fetch_basket_margin, req.session.margin, orders)',
        'symbols[product_key(leg)] = entry.ref(ZERODHA).broker_symbol',
        'available, required = await _zerodha_margin(req, priced, catalogue)',
        '"get_execute_clock", "get_kite_session", "get_quote_reader", "held_products", "market_open",',
    ),
    'backend/ofo_app/routes/execution_return.py': (
        'from ofo.instruments.models import ZERODHA, InstrumentId',
        'from ofo_app import eligibility_from_zerodha as elig',
        'from ofo_app.kite_reads import KiteReadError, unconfirmed_template',
        'from ofo_app.kite_replies import ContractIndex, KiteReplyError, log_ignored, positions_from_reply',
        'from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session',
        'zerodha_units: int',
        'session: KiteSession',
        'async def return_from_kite(',
        'session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045',
        'def _read_zerodha(req: _Request, catalogue: Any) -> _Read:',
        'except (KiteReadError, KiteReplyError, ValueError) as exc:',
        'async def _others(req: _Request, catalogue: Any, zerodha: _Read) -> tuple[dict[tuple, int], frozenset]:',
        'book = rb.read_book(zerodha.orders, zerodha.trades, other, tags)',
        'zerodha: _Read',
        'symbol = _listed(world.catalogue, h.instrument_id).ref(ZERODHA).broker_symbol  # refused before any key read',
        'return er.reconcile(sorted(symbols, key=repr), held, world.others, world.zerodha.net, world.undecidable)',
        '"zerodha_units": c.zerodha_units, "other_strategies_units": c.other_units,',
        'zerodha = _read_zerodha(req, catalogue)',
        'book = rb.read_book(zerodha.orders, zerodha.trades, req.strategy_id, tags)',
        'world = _World(catalogue, underlying, zerodha, *await _others(req, catalogue, zerodha),',
        'await order_audit.record_broker_book(req.db, zerodha.orders, zerodha.trades, tags)  # W-103: our orders + trades',
        '__all__ = ["ReturnOut", "return_from_kite"]',
    ),
    'backend/ofo_app/routes/positions.py': (
        'from ofo_app.kite_reads import KiteReadError, unconfirmed_template',
        'from ofo_app.kite_replies import ContractIndex, KiteReplyError, log_ignored, orders_from_reply, positions_from_reply',
        'from ofo_app.routes.execute import KiteSession, get_execute_clock, get_kite_session',
        'zerodha_units: int  # Zerodha\'s net units on this contract, as read (a pending row marks them "not yet confirmed")',
        'class _Zerodha:',
        'def _read(session: KiteSession, catalogue: Any) -> _Zerodha:',
        'except (KiteReadError, KiteReplyError, ValueError) as exc:',
        'return _Zerodha(read.net, orders, index)',
        'async def _attribute(db: Any, user_ref: str, zerodha: _Zerodha, sources: ra.Sources,',
        'return await ra.attribute_and_compare(ra.Account(db, user_ref), {}, zerodha.net, zerodha.orders, sources, at=now)',
        'contracts = [{"tradingsymbol": _symbol(key, index), "zerodha_units": result.raw_net.get(key, 0),',
        'session: Annotated[Optional[KiteSession], Depends(get_kite_session)],  # noqa: UP045',
        'zerodha = _read(session, catalogue)',
        'result = await _attribute(db, user_ref, zerodha, ra.Sources(catalogue, clock), now)',
        'return _answer(result, zerodha.index, now)',
    ),
    'backend/ofo_app/routes/strategies.py': (
        'from ofo_app import eligibility_from_zerodha as elig',
    ),
    'backend/ofo/strategy/modification.py': (
        'from ofo.instruments import Catalogue, ZerodhaEligibility',
        'eligibility: ZerodhaEligibility,',
    ),
    'backend/ofo/outcome/service.py': (
        'from ofo.instruments.models import ZERODHA',
        'symbol = listed.ref(ZERODHA).broker_symbol if listed.broker_refs else None',
    ),
    'frontend/src/components/execution/BasketForm.vue': (
        'function placeOnKite() {',
        'data-testid="place-on-kite"',
        '@click="placeOnKite"',
        'Open Kite to place these orders',
        '<p v-if="sent" class="mt-2 text-sm" data-testid="basket-sent">Kite\'s order page opened in a new tab. Place or close the orders there, then check with Zerodha below.</p>',
        '<button v-if="fields && sent" type="button" data-testid="open-kite-again" class="mt-2 rounded border border-line px-3 py-1" @click="openAgain">',
        "Open Kite's page again",
    ),
    'frontend/src/components/execution/ExecuteCost.vue': (
        '<dt>Funds available (Zerodha)</dt><dd data-testid="cost-funds">{{ cost.funds_available ?? NOT_READ }}</dd>',
        '<dt>Margin required (Zerodha)</dt><dd data-testid="cost-margin">{{ cost.margin_required ?? NOT_READ }}</dd>',
    ),
    'frontend/src/components/execution/ReturnCheck.vue': (
        '<button type="button" data-testid="check-with-zerodha" class="rounded border border-line px-3 py-1" :disabled="busy" @click="check">',
        'Check with Zerodha',
        '<p>Read from Zerodha at <span data-testid="return-read-at">{{ istTime(result.read_at) }}</span>.</p>',
        "<thead><tr><th>Contract</th><th>Zerodha units</th><th>This platform's units</th><th>Mismatch</th></tr></thead>",
        "<td>{{ c.tradingsymbol }}</td><td>{{ c.zerodha_units }}</td><td>{{ c.platform_units }}</td><td>{{ c.mismatch ?? 'none' }}</td>",
    ),
    'frontend/src/components/states/ReturnStatus.vue': (
        "import { CHECK_WITH_ZERODHA, RETURN_CHECKING, RETURN_NO_CHANGE, RETRY_LABEL, RETURN_DONE_TEXT } from '@/lib/sharedStateText'",
        '<button v-if="status === \'idle\'" type="button" class="min-h-[44px] rounded border border-line px-3" data-testid="return-status-check" @click="$emit(\'check\')">{{ CHECK_WITH_ZERODHA }}</button>',
    ),
    'frontend/src/components/states/TwoBasketStepper.vue': (
        "import { KITE_ORDER_BOOK_URL } from '@/lib/execute'",
        '<a v-if="state === \'buy_failed\'" :href="KITE_ORDER_BOOK_URL" target="_blank" rel="noopener" data-testid="two-basket-kite-link" class="underline">{{ message }}</a>',
    ),
    'frontend/src/components/strategy/MarginLine.vue': (
        'Margin (Zerodha): Rs {{ margin.needed }} needed, Rs {{ margin.available }} available',
    ),
    'frontend/src/lib/chainUnavailable.js': (
        "export const UNAVAILABLE_LABEL = 'Currently unavailable on Zerodha'",
        'not_listed: "Not in Zerodha\'s list today.",',
        "restricted: 'Zerodha limits trading in this strike.',",
        'unknown: "We couldn\'t check with Zerodha. Refresh to try again.",',
    ),
    'frontend/src/lib/execute.js': (
        "export const NOT_READ = 'Not available from Zerodha'",
        "export const KITE_BASKET_URL = 'https://kite.zerodha.com/connect/basket'",
        "export const KITE_ORDER_BOOK_URL = 'https://kite.zerodha.com/orders'",
        "export const KITE_POSITIONS_URL = 'https://kite.zerodha.com/positions'",
        'if (b.url !== KITE_BASKET_URL) return null',
    ),
    'frontend/src/lib/landingText.js': (
        "{ title: 'Place it on your own Zerodha account', body: 'You review the orders and place them yourself on Kite.' },",
        "'Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693',",
        '{ q: \'Do you ask for my Zerodha password?\', a: "No. You log in on Zerodha\'s own page; we never see or store your password." },',
        "{ q: 'Does the app place orders for me?', a: 'No. You review the orders and place them yourself on Kite.' },",
    ),
    'frontend/src/lib/learnContent.js': (
        "'The platform reads the lot size from Zerodha data. It is not typed in here.']),",
        "lesson('orders-to-zerodha', 'How orders reach Zerodha', 'You place the orders on Kite yourself.', [",
        "'It prepares the legs, and you place them on Kite yourself.',",
        "'Zerodha is the record of what was placed and what was executed.',",
        "'An order sent is not an order executed. Only Zerodha can say which.']),",
        "lesson('check-with-zerodha', 'What Check with Zerodha does', 'It asks Zerodha what happened and changes nothing.', [",
        "'Check with Zerodha reads your orders and positions from Zerodha.',",
        '\'"Not sent to Zerodha" means no order carrying the tag of this strategy has reached Zerodha.\',',
        '\'"Order placed" means Zerodha has the order. It may not have executed.\',',
        '\'"Not executed - see Kite" means it did not execute. Kite shows the reason.\']),',
    ),
    'frontend/src/lib/sharedStateText.js': (
        "export const SESSION_ENDED_TEXT = 'Zerodha session ended. Reconnect to continue'",
        "export const STEP_SELLS = 'Step 2 of 2 Sells (locked until Zerodha confirms the fills)'",
        "export const BUY_FAILED_TEXT = 'Buy not executed - see Kite'",
        "export const CHECK_WITH_ZERODHA = 'Check with Zerodha' // wording fixed by REQ-073, F-41",
        "export const RETURN_CHECKING = 'Checking with Zerodha…'",
        "export const RETURN_DONE_TEXT = 'Zerodha confirmed your orders.' // ADR-129",
    ),
    'frontend/src/pages/BrokerConnectedPage.vue': (
        '<h1 class="text-xl font-semibold" data-testid="page-title">Zerodha is connected</h1>',
        '<p class="mt-2" data-testid="connected-what">Your Zerodha account is now linked to this platform for today.</p>',
    ),
    'frontend/src/pages/BrokerRefusedPage.vue': (
        "const NEUTRAL = { ...NEUTRAL_PARTS, what_happened: 'The Zerodha login was not completed.' }",
        '<h1 class="text-xl font-semibold" data-testid="page-title">Zerodha login not completed</h1>',
        '<router-link to="/settings/zerodha-connection" class="mt-4 inline-block rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="to-connection">Back to the Zerodha connection page</router-link>',
    ),
    'frontend/src/pages/BrokerSettingsPage.vue': (
        "['account_connection', 'Zerodha account connection'],",
        "connect_zerodha: 'Zerodha is not connected. Use Connect Zerodha below, log in on Zerodha\\'s own page, and come back here.',",
        "session_expired: 'Your Zerodha login for today has expired. Use Reconnect and log in again on Zerodha\\'s own page.',",
        "live_feed_waiting: 'Connected to Zerodha, but no prices have arrived yet. Wait a few seconds; if this stays, use Reconnect.',",
        "live_feed_market_closed: 'The market is closed, so no new prices are arriving. Live prices resume at the next market open (9:15 am IST on a trading day).',",
        "live_feed_reconnecting: 'The live price feed dropped and is reconnecting. It resumes by itself while your Zerodha login is valid.',",
        "live_feed_session_ended: 'Zerodha ended the live feed. Use Reconnect and log in again.',",
        "live_feed_capped: 'Live prices are not available: Zerodha\\'s connection limit for this app is reached.',",
        "no_read_yet: 'No position read from Zerodha has succeeded since you connected. Open Execute for a strategy to read your positions.',",
        "positions_not_synced: 'Orders are not ready until your positions have been read from Zerodha. Fix the position sync row first.',",
        '<p class="mt-1 text-sm text-ink-muted">Zerodha is the only broker. Your strategies, history and account stay here whether or not Zerodha is connected.</p>',
        '<p v-if="state === \'loading\'" class="mt-4 text-sm text-ink-muted" data-testid="broker-loading">Checking the Zerodha connection.</p>',
        '<p class="mb-2 font-medium">The Zerodha connection could not be checked, so nothing below is shown as connected.</p>',
        '<span v-else data-testid="last-sync-none">no successful read from Zerodha is recorded yet</span>',
        '<a href="/api/broker/zerodha/login" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-reconnect">{{ anyConnected ? \'Reconnect Zerodha\' : \'Connect Zerodha\' }}</a>',
        '<button v-if="anyConnected && !confirming" type="button" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-disconnect" @click="confirming = true">Disconnect Zerodha</button>',
    ),
    'frontend/src/pages/ExecuteStrategyPage.vue': (
        '<h2 class="mt-4 font-medium">Plan {{ reply.plan_number }}: orders for Kite\'s page</h2>',
    ),
    'frontend/src/pages/ExecutionReturnedPage.vue': (
        '<h1 class="text-xl font-semibold" data-testid="page-title">Back from Kite</h1>',
        '<p class="mt-2">Your orders were handled on Kite\'s page.</p>',
    ),
    'frontend/src/pages/HomeOverviewPage.vue': (
        '<p v-if="state !== \'loading\'" class="mt-8 text-xs text-ink-muted" data-testid="zerodha-line">Already trade with Zerodha? Connect when ready</p>',
    ),
    'frontend/src/pages/OptionChainPage.vue': (
        'Some contracts are currently unavailable on Zerodha and cannot be added.',
    ),
    'frontend/src/pages/PositionsPage.vue': (
        "import { KITE_POSITIONS_URL } from '@/lib/execute'",
        "const WAITING = 'Order placed - waiting for Check with Zerodha'",
        "const BLOCKED = 'blocked until its position matches Zerodha'",
        "const VIEW_ON_KITE = 'view on Kite'",
        '<p v-if="loading" class="mt-2" data-testid="positions-loading">Reading your positions from Zerodha.</p>',
        '<p>Read from Zerodha at <span data-testid="positions-read-at">{{ istTime(result.read_at) }}</span>.</p>',
        'Zerodha shows no open positions, and none of your strategies holds any.',
        'Zerodha: <span data-testid="position-zerodha">{{ c.zerodha_units }}</span> units,',
        '(Zerodha shows <span data-testid="position-zerodha">{{ c.zerodha_units }}</span> on this contract)',
        '<a :href="KITE_POSITIONS_URL" target="_blank" rel="noopener noreferrer" class="underline" data-testid="positions-outside-kite">{{ VIEW_ON_KITE }}</a>',
    ),
    'frontend/src/router/nav.js': (
        "['zerodha-connection', 'Zerodha connection'],",
    ),
    'frontend/src/router/routes.js': (
        "{ path: '/execution/returned', name: 'execution-returned', beforeEnter: requireOrderPath, component: () => import('../pages/ExecutionReturnedPage.vue'), meta: { title: 'Back from Kite', section: 'strategies' } },",
        "{ path: '/broker/connected', name: 'broker-connected', component: () => import('../pages/BrokerConnectedPage.vue'), meta: { title: 'Zerodha connected', section: 'settings' } },",
        "{ path: '/broker/refused', name: 'broker-refused', component: () => import('../pages/BrokerRefusedPage.vue'), meta: { title: 'Zerodha login not completed', section: 'settings' } },",
    ),
    'frontend/src/lib/brokerConnected.js': (
        "export const TRADE_NEEDS_BROKER_REASON = 'Log in with Zerodha to trade. Use Connect Zerodha in Settings, then come back.'",
    ),
    'frontend/src/lib/connectHelp.js': (
        "'This app uses the connection to read your positions, orders and margin from Zerodha and to prepare orders that you confirm on Zerodha\\'s own page. It never sees your Zerodha password, PIN or OTP: you log in on Zerodha\\'s own page.'",
        "export const NO_EXTRA_CHARGES = 'Connecting your Zerodha account adds no charge from this app. Your normal Zerodha brokerage and charges apply to orders you place.'",
        "export const OPEN_ACCOUNT_LABEL = 'Don\\'t have a Zerodha account? Open one'",
        'export function openAccountUrl(raw = import.meta.env.VITE_ZERODHA_OPEN_ACCOUNT_URL) {',
    ),
    'frontend/src/lib/dataHealthText.js': (
        "not_sent: 'Zerodha did not send this figure for this contract.',",
    ),
}
ALLOW: dict[tuple[str, str], str] = {
    (path, line): REASONS.get(path, UI)
    for path, lines in LINES.items() for line in lines}

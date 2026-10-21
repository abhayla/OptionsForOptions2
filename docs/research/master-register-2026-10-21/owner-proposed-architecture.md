# Owner's proposed high-level architecture (input, 2026-10-21)

Pasted by the owner on 2026-10-21 as the target level of architecture compliance ("mostly taken from Sensibull, but
applicable to all commercial finance apps"). Kept verbatim as an input to the master register; it is not a decision.
Each line is triaged in `register.md`.

---

Design my commercial, Zerodha-only options-trading SaaS using Sensibull (https://web.sensibull.com/home) as a product
reference. This is a proposed architecture, not a claim about Sensibull's actual internal implementation.

The market-data engine should provide a consistent instrument and pricing model to every screen.
The broker integration translates your application's order requests into the broker's supported API operations.
Trading controls make sure that a valid strategy in theory doesn't become an unsafe or incomplete live trade.
The database and infrastructure preserve user strategies, preferences, orders, execution history and entitlement
information. This separation is especially important for a commercial app: a change to the strategy builder shouldn't
require you to rebuild the broker integration.

## 1. Customer Web Application
Provides the user interface for:
- Dashboard and market overview
- Option Chain
- Strategy Builder
- Payoff graphs and P&L analysis
- Greeks and risk analysis
- Scenario analysis
- Saved strategies and draft portfolios
- Live positions and orders
- Strategy adjustment suggestions
- Broker connection and account information
- User settings, subscriptions and account management

## 2. Backend API and Authentication Layer
- User authentication and profiles
- Permissions and multi-user data isolation
- Subscription and Pro-feature entitlements
- Strategy management
- Server-side validation and API security
- Audit logging

## 3. Market-Data Engine
- Receiving data from a licensed market-data provider
- Normalizing live market prices
- Maintaining instrument, strike and expiry information
- Providing option-chain data
- Tracking data timestamps and freshness
- Distributing updates to connected users through WebSockets
- Handling feed interruptions and stale data

## 4. Options and Strategy Calculation Engine
- Multi-leg options strategies
- Call and put buying and selling
- Futures buying and selling
- Expiry payoff calculations
- Current mark-to-market P&L
- Scenario P&L
- Greeks: Delta, Gamma, Theta and Vega
- Breakeven calculations
- Margin estimates
- Strategy validation and adjustment-rule evaluation

This engine must be reusable across the Strategy Builder, saved strategies, positions and scenario analysis. Keep
expiry payoff, live P&L and model-based scenario calculations distinct.

## 5. Broker Integration and Execution Engine
Integrates with Zerodha Kite Connect for:
- Customer broker authentication
- Funds and margin information
- Order placement and updates
- Positions and holdings where applicable
- Execution tracking and reconciliation

It must validate approved strategies, sequence orders, track partial fills, handle failures and reconcile actual broker
state. Never assume a timeout means an order failed, and never blindly retry an uncertain order.

## 6. Trading Risk and Safety Controls
- Validating permitted contracts and quantities
- Checking market-data freshness
- Validating available funds and applicable margin requirements
- Enforcing strategy and execution permissions
- Handling incomplete or partially executed strategies
- Supporting controlled recovery and manual review
- Maintaining execution audit trails

Initially, require explicit user approval before executing a strategy or applying an adjustment.

## 7. Positions and Adjustment Engine
- Monitoring live positions
- Calculating strategy-level P&L
- Evaluating configurable user-specific adjustment rules
- Suggesting adjustments with explanations
- Tracking whether suggestions are accepted, rejected or completed

Support configurable rules rather than assuming one adjustment method suits every customer.

## 8. Data and Infrastructure Layer
- PostgreSQL for users, strategies, subscriptions, rules, execution records and audit history
- Redis for caching and temporary coordination
- Background workers for market-data processing, execution and reconciliation
- WebSockets for live customer updates
- Secure credential storage for broker tokens and secrets

PostgreSQL should remain the durable source of truth for important application and trading records.

## Architecture flow
Customer Web Application -> Backend API and Authentication -> Market-Data Engine | Strategy Calculation Engine |
Broker Execution Engine | Risk Controls | SaaS Services -> PostgreSQL | Redis | Background Workers.
External: licensed market-data provider -> Market-Data Engine; each customer's authorized Zerodha account -> Broker
Integration and Execution Engine.

## Core architectural principles
- Start with a modular monolith instead of many microservices.
- Keep logical modules separate, even if they initially share one backend deployment.
- Separate shared market data from customer-specific broker data.
- Use one reusable calculation engine across all screens.
- Preserve immutable strategy versions for approved executions.
- Enforce customer isolation and authorization on the backend.
- Make execution state durable, auditable and recoverable.
- Design for commercial multi-user use and future scaling.
- Treat live trading and commercial licensing requirements as explicit launch dependencies.

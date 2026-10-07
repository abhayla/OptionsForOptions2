# Owner actions after the Stage 1 research (2026-10-07)

These are the only things on the critical path that need you; everything else the orchestrator decides and records
(owner delegation, 2026-10-07). Each answer, when it arrives, goes into the spec the same day.

## 1. Kite Connect app for the core data test (needed at Stage 4a; ADR-051)
- Create a Kite Connect app on your own Zerodha account (Connect plan, Rs 500 for one month).
- Redirect URL: given to you when Stage 4a starts (a local address for the test).
- Put the API key and API secret in the project's `.env` file yourself (variable names given at Stage 4a). Never paste
  them into a chat, an email or the repository.

## 2. Email to Zerodha (one email; reply to the existing ADR-034 thread with talk@rainmatter.com)

Draft, ready to send:

> Subject: Kite Connect for a multi-user options strategy platform - four questions
>
> Hello Kite Connect team,
>
> I am a Zerodha Authorised Person building a web platform where Zerodha clients plan NIFTY/SENSEX options
> strategies and see the payoff. Each user connects their own Kite account. We would like your written guidance on:
>
> 1. **Order placement.** We plan to send each strategy's orders as a read-only Kite basket (offsite order execution,
>    kite.zerodha.com/connect/basket) that the user places on Kite's own order page; our server would never place
>    orders through the API. Under NSE/INVG/69255 (para 2.8: "all orders received via API ... shall be considered as
>    Algo"), are orders placed this way algo orders? Is there a limit on orders per basket, and how is a rejected leg
>    reported back?
> 2. **Market data.** May our platform show a connected user their own Kite Connect market data (quotes for the
>    contracts in their strategy) inside our website, given the terms' clause allowing platforms "offer[ed] to other
>    Clients of Zerodha (after obtaining the required exchange approvals)"? Which exchange approvals apply?
> 3. **Startup programme.** Does the free mass-retail access (kite.trade/startups) include live data, and per user or
>    per platform?
> 4. **Authorised Person.** May an AP (or a separate company the AP owns) sell a paid subscription for such a platform
>    to clients, and give clients free access? We are reading the AP rule "shall not charge any amount from the
>    clients" and NSE/COMP/55482 §5.5.
>
> Thank you.

Why: Q259 (order path, ADR-054), Q210 (data display), Q260 (AP rules, ADR-055).

## 3. Legal review (Q211, already decided as "before production")
Ask the reviewer one added question: do suggested option setups, strike suggestions or adjustment suggestions on a
paid plan count as "research services" under the SEBI (Research Analysts) Regulations as amended in Dec 2024, and
what wording or registration would keep them outside (Q261, F-24)? Until then the product follows ADR-055.

## 4. Outside this repo (from the 2026-10-02 build plan, still not evidenced)
Rotate the secrets that were committed in the public algochanakya repository.

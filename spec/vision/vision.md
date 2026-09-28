# Vision

Decisions: ADR-001, ADR-002, ADR-003, ADR-004. Sources: the owner's first message (T1 #1) and the full chats in
`docs/reference/chatgpt/`.

**Core promise:** *Plan the trade. Follow the strategy. Then execute.*
**Principle:** *You can change your strategy, but you cannot bypass the strategy.*
**Positioning:** *Your Zerodha account. Your strategy. Your decision. Our technology.*

## What it is
A public SaaS web platform for Indian index options and futures (V1: NIFTY on NSE, SENSEX on BSE; Zerodha only).
It makes strategy-based trading, especially **option selling**, easy for anyone with basic option-selling knowledge
("without any hand-holding", T1 #1) and useful for intermediate and advanced traders. Users build a strategy, see what can happen to their money at every market level before they
trade, execute it through their own Zerodha account, and have it monitored against their own rules.

## Why
Impulsive, unplanned trades are the problem it addresses. The owner sees "no unrestricted orders" as the headline
feature that builds user confidence (T1 #73). The product enforces strategy context, risk visibility,
predefined conditions and controlled execution. It does not promise returns or that losses will be smaller.

## Who
Primary: beginners and intermediate options traders. Advanced users are supported. *Simple on the surface,
sophisticated underneath* — three UX levels (Guided, Standard, Advanced).

## What it is not
A Kite clone · an unrestricted trading terminal or order form · an AI investment-advice chatbot · an autonomous
trading bot **in V1** (the owner's brief asked for auto-triggered orders from predefined conditions, T1 #1; Q1 = A
keeps automation as a later stage, not dropped) · copy trading, pooled money or managing anyone else's account.

## How it makes money
7-day full Pro trial → ₹600/month Pro (Razorpay), or free Pro for qualifying Zerodha customers and for successful
Zerodha referrals; everyone else becomes Limited/Read-Only (ADR-023–ADR-026).

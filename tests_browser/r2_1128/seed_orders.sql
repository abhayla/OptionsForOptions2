-- Lane TC: paper fills inserted as the store would (insert-only table), 27 Nov 2026 10:15 IST (an exit 10:45: an exit with the same time as its open is replayed first by the book), throwaway database only.
-- The routes refuse paper entries while the market is closed (MARKET_DATA_102), so the fills go in by SQL.
INSERT INTO public.paper_orders (strategy_id, contract_id, side, quantity, price, kind, placed_at)
SELECT s, c.id, side, 65, price::numeric, kind,
       CASE WHEN kind = 'exit' THEN '2026-11-27 10:45:00+05:30'::timestamptz ELSE '2026-11-27 10:15:00+05:30'::timestamptz END
FROM (VALUES
 (1,44732,'SELL','88.00','open'),(1,44746,'BUY','45.00','open'),(1,44721,'SELL','70.00','open'),(1,44715,'BUY','38.00','open'),
 (2,44730,'SELL','64.00','open'),(2,44727,'SELL','66.00','open'),
 (3,44740,'SELL','55.00','open'),(3,44745,'SELL','57.00','open'),
 (4,44728,'SELL','98.00','open'),(4,44728,'BUY','90.00','exit'),
 (5,44720,'SELL','150.00','open'),(5,44739,'SELL','30.00','open')
) AS v(s,tok,side,price,kind)
JOIN public.catalogue_contracts c ON c.exchange_token = v.tok AND c.exchange_segment = 'NSE_FO';
UPDATE public.strategies SET status = 'closed' WHERE id = 4;

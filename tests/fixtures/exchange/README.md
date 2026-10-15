# Exchange file fixtures

`NSE_FO_contract_15102026_sample.csv` - 88 rows cut, unmodified, from NSE's daily F&O contract file
`https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_15102026.csv.gz` (downloaded 2026-10-16 00:36 IST,
sha256 `9b4e035d2e37e9ab00fa6aa69723df983c4d13237089fbb6c3461f32bdad4140`; full file kept outside the repo at
`D:\Abhay\Ventures\ofo-exchange-files\2026-10-15\`). Header row kept as is. Rows: NIFTY options expiring 2026-10-19
with strikes 22,000-24,000, every NIFTY future, and the first 3 BANKNIFTY option rows of the file.

Column meanings measured in `spec/findings.md` F-36: `FinInstrmId` = exchange token, `MaxTradQty` = freeze limit (the
largest allowed order is one less), `XpryDt` = seconds from 1980-01-01, `StrkPric` in paise, `MinLot` = lot size.

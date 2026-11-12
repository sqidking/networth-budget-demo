"""Invented statements and exports for the demo and the tests. Every name, place, number and amount is made up.

The text is shaped like pdfplumber's output of real statement layouts, including its quirks: bold headings
with doubled letters, a page footer in the middle of the activity, a summary line that runs into marketing
text beside it, and amounts printed without a leading zero (".99").
"""

CARD = """AACCCCOOUUNNTT SSUUMMMMAARRYY
Account Number: XXXX XXXX XXXX 1234
Previous Balance $850.00 Cardmembers earn rewards at
Payment, Credits -$863.85 Example Store.
Purchases +$162.37
Cash Advances $0.00
Balance Transfers $0.00
Fees Charged +$39.00
Interest Charged $0.00
New Balance $187.52
Opening/Closing Date 12/05/25 - 01/04/26
AACCCCOOUUNNTT AACCTTIIVVIITTYY
Date of
Transaction Merchant Name or Transaction Description $ Amount
PAYMENTS AND OTHER CREDITS
12/08 & Payment Thank You-Mobile -850.00
12/20 BOOKSHOP ONLINE*ZY98XW76 example.com WA -13.85
PURCHASE
12/04 BOOKSHOP ONLINE*AB12CD34 example.com WA 27.18
Order Number 000-0000000-0000001
12/31 GROCERY MART #0001 ANYTOWN ST 121.20
JANE DOE Page2 of 3 Statement Date: 01/04/26
01/02 COFFEE HOUSE 00001 ANYTOWN ST 6.50
01/03 COFFEE HOUSE 00001 ANYTOWN ST 6.50
01/03 CLOUD STORAGE *Example example.com CA .99
FEES CHARGED
01/01 ANNUAL MEMBERSHIP FEE 39.00
TOTAL FEES FOR THIS PERIOD $39.00
2026 Totals Year-to-Date
Total fees charged in 2026 $39.00
IINNTTEERREESSTT CCHHAARRGGEESS
PURCHASES
Purchases 21.49%(v)(d) - 0 - - 0 -
SSHHOOPP WWIITTHH PPOOIINNTTSS AACCTTIIVVIITTYY
PURCHASES AND REDEMPTIONS
12/13 BOOKSHOP ONLINE EXAMPLE.COM WA 16.00 1,600
"""

CHECKING = """CUSTOMER SERVICE INFORMATION
December 16, 2025throughJanuary 16, 2026
CHECKING SUMMARY
AMOUNT
Beginning Balance $4,000.00
Deposits and Additions 2,500.00
Checks Paid -75.00
ATM & Debit Card Withdrawals -6.50
Electronic Withdrawals -1,460.00
Fees -2.95
Ending Balance $4,955.55
DEPOSITS AND ADDITIONS
DATE DESCRIPTION AMOUNT
12/19 EXAMPLE EMPLOYER Payroll PPD ID: 0000000002 $2,500.00
Total Deposits and Additions $2,500.00
CHECKS PAID
DATE
CHECK NO. DESCRIPTION PAID AMOUNT
3001 ^ 01/09 $75.00
Total Checks Paid $75.00
ATM & DEBIT CARD WITHDRAWALS
DATE DESCRIPTION AMOUNT
01/06 Card Purchase 01/05 Coffee House 00002 Anytown ST Card 0000 $6.50
TotalATM & Debit Card Withdrawals $6.50
ELECTRONIC WITHDRAWALS
DATE DESCRIPTION AMOUNT
12/22 12/22 Payment To Example Bank Card Ending IN 1234 850.00
Page of
1 4
December 16, 2025throughJanuary 16, 2026
(continued)
ELECTRONIC WITHDRAWALS
DATE DESCRIPTION AMOUNT
01/02 EXAMPLE LOAN SVC PPD ID: 0000000001 410.00
01/05 Online Transfer To Sav ...0000 Transaction#: 000000001 200.00
Total Electronic Withdrawals $1,460.00
FEES
DATE DESCRIPTION AMOUNT
01/06 Out-of-Network ATM Fee-With $2.95
Total Fees $2.95
"""

# Some of the same card purchases as the bank's CSV export words them, plus one after the statement closed.
CARD_STATEMENT_CSV = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
12/31/2025,01/02/2026,GROCERY MART #0001,Groceries,Sale,-121.20,
01/02/2026,01/03/2026,COFFEE HOUSE 00001,Food & Drink,Sale,-6.50,
01/03/2026,01/04/2026,COFFEE HOUSE 00001,Food & Drink,Sale,-6.50,
01/04/2026,01/05/2026,FUEL STOP 0001,Gas,Sale,-44.05,
"""

CARD_CSV = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
02/02/2026,02/03/2026,GROCERY MART #0001,Groceries,Sale,-98.40,
02/02/2026,02/03/2026,COFFEE HOUSE 00001,Food & Drink,Sale,-6.50,
02/02/2026,02/03/2026,COFFEE HOUSE 00001,Food & Drink,Sale,-6.50,
02/05/2026,02/06/2026,BOOKSHOP ONLINE*AB12CD34,Shopping,Return,13.85,
02/20/2026,02/20/2026,Payment Thank You-Mobile,,Payment,500.00,
"""

CHECKING_CSV = """﻿Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
DEBIT,02/21/2026,"Payment to Example Bank card ending in 1234 02/21",-500.00,LOAN_PMT,3590.00,,
DEBIT,02/15/2026,"EXAMPLE LOAN SVC PPD ID: 0000000001",-410.00,ACH_DEBIT,4090.00,,
CREDIT,02/15/2026,"EXAMPLE EMPLOYER PAYROLL PPD ID: 0000000002",2500.00,ACH_CREDIT,4500.00,,
CHECK,02/09/2026,"CHECK 3002",-75.00,CHECK_PAID,2000.00,3002,
"""

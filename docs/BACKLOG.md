# Backlog File

## Backlog-0010: Improve Monitoring of API Calls
**Status**: Closed — addressed by [Story-0170](stories/Story-0170.md)

Regarding your verbose flag question: yes, absolutely add it to the backlog. It would print something like [BULL] 12/87 — enriching AAPL... per ticker so you can see exactly where it is and monitor API traffic. The current silence makes it impossible to know if it's stuck or just slow.

## Backlog-0020: Monitor API throughput
**Status**: Closed — addressed by [Story-0170](stories/Story-0170.md)

The documentation for the 'Tradier' API describes some feedback that they provide regarding current usage and it relates to the rate limits. We need to see if we can utilize this data, and also be able to measure our API run rate so that we can possibly run at ~89% of capacity. This would also help us confirm that we are not being too conservative on our throttling.





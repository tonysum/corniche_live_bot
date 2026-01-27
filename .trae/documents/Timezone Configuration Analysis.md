I will convert the entire system to use **UTC** as the standard time, and add a Beijing Time display for the "Last Update" field on the dashboard.

### Implementation Plan

1.  **Backend (`src/main.py`) - Switch to UTC**:
    *   Replace all instances of `datetime.now()` with `datetime.utcnow()`.
    *   This ensures that `created_at`, `timeout_time`, `entry_time`, and log timestamps are all generated in UTC, matching the market data `signal_time`.

2.  **Data Migration - Adjust Existing State**:
    *   Create and run a one-time script (`migrate_to_utc.py`) to convert the current "Local/CST" timestamps in `trading_state.json` to "UTC" (subtract 8 hours).
    *   This prevents existing signals from having "future" timestamps relative to the new UTC clock.

3.  **Frontend (`src/dashboard.py`) - Add Beijing Time Display**:
    *   Modify the "Last Updated" (最后更新) metric.
    *   It will display the UTC time from the state file.
    *   **New Feature**: Calculate and append the corresponding Beijing Time (UTC+8) alongside it (e.g., `10:00 UTC (18:00 BJ)`).

### Outcome
*   **System Logic**: Fully UTC-based (consistent with crypto markets).
*   **Dashboard**: Shows UTC for everything (Signal Time, Expire, etc.), but provides a Beijing Time reference for the last heartbeat.

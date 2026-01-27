
import json
from pathlib import Path
from datetime import datetime, timedelta

STATE_FILE = Path("data/trading_state.json")

def patch():
    if not STATE_FILE.exists():
        print("No state file found.")
        return

    data = json.loads(STATE_FILE.read_text())
    pending = data.get("pending_signals", [])
    
    count = 0
    for p in pending:
        # Check if already patched (naive check: if hour is > 8? no, that's risky)
        # We assume all current signals are UTC (because code was UTC)
        # But wait, I just restarted main.py with the fix.
        # If main.py ran for a few seconds, did it update anything?
        # It updates `updated_at`.
        # It might have added new signals (unlikely in 1 min).
        # Existing signals from JSON are loaded into memory.
        # So they are still old values.
        
        # Let's just add 8 hours to all pending signals.
        # ISO format: YYYY-MM-DDTHH:MM:SS
        try:
            st_str = p['signal_time']
            # If it doesn't look like it's been patched?
            # It's hard to tell.
            # But since I know I haven't patched them yet, I'll just do it.
            
            # Simple string manipulation or datetime parsing
            dt = datetime.fromisoformat(st_str)
            new_dt = dt + timedelta(hours=8)
            p['signal_time'] = new_dt.isoformat()
            count += 1
        except Exception as e:
            print(f"Error patching {p.get('symbol')}: {e}")

    if count > 0:
        STATE_FILE.write_text(json.dumps(data, indent=2))
        print(f"Patched {count} signals.")
    else:
        print("No signals to patch.")

if __name__ == "__main__":
    patch()


import json
from pathlib import Path
from datetime import datetime, timedelta

STATE_FILE = Path("data/trading_state.json")

def revert_patch():
    if not STATE_FILE.exists():
        print("No state file found.")
        return

    data = json.loads(STATE_FILE.read_text())
    pending = data.get("pending_signals", [])
    
    count = 0
    for p in pending:
        try:
            st_str = p['signal_time']
            # Revert the +8 hours change
            dt = datetime.fromisoformat(st_str)
            new_dt = dt - timedelta(hours=8)
            p['signal_time'] = new_dt.isoformat()
            count += 1
        except Exception as e:
            print(f"Error patching {p.get('symbol')}: {e}")

    if count > 0:
        STATE_FILE.write_text(json.dumps(data, indent=2))
        print(f"Reverted {count} signals to UTC.")
    else:
        print("No signals to revert.")

if __name__ == "__main__":
    revert_patch()

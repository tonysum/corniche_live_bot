
import importlib
import sys

def check_dependencies():
    print("🔍 Checking dependencies...")
    
    # Map of requirement name to import name
    import_map = {
        "python-dotenv": "dotenv",
        "psycopg2-binary": "psycopg2",
        "binance-sdk-derivatives-trading-usds-futures": "binance_sdk_derivatives_trading_usds_futures"
    }
    
    requirements_file = "requirements.txt"
    try:
        with open(requirements_file, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ Error: {requirements_file} not found!")
        return

    missing = []
    installed = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
            
        # Extract package name (ignore version specifiers like >=, ==)
        pkg_name = line
        for op in [">=", "==", "<=", ">", "<"]:
            if op in line:
                pkg_name = line.split(op)[0].strip()
                break
        
        # Determine import name
        import_name = import_map.get(pkg_name, pkg_name)
        # Handle cases where package name uses dashes but import uses underscores (common convention)
        if "-" in import_name and import_name not in import_map.values():
             import_name = import_name.replace("-", "_")

        try:
            importlib.import_module(import_name)
            installed.append(pkg_name)
            print(f"✅ {pkg_name} is installed")
        except ImportError:
            print(f"❌ {pkg_name} is MISSING (tried import '{import_name}')")
            missing.append(pkg_name)

    print("-" * 30)
    if missing:
        print(f"⚠️  Missing {len(missing)} dependencies:")
        for m in missing:
            print(f"   - {m}")
        print("\nPlease run: pip install -r requirements.txt")
        sys.exit(1)
    else:
        print("🎉 All dependencies are installed!")
        sys.exit(0)

if __name__ == "__main__":
    check_dependencies()

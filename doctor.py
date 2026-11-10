import json
from verification import tool_health
if __name__ == "__main__":
    status = tool_health()
    print(json.dumps(status, indent=2))
    if not all(status.values()):
        print("One or more dependencies are unavailable. The report will retain explicit tool outcomes.")

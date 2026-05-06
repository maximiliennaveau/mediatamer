import os
from mediatamer.config import load_config
from mediatamer.signals.search_ovdb import MetadataMatcher

config = load_config()
print(config)
m = MetadataMatcher(config["tmdb-api-key"])
for name in ["Nick Frost", "Jenna Coleman", "Peter Capaldi"]:
    hits = m.search_person(name)
    print(f"\n{name}:")
    for h in hits:
        print(
            f"  id:{h['id']:>10}  pop:{h['popularity']:5.1f}"
            f"  dept:{h['known_for_department']:12s}"
            f"  name:{h['name']}"
            f"  known_for:{h['known_for']}"
        )

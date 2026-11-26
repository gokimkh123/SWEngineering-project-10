import json, sys
sys.path.insert(0, "/srv/backend")
from app.models import SessionLocal
from app.services import finder
ROWS = [{"name": "haeundae", "lat": 35.159059, "lng": 129.1604, "truth": "tour:900101"}, {"name": "gwangalli", "lat": 35.153559, "lng": 129.1186, "truth": "tour:900102"}, {"name": "gamcheon", "lat": 35.097859, "lng": 129.0106, "truth": "tour:900108"}, {"name": "jagalchi", "lat": 35.096959, "lng": 129.0306, "truth": "tour:900109"}, {"name": "yonggungsa", "lat": 35.188759, "lng": 129.2233, "truth": "tour:900115"}, {"name": "oryukdo", "lat": 35.101059, "lng": 129.1245, "truth": "tour:900116"}, {"name": "yongdusan", "lat": 35.100959, "lng": 129.032, "truth": "tour:900112"}, {"name": "taejongdae", "lat": 35.052859, "lng": 129.0857, "truth": "tour:900114"}, {"name": "huinnyeoul", "lat": 35.078759, "lng": 129.0453, "truth": "tour:900113"}, {"name": "beomeosa", "lat": 35.284459, "lng": 129.0687, "truth": "tour:900121"}, {"name": "citizenspark", "lat": 35.168459, "lng": 129.057, "truth": "busan:B002"}, {"name": "dadaepo", "lat": 35.047059, "lng": 128.966, "truth": "tour:900119"}, {"name": "haeundae@gamcheon", "lat": 35.097859, "lng": 129.0106, "truth": "none"}, {"name": "gamcheon@haeundae", "lat": 35.159059, "lng": 129.1604, "truth": "none"}, {"name": "jagalchi@beomeosa", "lat": 35.284459, "lng": 129.0687, "truth": "none"}, {"name": "gwanghwamun@yonggungsa", "lat": 35.189352, "lng": 129.2233, "truth": "none"}, {"name": "synthetic-V1", "lat": 35.1586, "lng": 129.15992222222224, "truth": "tour:900101"}, {"name": "synthetic-V2", "lat": 35.15897222222222, "lng": 129.17140277777776, "truth": "tour:900103"}, {"name": "synthetic-V3", "lat": 35.15799444444444, "lng": 129.05949166666667, "truth": "kakao:S9001"}, {"name": "synthetic-V4", "lat": 35.15343611111111, "lng": 129.1191, "truth": "tour:900102"}, {"name": "synthetic-V5", "lat": 35.15533055555555, "lng": 129.1331638888889, "truth": "busan:B001"}, {"name": "synthetic-V6", "lat": 35.0974, "lng": 129.01025277777777, "truth": "tour:900108"}]
out = []
with SessionLocal() as db:
    for r in ROWS:
        cands, radius = finder.find(db, r["lat"], r["lng"])
        ids = [c.place_id for c in cands]
        out.append({"name": r["name"], "truth": r["truth"], "radius": radius, "n": len(ids), "included": (r["truth"] in ids) if r["truth"] != "none" else None, "ids": ids})
print(json.dumps(out, ensure_ascii=False))


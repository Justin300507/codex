from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def passenger(name, lat, lng, dest="Test", preference="any", max_walk_m=300):
    return {
        "id": name,
        "name": name,
        "destination": dest,
        "lat": lat,
        "lng": lng,
        "origin_station": "Vyttila",
        "budget_range": "no_limit",
        "max_walk_m": max_walk_m,
        "preference": preference,
        "meetup_tag": name,
        "pool_opted_in": True,
    }


def test_recommendation_boundaries():
    assert main.recommendation(17.9, "no_limit", "under 18")["mode"] == "cab"
    assert main.recommendation(18.0, "no_limit", "over 18")["mode"] == "bus"
    fort = main.recommendation(14.8, "no_limit", "Fort Kochi")
    assert fort["fares"]["auto"] == 320
    assert fort["fares"]["cab"] == 360


def test_pool_tiers_and_guards():
    old = main.PASSENGERS
    try:
        main.PASSENGERS = [
            passenger("a", 10.0000, 76.3200),
            passenger("b", 10.0020, 76.3200),
            passenger("c", 10.0010, 76.3210),
            passenger("d", 10.0015, 76.3195),
        ]
        assert len(main.build_groups()[0]["members"]) == 4

        main.PASSENGERS = [passenger("a", 10.0000, 76.3200), passenger("b", 10.0063, 76.3200)]
        assert len(main.build_groups()[0]["members"]) == 2

        main.PASSENGERS = [passenger("a", 10.0000, 76.3200), passenger("b", 10.0140, 76.3200)]
        assert main.build_groups() == []

        main.PASSENGERS = [passenger("a", 9.9705, 76.3200), passenger("b", 9.9645, 76.3200)]
        assert main.build_groups() == []

        main.PASSENGERS = [passenger("a", 10.0000, 76.3200, preference="women-only"), passenger("b", 10.0020, 76.3200)]
        assert main.build_groups() == []

        main.PASSENGERS = [passenger("a", 10.0000, 76.3200, max_walk_m=100), passenger("b", 10.0020, 76.3200)]
        assert main.build_groups() == []

        main.PASSENGERS = [
            passenger("a", 10.0000, 76.3200, dest="Hill Palace", preference="women-only"),
            passenger("b", 10.0020, 76.3200, dest="Hill Palace", preference="women-only"),
            passenger("c", 10.0100, 76.3200, dest="Infopark"),
            passenger("d", 10.0163, 76.3200, dest="Infopark"),
        ]
        reasons = [g["ai_reasoning"] for g in main.build_groups()]
        assert len(reasons) == len(set(reasons))
        assert {g["ai_reasoning_source"] for g in main.build_groups()} <= {"cerebras", "fallback"}
    finally:
        main.PASSENGERS = old


def test_locate_bad_and_long_inputs_do_not_crash():
    bad = client.post("/locate", json={"destination": "asdkfj123"})
    assert bad.status_code == 200
    assert "lat" in bad.json()

    long_text = "Lulu Mall Edappally " + ("near Kochi " * 60)
    long_result = client.post("/locate", json={"destination": long_text})
    assert long_result.status_code == 200
    assert "lat" in long_result.json()

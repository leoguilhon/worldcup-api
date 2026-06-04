import requests


BASE_URL = "http://localhost:8000"


def get_json(path: str):
    response = requests.get(f"{BASE_URL}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def main() -> None:
    assert get_json("/health")["status"] == "ok"
    assert get_json("/health/db")["database"] == "ok"

    groups = get_json("/groups")
    assert "A" in groups

    group_a = get_json("/groups/A/standings")
    assert len(group_a) == 4
    assert all("points" in row for row in group_a)

    live_matches = get_json("/matches/live")
    assert isinstance(live_matches, list)

    scraping_status = get_json("/scraping/status")
    assert scraping_status["status"] in {"ok", "degraded", "unknown"}
    assert "worker_status" in scraping_status
    assert "recent_runs" in scraping_status

    print("integration tests passed")


if __name__ == "__main__":
    main()

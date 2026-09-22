"""Smoke tests for profile and mitigate HTTP API endpoints."""

from fastapi.testclient import TestClient

from src.gui.app import app

client = TestClient(app)


def _write_profile_csv(path):
    path.write_text("run_id,outer_time\n1,1.0\n2,1.1\n3,0.9\n4,1.05\n5,0.95\n")


class TestProfileAPI:
    """Tests for /api/v1/profile/* endpoints."""

    def test_analyze_returns_structured_payload(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        _write_profile_csv(csv_path)

        response = client.post(
            "/api/v1/profile/analyze",
            json={"csv_path": str(csv_path), "metric": "outer_time"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "factors" in data
        assert "quality" in data
        assert "analysis_data" in data
        if data["factors"]:
            assert {"name", "strength", "rank", "method"}.issubset(data["factors"][0])

    def test_analyze_returns_error_for_missing_metric(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        _write_profile_csv(csv_path)

        response = client.post(
            "/api/v1/profile/analyze",
            json={"csv_path": str(csv_path), "metric": "nonexistent_metric"},
        )
        assert response.status_code == 200
        assert response.json().get("error") is not None

    def test_analyze_404_for_missing_file(self):
        response = client.post(
            "/api/v1/profile/analyze",
            json={"csv_path": "/no/such/file.csv", "metric": "outer_time"},
        )
        assert response.status_code == 404

    def test_analyze_accepts_filter_spec(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text(
            "run_id,backend,outer_time\n1,local,1.0\n2,mpi,10.0\n3,local,1.1\n4,mpi,11.0\n"
        )
        response = client.post(
            "/api/v1/profile/analyze",
            json={
                "csv_path": str(csv_path),
                "metric": "outer_time",
                "filters": [{"metric": "backend", "kind": "equals", "value": "local"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["error"] is None

    def test_analyze_rejects_multiple_filters_until_internal_refactor(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("run_id,backend,size,outer_time\n1,local,1,1.0\n2,mpi,2,2.0\n")
        response = client.post(
            "/api/v1/profile/analyze",
            json={
                "csv_path": str(csv_path),
                "metric": "outer_time",
                "filters": [
                    {"metric": "backend", "kind": "equals", "value": "local"},
                    {"metric": "size", "kind": "range", "min": "1", "max": "2"},
                ],
            },
        )
        assert response.status_code == 422

    def test_factors_returns_only_structured_factors(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        _write_profile_csv(csv_path)

        response = client.post(
            "/api/v1/profile/factors",
            json={"csv_path": str(csv_path), "metric": "outer_time"},
        )
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"error", "factors"}
        if data["factors"]:
            assert {"name", "strength", "rank", "method"}.issubset(data["factors"][0])

    def test_suggest_cutoff_returns_binary_cutoff(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        _write_profile_csv(csv_path)

        response = client.post(
            "/api/v1/profile/suggest-cutoff",
            json={"csv_path": str(csv_path), "metric": "outer_time"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("error") is None
        assert len(data["cutoffs"]) == 1
        assert data["strategy"] == "binary"

    def test_suggest_cutoff_manual_num_groups_returns_multiple_cutoffs(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("run_id,outer_time\n1,1.0\n2,2.0\n3,3.0\n4,4.0\n5,5.0\n")

        response = client.post(
            "/api/v1/profile/suggest-cutoff",
            json={"csv_path": str(csv_path), "metric": "outer_time", "strategy": "manual", "num_groups": 4},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "manual"
        assert len(data["cutoffs"]) == 3
        assert data["cutoffs"] == sorted(data["cutoffs"])

    def test_suggest_cutoff_422_for_missing_metric(self, tmp_path):
        csv_path = tmp_path / "test.csv"
        _write_profile_csv(csv_path)

        response = client.post(
            "/api/v1/profile/suggest-cutoff",
            json={"csv_path": str(csv_path), "metric": "missing"},
        )
        assert response.status_code == 422


class TestMitigateAPI:
    """Tests for /api/v1/mitigate/* endpoints."""

    def test_list_returns_known_mitigations(self):
        response = client.get("/api/v1/mitigate/list")
        assert response.status_code == 200
        mitigations = response.json()["mitigations"]
        assert isinstance(mitigations, list)
        assert len(mitigations) > 0
        assert any(m in mitigations for m in ["huge_pages", "mem_allocator_je", "mem_allocator_tc"])

    def test_info_returns_known_mitigation_with_backend_options_field(self):
        response = client.get("/api/v1/mitigate/info/huge_pages")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "huge_pages"
        assert "description" in data
        assert "references" in data
        assert "is_automated" in data
        assert "backend_options" in data

    def test_info_returns_404_for_unknown_mitigation(self):
        response = client.get("/api/v1/mitigate/info/nonexistent_mitigation_xyz_123")
        assert response.status_code == 404

    def test_apply_queues_job(self, tmp_path):
        md_path = tmp_path / "test.md"
        md_path.write_text("# Test Experiment\n")

        response = client.post(
            "/api/v1/mitigate/apply",
            json={"md_path": str(md_path), "mitigation_name": "huge_pages"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "queued"
        assert data["job_id"]

        status_response = client.get(f"/api/v1/mitigate/apply/{data['job_id']}")
        assert status_response.status_code == 200
        assert status_response.json()["job_id"] == data["job_id"]

    def test_apply_job_reports_error_for_nonexistent_md(self):
        response = client.post(
            "/api/v1/mitigate/apply",
            json={"md_path": "/nonexistent/path/to/file.md", "mitigation_name": "huge_pages"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        payload = {}
        for _ in range(20):
            status_response = client.get(f"/api/v1/mitigate/apply/{job_id}")
            payload = status_response.json()
            if payload["status"] in {"completed", "failed"}:
                break
        assert payload["status"] == "failed"
        assert payload["success"] is False
        assert payload["error"]

    def test_apply_unknown_job_returns_404(self):
        response = client.get("/api/v1/mitigate/apply/not-a-job")
        assert response.status_code == 404

    def test_revert_remains_documented_stub(self):
        response = client.post("/api/v1/mitigate/revert")
        assert response.status_code == 501
        assert response.json()["detail"]["operation"] == "mitigate.revert"

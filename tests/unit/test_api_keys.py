"""
Unit tests for API Key Management endpoints.
Tests all endpoints from app/api/v1/endpoints/api_keys.py
"""
import pytest
from fastapi import HTTPException
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.api_key import APIKey
from app.api.v1.endpoints.api_keys import generate_api_key


class TestGenerateAPIKey:
    """Test API key generation function."""

    def test_generate_api_key_format(self):
        """Test that generated keys have correct format."""
        full_key, key_hash, key_prefix = generate_api_key()

        assert full_key.startswith("tfk_")
        assert len(full_key) > 20
        assert len(key_hash) == 64  # SHA256 hex digest
        assert key_prefix == full_key[:12]
        assert key_prefix.startswith("tfk_")

    def test_generate_api_key_uniqueness(self):
        """Test that generated keys are unique."""
        key1, hash1, prefix1 = generate_api_key()
        key2, hash2, prefix2 = generate_api_key()

        assert key1 != key2
        assert hash1 != hash2
        assert prefix1 != prefix2


@pytest.mark.unit
class TestCreateAPIKey:
    """Test POST /api-keys endpoint."""

    def test_create_api_key_success(self, authenticated_client, master_api_key):
        """Test successful API key creation by master key."""
        response = authenticated_client.post(
            "/api/v1/api-keys",
            json={
                "name": "Test API Key",
                "email": "test@example.com",
                "organization": "Test Org",
                "expires_in_days": 365,
                "is_master_key": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test API Key"
        assert data["email"] == "test@example.com"
        assert data["organization"] == "Test Org"
        assert data["is_active"] is True
        assert data["is_master_key"] is False
        assert "api_key" in data
        assert data["api_key"].startswith("tfk_")

    def test_create_api_key_without_master_fails(self, client, sub_api_key, db):
        """Test that non-master keys cannot create new keys."""
        client.headers = {"X-API-Key": sub_api_key._test_key}

        response = client.post(
            "/api/v1/api-keys",
            json={
                "name": "Should Fail",
                "email": "test@example.com",
            },
        )

        assert response.status_code == 403
        assert "Only master keys" in response.json()["detail"]

    def test_create_api_key_with_custom_scopes(self, authenticated_client):
        """Test creating API key with custom scopes."""
        response = authenticated_client.post(
            "/api/v1/api-keys",
            json={
                "name": "Limited Key",
                "scopes": ["jobs:read", "jobs:list"],
                "expires_in_days": 30,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert set(data["scopes"]) == {"jobs:read", "jobs:list"}

    def test_create_api_key_with_ip_whitelist(self, authenticated_client):
        """Test creating API key with IP whitelist."""
        response = authenticated_client.post(
            "/api/v1/api-keys",
            json={
                "name": "IP Restricted Key",
                "ip_whitelist": ["192.168.1.100", "10.0.0.5"],
                "expires_in_days": 90,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["ip_whitelist"] == ["192.168.1.100", "10.0.0.5"]


@pytest.mark.unit
class TestGetAPIKey:
    """Test GET /api-keys/{key_id} endpoint."""

    def test_get_own_api_key(self, authenticated_client, master_api_key):
        """Test retrieving own API key."""
        response = authenticated_client.get(f"/api/v1/api-keys/{master_api_key.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == master_api_key.id
        assert data["name"] == master_api_key.name
        assert data["key_prefix"] == master_api_key.key_prefix

    def test_get_api_key_not_found(self, authenticated_client):
        """Test retrieving non-existent API key."""
        response = authenticated_client.get("/api/v1/api-keys/999999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_other_api_key_denied(self, client, sub_api_key, db):
        """Test that non-master keys cannot view other keys."""
        # Create another unrelated key
        other_key = APIKey(
            key_hash="other_hash",
            key_prefix="tfk_other",
            name="Other Key",
            is_active=True,
            permissions={},
            scopes=[],
        )
        db.add(other_key)
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.get(f"/api/v1/api-keys/{other_key.id}")

        assert response.status_code == 403


@pytest.mark.unit
class TestListAPIKeys:
    """Test GET /api-keys endpoint."""

    def test_list_api_keys_master(self, authenticated_client, master_api_key, sub_api_key):
        """Test that master key can list itself and sub-keys."""
        response = authenticated_client.get("/api/v1/api-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2  # Master + at least one sub-key
        key_ids = [k["id"] for k in data]
        assert master_api_key.id in key_ids
        assert sub_api_key.id in key_ids

    def test_list_api_keys_sub_key(self, client, sub_api_key):
        """Test that sub-key only sees itself."""
        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.get("/api/v1/api-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sub_api_key.id

    def test_list_api_keys_include_inactive(self, authenticated_client, db, master_api_key):
        """Test listing with inactive keys included."""
        # Create inactive key
        inactive_key = APIKey(
            key_hash="inactive_hash",
            key_prefix="tfk_inactive",
            name="Inactive Key",
            is_active=False,
            parent_key_id=master_api_key.id,
            permissions={},
            scopes=[],
        )
        db.add(inactive_key)
        db.commit()

        # Without include_inactive
        response = authenticated_client.get("/api/v1/api-keys")
        assert response.status_code == 200
        assert not any(k["id"] == inactive_key.id for k in response.json())

        # With include_inactive
        response = authenticated_client.get("/api/v1/api-keys?include_inactive=true")
        assert response.status_code == 200
        assert any(k["id"] == inactive_key.id for k in response.json())


@pytest.mark.unit
class TestRotateAPIKey:
    """Test POST /api-keys/{key_id}/rotate endpoint."""

    def test_rotate_api_key_success(self, authenticated_client, master_api_key, db):
        """Test successful key rotation."""
        response = authenticated_client.post(
            f"/api/v1/api-keys/{master_api_key.id}/rotate",
            json={
                "expires_old_key_in_days": 7,
                "schedule_rotation": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == f"{master_api_key.name} (Rotated)"
        assert data["rotated_from_key_id"] == master_api_key.id
        assert "api_key" in data
        assert data["api_key"] != master_api_key._test_key

        # Check old key expiration
        db.refresh(master_api_key)
        assert master_api_key.expires_at is not None
        time_until_expiry = (master_api_key.expires_at - datetime.now(timezone.utc)).days
        assert 6 <= time_until_expiry <= 7

    def test_rotate_with_scheduled_rotation(self, authenticated_client, master_api_key):
        """Test rotation with scheduled next rotation."""
        response = authenticated_client.post(
            f"/api/v1/api-keys/{master_api_key.id}/rotate",
            json={
                "expires_old_key_in_days": 3,
                "schedule_rotation": True,
                "rotation_days": 90,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["rotation_scheduled_at"] is not None

    def test_rotate_other_key_denied(self, client, sub_api_key, db):
        """Test that sub-keys cannot rotate other keys."""
        other_key = APIKey(
            key_hash="other_hash2",
            key_prefix="tfk_other2",
            name="Other Key",
            is_active=True,
            permissions={},
            scopes=[],
        )
        db.add(other_key)
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.post(
            f"/api/v1/api-keys/{other_key.id}/rotate",
            json={"expires_old_key_in_days": 7},
        )

        assert response.status_code == 403


@pytest.mark.unit
class TestUpdateScopes:
    """Test PATCH /api-keys/{key_id}/scopes endpoint."""

    def test_update_scopes_replace(self, authenticated_client, master_api_key, db):
        """Test replacing scopes."""
        new_scopes = ["jobs:read", "jobs:list"]
        response = authenticated_client.patch(
            f"/api/v1/api-keys/{master_api_key.id}/scopes",
            json={"scopes": new_scopes, "merge": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert set(data["scopes"]) == set(new_scopes)

    def test_update_scopes_merge(self, authenticated_client, master_api_key):
        """Test merging scopes."""
        original_scopes = master_api_key.scopes.copy()
        new_scopes = ["new:scope"]

        response = authenticated_client.patch(
            f"/api/v1/api-keys/{master_api_key.id}/scopes",
            json={"scopes": new_scopes, "merge": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert "new:scope" in data["scopes"]
        assert all(scope in data["scopes"] for scope in original_scopes)

    def test_update_sub_key_scopes_validation(self, authenticated_client, sub_api_key, master_api_key):
        """Test that sub-key scopes must be subset of parent."""
        # Try to add scope that parent doesn't have
        response = authenticated_client.patch(
            f"/api/v1/api-keys/{sub_api_key.id}/scopes",
            json={"scopes": ["admin:full_access"], "merge": False},
        )

        assert response.status_code == 400
        assert "subset of parent" in response.json()["detail"]


@pytest.mark.unit
class TestUpdateIPFilter:
    """Test PATCH /api-keys/{key_id}/ip-filter endpoint."""

    def test_update_ip_whitelist(self, authenticated_client, master_api_key):
        """Test updating IP whitelist."""
        response = authenticated_client.patch(
            f"/api/v1/api-keys/{master_api_key.id}/ip-filter",
            json={
                "ip_whitelist": ["192.168.1.1", "10.0.0.1"],
                "ip_blacklist": None,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ip_whitelist"] == ["192.168.1.1", "10.0.0.1"]
        assert data["ip_blacklist"] is None

    def test_update_ip_blacklist(self, authenticated_client, master_api_key):
        """Test updating IP blacklist."""
        response = authenticated_client.patch(
            f"/api/v1/api-keys/{master_api_key.id}/ip-filter",
            json={
                "ip_whitelist": None,
                "ip_blacklist": ["203.0.113.0"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ip_blacklist"] == ["203.0.113.0"]


@pytest.mark.unit
class TestGetAnalytics:
    """Test GET /api-keys/{key_id}/analytics endpoint."""

    def test_get_analytics_success(self, authenticated_client, master_api_key):
        """Test retrieving API key analytics."""
        response = authenticated_client.get(f"/api/v1/api-keys/{master_api_key.id}/analytics")

        assert response.status_code == 200
        data = response.json()
        assert data["key_id"] == master_api_key.id
        assert data["key_prefix"] == master_api_key.key_prefix
        assert "total_requests" in data
        assert "storage_used_bytes" in data
        assert "storage_usage_percent" in data
        assert "jobs_usage_percent" in data
        assert "rate_limit_status" in data

    def test_get_analytics_with_usage(self, authenticated_client, master_api_key, db):
        """Test analytics with actual usage data."""
        master_api_key.total_requests = 500
        master_api_key.storage_used_bytes = 10 * 1024 * 1024 * 1024  # 10 GB
        master_api_key.jobs_used_monthly = 100
        db.commit()

        response = authenticated_client.get(f"/api/v1/api-keys/{master_api_key.id}/analytics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_requests"] == 500
        assert data["storage_used_bytes"] == 10 * 1024 * 1024 * 1024
        assert data["jobs_used_monthly"] == 100


@pytest.mark.unit
class TestRevokeAPIKey:
    """Test DELETE /api-keys/{key_id} endpoint."""

    def test_revoke_sub_key(self, authenticated_client, sub_api_key, db):
        """Test revoking a sub-key (soft delete)."""
        response = authenticated_client.delete(
            f"/api/v1/api-keys/{sub_api_key.id}",
            params={"permanent_delete": False},
        )

        assert response.status_code == 204

        db.refresh(sub_api_key)
        assert sub_api_key.is_active is False
        assert "Revoked on" in sub_api_key.notes

    def test_permanent_delete_sub_key(self, authenticated_client, sub_api_key, db):
        """Test permanently deleting a sub-key."""
        key_id = sub_api_key.id
        response = authenticated_client.delete(
            f"/api/v1/api-keys/{key_id}",
            params={"permanent_delete": True},
        )

        assert response.status_code == 204

        # Verify key is deleted
        deleted_key = db.query(APIKey).filter(APIKey.id == key_id).first()
        assert deleted_key is None

    def test_cannot_revoke_own_key(self, authenticated_client, master_api_key):
        """Test that you cannot revoke your own API key."""
        response = authenticated_client.delete(f"/api/v1/api-keys/{master_api_key.id}")

        assert response.status_code == 400
        assert "Cannot revoke your own" in response.json()["detail"]

    def test_non_master_cannot_revoke(self, client, sub_api_key, db):
        """Test that non-master keys cannot revoke keys."""
        other_key = APIKey(
            key_hash="revoke_test",
            key_prefix="tfk_revoke",
            name="Revoke Test",
            is_active=True,
            permissions={},
            scopes=[],
        )
        db.add(other_key)
        db.commit()

        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.delete(f"/api/v1/api-keys/{other_key.id}")

        assert response.status_code == 403


@pytest.mark.unit
class TestCreateSubKey:
    """Test POST /api-keys/{parent_key_id}/sub-keys endpoint."""

    def test_create_sub_key_success(self, authenticated_client, master_api_key):
        """Test creating a sub-key under master key."""
        response = authenticated_client.post(
            f"/api/v1/api-keys/{master_api_key.id}/sub-keys",
            json={
                "name": "New Sub Key",
                "scopes": ["jobs:read", "jobs:list"],
                "expires_in_days": 30,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Sub Key"
        assert data["parent_key_id"] == master_api_key.id
        assert data["is_master_key"] is False
        assert set(data["scopes"]) == {"jobs:read", "jobs:list"}
        assert "api_key" in data

    def test_create_sub_key_inherits_limits(self, authenticated_client, master_api_key):
        """Test that sub-key inherits reduced quotas."""
        response = authenticated_client.post(
            f"/api/v1/api-keys/{master_api_key.id}/sub-keys",
            json={
                "name": "Quota Test Sub Key",
                "scopes": ["jobs:create"],
                "expires_in_days": 30,
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Should be half of parent's quotas
        assert data["rate_limit_per_hour"] == master_api_key.rate_limit_per_hour // 2
        assert data["storage_quota_gb"] == master_api_key.storage_quota_gb // 2

    def test_create_sub_key_invalid_scopes(self, authenticated_client, master_api_key):
        """Test that sub-key scopes must be subset of parent."""
        response = authenticated_client.post(
            f"/api/v1/api-keys/{master_api_key.id}/sub-keys",
            json={
                "name": "Invalid Scopes",
                "scopes": ["admin:delete_everything"],
                "expires_in_days": 30,
            },
        )

        assert response.status_code == 400
        assert "subset of parent" in response.json()["detail"]

    def test_create_sub_key_non_master_fails(self, client, sub_api_key):
        """Test that non-master keys cannot create sub-keys."""
        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.post(
            f"/api/v1/api-keys/{sub_api_key.id}/sub-keys",
            json={
                "name": "Should Fail",
                "scopes": ["jobs:read"],
                "expires_in_days": 30,
            },
        )

        assert response.status_code == 400
        assert "must be a master key" in response.json()["detail"]


@pytest.mark.unit
class TestListSubKeys:
    """Test GET /api-keys/{parent_key_id}/sub-keys endpoint."""

    def test_list_sub_keys(self, authenticated_client, master_api_key, sub_api_key):
        """Test listing sub-keys for a master key."""
        response = authenticated_client.get(f"/api/v1/api-keys/{master_api_key.id}/sub-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(k["id"] == sub_api_key.id for k in data)
        assert all(k["parent_key_id"] == master_api_key.id for k in data)

    def test_list_sub_keys_include_inactive(self, authenticated_client, master_api_key, db):
        """Test listing sub-keys with inactive ones."""
        # Create inactive sub-key
        inactive_sub = APIKey(
            key_hash="inactive_sub",
            key_prefix="tfk_inact_sub",
            name="Inactive Sub",
            is_active=False,
            parent_key_id=master_api_key.id,
            permissions={},
            scopes=[],
        )
        db.add(inactive_sub)
        db.commit()

        # Without inactive
        response = authenticated_client.get(f"/api/v1/api-keys/{master_api_key.id}/sub-keys")
        assert not any(k["id"] == inactive_sub.id for k in response.json())

        # With inactive
        response = authenticated_client.get(
            f"/api/v1/api-keys/{master_api_key.id}/sub-keys?include_inactive=true"
        )
        assert any(k["id"] == inactive_sub.id for k in response.json())

    def test_list_sub_keys_other_master_denied(self, client, sub_api_key, master_api_key):
        """Test that you can only list sub-keys for your own master key."""
        client.headers = {"X-API-Key": sub_api_key._test_key}
        response = client.get(f"/api/v1/api-keys/{master_api_key.id}/sub-keys")

        assert response.status_code == 403

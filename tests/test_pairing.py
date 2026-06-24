"""
Tests for DM Pairing Security (M3.6d)
"""
import time

import pytest

from clawhermes.channel.pairing import (
    DMPairingManager,
    PairingExpiredError,
    PairingInvalidError,
    PairingStatus,
)


class TestDMPairingManager:
    """DM 配对管理器单元测试"""

    @pytest.fixture
    def manager(self):
        return DMPairingManager()

    # ── Pairing Code Generation ──────────────────────────

    def test_generate_code_creates_valid_request(self, manager):
        req = manager.generate_code("user_001", "feishu", "ios")
        assert len(req.code) == 6
        assert req.code.isdigit()
        assert req.user_id == "user_001"
        assert req.platform == "feishu"
        assert req.device_family == "ios"
        assert req.status == PairingStatus.PENDING
        assert req.challenge  # non-empty challenge

    def test_generate_code_has_ttl(self, manager):
        req = manager.generate_code("user_002", "wechat")
        assert req.expires_at > req.created_at
        assert req.expires_at - req.created_at == pytest.approx(300, rel=0.1)

    def test_code_is_unique(self, manager):
        codes = set()
        for i in range(10):
            req = manager.generate_code(f"user_{i}", "test")
            codes.add(req.code)
        assert len(codes) == 10  # should be unique (probabilistic)

    # ── Code Verification ────────────────────────────────

    def test_verify_valid_code(self, manager):
        req = manager.generate_code("user_003", "feishu")
        response = manager._compute_challenge_response(req.challenge)

        result = manager.verify_code(req.code, response)
        assert result.status == PairingStatus.APPROVED
        assert manager.is_paired("user_003")

    def test_verify_invalid_code_raises(self, manager):
        with pytest.raises(PairingInvalidError):
            manager.verify_code("000000", "bad_response")

    def test_verify_wrong_challenge_response_raises(self, manager):
        req = manager.generate_code("user_004", "feishu")
        with pytest.raises(PairingInvalidError):
            manager.verify_code(req.code, "wrong_response")

    def test_verify_wrong_user_id_raises(self, manager):
        req = manager.generate_code("user_005", "feishu")
        response = manager._compute_challenge_response(req.challenge)
        with pytest.raises(PairingInvalidError):
            manager.verify_code(req.code, response, user_id="wrong_user")

    def test_verify_expired_code_raises(self, manager):
        req = manager.generate_code("user_006", "feishu")
        # Force expiry
        req.expires_at = time.time() - 10
        response = manager._compute_challenge_response(req.challenge)
        with pytest.raises(PairingExpiredError):
            manager.verify_code(req.code, response)

    # ── Reject ───────────────────────────────────────────

    def test_reject_code(self, manager):
        req = manager.generate_code("user_007", "feishu")
        result = manager.reject_code(req.code, "admin_001")
        assert result.status == PairingStatus.REJECTED
        assert result.approved_by == "admin_001"

    # ── Challenge System ─────────────────────────────────

    def test_challenge_verify_cycle(self, manager):
        challenge = manager.create_challenge("user_008")
        response = manager._compute_challenge_response(challenge)
        assert manager.verify_challenge(challenge, response)

    def test_challenge_wrong_response_fails(self, manager):
        challenge = manager.create_challenge("user_009")
        assert not manager.verify_challenge(challenge, "bad")

    def test_challenge_nonexistent_fails(self, manager):
        assert not manager.verify_challenge("fake_challenge", "response")

    # ── Signature ────────────────────────────────────────

    def test_sign_and_verify_payload(self, manager):
        payload = b"hello, clawhermes"
        sig = manager.sign_payload(payload)
        assert manager.verify_signature(payload, sig)

    def test_signature_tamper_detection(self, manager):
        payload = b"hello"
        sig = manager.sign_payload(payload)
        assert not manager.verify_signature(b"hello!", sig)

    # ── Paired User Management ───────────────────────────

    def test_is_paired_after_verify(self, manager):
        assert not manager.is_paired("user_010")
        req = manager.generate_code("user_010", "feishu")
        response = manager._compute_challenge_response(req.challenge)
        manager.verify_code(req.code, response)
        assert manager.is_paired("user_010")

    def test_revoke_pairing(self, manager):
        req = manager.generate_code("user_011", "feishu")
        response = manager._compute_challenge_response(req.challenge)
        manager.verify_code(req.code, response)
        assert manager.is_paired("user_011")

        revoked = manager.revoke_pairing("user_011")
        assert revoked
        assert not manager.is_paired("user_011")

    def test_revoke_nonexistent(self, manager):
        assert not manager.revoke_pairing("nobody")

    def test_list_paired_users(self, manager):
        for i in range(3):
            uid = f"user_list_{i}"
            req = manager.generate_code(uid, "feishu")
            resp = manager._compute_challenge_response(req.challenge)
            manager.verify_code(req.code, resp)

        users = manager.list_paired_users()
        assert len(users) == 3

    def test_touch_user_updates_last_active(self, manager):
        req = manager.generate_code("user_touch", "wechat")
        resp = manager._compute_challenge_response(req.challenge)
        manager.verify_code(req.code, resp)

        before = manager.get_paired_user("user_touch")
        assert before is not None
        time.sleep(0.01)
        manager.touch_user("user_touch")
        after = manager.get_paired_user("user_touch")
        assert after is not None
        assert after.last_active >= before.last_active

    # ── Status Query ─────────────────────────────────────

    def test_get_pairing_status_pending(self, manager):
        _ = manager.generate_code("user_status", "feishu")
        status = manager.get_pairing_status("user_status")
        assert status is not None
        assert status["status"] == "pending"

    def test_get_pairing_status_approved(self, manager):
        req = manager.generate_code("user_approved", "feishu")
        resp = manager._compute_challenge_response(req.challenge)
        manager.verify_code(req.code, resp)
        status = manager.get_pairing_status("user_approved")
        assert status is not None
        assert status["status"] == "approved"

    def test_get_pairing_status_not_found(self, manager):
        assert manager.get_pairing_status("nobody") is None


class TestPairingEdgeCases:
    """配对边界情况测试"""

    def test_multiple_codes_same_user(self):
        manager = DMPairingManager()
        # First code
        r1 = manager.generate_code("user_multi", "feishu")
        # Second code (new)
        r2 = manager.generate_code("user_multi", "wechat")
        assert r1.code != r2.code

    def test_cleanup_expired_requests(self):
        manager = DMPairingManager()
        r1 = manager.generate_code("user_exp1", "feishu")
        r2 = manager.generate_code("user_exp2", "wechat")

        # Force both expired
        r1.expires_at = time.time() - 10
        r2.expires_at = time.time() - 10

        pending = manager.list_pending_requests()
        assert len(pending) == 0  # cleanup should have removed them

    def test_signing_key_isolation(self):
        m1 = DMPairingManager("key1")
        m2 = DMPairingManager("key2")
        payload = b"test"

        sig1 = m1.sign_payload(payload)
        # m2 should NOT verify m1's signature
        assert not m2.verify_signature(payload, sig1)

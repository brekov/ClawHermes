"""
ClawHermes - DM Pairing Security
DM 配对安全模型：配对码生成 + 管理员审批 + 签名挑战

参考 OpenClaw 的 DM 配对机制设计，适配 ClawHermes 的 asyncio 架构
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from clawhermes.agent.exceptions import ClawHermesError

logger = logging.getLogger(__name__)


class PairingError(ClawHermesError):
    """配对相关错误"""


class PairingExpiredError(PairingError):
    """配对码过期"""


class PairingInvalidError(PairingError):
    """配对码无效"""


class PairingDeniedError(PairingError):
    """配对被拒绝"""


class PairingRateLimitError(PairingError):
    """验证尝试过于频繁（触发漏桶限流）"""


class PairingStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass
class PairingRequest:
    """配对请求"""
    code: str
    challenge: str
    user_id: str
    platform: str
    device_family: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 300)  # 5min TTL
    status: PairingStatus = PairingStatus.PENDING
    approved_by: str = ""
    approved_at: float = 0.0
    # C6: 客户端 Ed25519 公钥（hex），非空时 verify_code 改用 Ed25519 签名验证挑战
    public_key: str = ""

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.status == PairingStatus.PENDING and not self.is_expired


@dataclass
class PairedUser:
    """已配对用户"""
    user_id: str
    platform: str
    device_family: str
    paired_at: float
    approved_by: str
    last_active: float = field(default_factory=time.time)
    # C6: 客户端 Ed25519 公钥（hex），用于后续消息签名验证
    public_key: str = ""


class DMPairingManager:
    """
    DM 配对管理器

    负责：
    1. 配对码生成与验证
    2. HMAC 签名挑战（防重放）
    3. 管理员审批流
    4. 已配对用户管理
    """

    # 配对码长度（H8: 6 -> 8，扩大搜索空间至 10^8）
    CODE_LENGTH: int = 8
    # 配对码 TTL（秒）
    CODE_TTL: int = 300
    # 签名挑战 nonce TTL
    CHALLENGE_TTL: int = 60

    def __init__(self, signing_key: str | None = None, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else None
        self._signing_key: bytes = b""
        self._pending: dict[str, PairingRequest] = {}       # code -> PairingRequest
        self._paired: dict[str, PairedUser] = {}            # user_id -> PairedUser
        self._challenges: dict[str, tuple[str, float]] = {}  # challenge -> (user_id, expires)
        self._allowlist: set[str] = set()                   # admin allowlist
        # H8: 漏桶限流 — user_id -> [验证尝试时间戳]
        self._rate_limiter: dict[str, list[float]] = {}
        self._lock = threading.RLock()  # 可重入锁，保护 _pending/_paired/_challenges

        # 从持久化存储加载 signing_key 和已配对用户
        if self._db_path is not None:
            self._load_state()
        # signing_key 优先级：显式传入 > 持久化加载 > 新生成
        if signing_key:
            self._signing_key = signing_key.encode()
        if not self._signing_key:
            self._signing_key = secrets.token_bytes(32)
            if self._db_path is not None:
                self._save_state()

    # ── 配对码管理 ──────────────────────────────────────

    def generate_code(self, user_id: str, platform: str,
                      device_family: str = "", public_key: str = "") -> PairingRequest:
        """
        由管理员调用，为新用户生成配对码

        返回 PairingRequest，code 为 8 位数字。
        public_key 为可选的 Ed25519 公钥（hex），非空时验证改用签名校验。
        """
        with self._lock:
            code = secrets.randbelow(10 ** self.CODE_LENGTH)
            code_str = f"{code:0{self.CODE_LENGTH}d}"

            challenge = self._generate_challenge(user_id)

            request = PairingRequest(
                code=code_str,
                challenge=challenge,
                user_id=user_id,
                platform=platform,
                device_family=device_family,
                public_key=public_key,
            )

            self._pending[code_str] = request
            self._challenges[challenge] = (user_id, time.time() + self.CHALLENGE_TTL)

            logger.info("Pairing code generated: user=%s platform=%s code=%s",
                         user_id, platform, code_str)
            return request

    def verify_code(self, code: str, challenge_response: str,
                    user_id: str) -> PairingRequest:
        """
        用户提交配对码和挑战响应进行验证

        C6: user_id 改为必填，强制校验配对码与用户绑定关系
        H8: 调用前先经过漏桶限流（10 次/60s per user_id）
        C6: 若 request.public_key 非空，改用 Ed25519 签名验证挑战；否则回退 HMAC

        验证通过后状态变为 APPROVED
        """
        with self._lock:
            # H8: 漏桶限流 — 无论后续验证成功失败均记录本次尝试
            self._check_rate_limit(user_id)
            self._cleanup_expired()

            request = self._pending.get(code)
            if request is None:
                raise PairingInvalidError(f"无效的配对码: {code}")

            if not request.is_valid:
                if request.is_expired:
                    request.status = PairingStatus.EXPIRED
                    raise PairingExpiredError(f"配对码已过期: {code}")
                raise PairingInvalidError(f"配对码状态异常: {request.status}")

            # C6: 强制校验 user_id 绑定（删除可选前缀）
            if request.user_id != user_id:
                raise PairingInvalidError("配对码与用户不匹配")

            # C6: 挑战响应验证 — Ed25519 优先，回退 HMAC（向后兼容）
            if request.public_key:
                if not self.verify_challenge_signature(
                    request.challenge, challenge_response, request.public_key
                ):
                    raise PairingInvalidError("挑战响应验证失败")
            else:
                expected = self._compute_challenge_response(request.challenge)
                if not hmac.compare_digest(challenge_response, expected):
                    raise PairingInvalidError("挑战响应验证失败")

            request.status = PairingStatus.APPROVED
            request.approved_at = time.time()

            # 加入已配对列表
            self._paired[request.user_id] = PairedUser(
                user_id=request.user_id,
                platform=request.platform,
                device_family=request.device_family,
                paired_at=time.time(),
                approved_by=request.approved_by or "self",
                public_key=request.public_key,
            )

            logger.info("Pairing verified: user=%s platform=%s", request.user_id, request.platform)
            self._save_state()
            return request

    def reject_code(self, code: str, admin_id: str = "") -> PairingRequest:
        """管理员拒绝配对请求"""
        with self._lock:
            request = self._pending.get(code)
            if request is None:
                raise PairingInvalidError(f"无效的配对码: {code}")

            request.status = PairingStatus.REJECTED
            request.approved_by = admin_id
            logger.info("Pairing rejected: user=%s by=%s", request.user_id, admin_id)
            return request

    # ── 签名挑战 ────────────────────────────────────────

    def create_challenge(self, user_id: str) -> str:
        """为用户创建签名挑战"""
        with self._lock:
            challenge = self._generate_challenge(user_id)
            self._challenges[challenge] = (user_id, time.time() + self.CHALLENGE_TTL)
            return challenge

    def verify_challenge(self, challenge: str, response: str) -> bool:
        """验证挑战响应"""
        with self._lock:
            self._cleanup_challenges()

            entry = self._challenges.get(challenge)
            if entry is None:
                return False

            user_id, expires = entry
            if time.time() > expires:
                del self._challenges[challenge]
                return False

            expected = self._compute_challenge_response(challenge)
            return hmac.compare_digest(response, expected)

    def sign_payload(self, payload: bytes) -> str:
        """对消息签名，用于身份验证"""
        mac = hmac.new(self._signing_key, payload, hashlib.sha256)
        return mac.hexdigest()

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """验证消息签名"""
        expected = self.sign_payload(payload)
        return hmac.compare_digest(expected.encode(), signature.encode())

    # ── 已配对用户管理 ──────────────────────────────────

    def is_paired(self, user_id: str) -> bool:
        """检查用户是否已配对"""
        with self._lock:
            return user_id in self._paired

    def get_paired_user(self, user_id: str) -> PairedUser | None:
        with self._lock:
            return self._paired.get(user_id)

    def touch_user(self, user_id: str) -> None:
        """更新用户活跃时间"""
        with self._lock:
            user = self._paired.get(user_id)
            if user:
                user.last_active = time.time()

    def revoke_pairing(self, user_id: str) -> bool:
        """撤销配对"""
        with self._lock:
            if user_id in self._paired:
                del self._paired[user_id]
                logger.info("Pairing revoked: user=%s", user_id)
                self._save_state()
                return True
            return False

    def list_paired_users(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "user_id": u.user_id,
                    "platform": u.platform,
                    "device_family": u.device_family,
                    "paired_at": u.paired_at,
                    "approved_by": u.approved_by,
                    "last_active": u.last_active,
                }
                for u in self._paired.values()
            ]

    def list_pending_requests(self) -> list[dict[str, Any]]:
        with self._lock:
            self._cleanup_expired()
            return [
                {
                    "code": r.code,
                    "user_id": r.user_id,
                    "platform": r.platform,
                    "created_at": r.created_at,
                    "expires_at": r.expires_at,
                    "status": r.status.value,
                }
                for r in self._pending.values()
                if r.status == PairingStatus.PENDING
            ]

    def get_pairing_status(self, code_or_user_id: str) -> dict[str, Any] | None:
        """查询配对状态（通过配对码或用户ID）"""
        with self._lock:
            # 先查 pending
            for code, req in self._pending.items():
                if code == code_or_user_id or req.user_id == code_or_user_id:
                    return {
                        "code": req.code,
                        "user_id": req.user_id,
                        "platform": req.platform,
                        "status": req.status.value,
                        "created_at": req.created_at,
                        "expires_at": req.expires_at,
                        "is_expired": req.is_expired,
                    }

            # 再查 paired
            user = self._paired.get(code_or_user_id)
            if user:
                return {
                    "user_id": user.user_id,
                    "platform": user.platform,
                    "status": "paired",
                    "paired_at": user.paired_at,
                    "last_active": user.last_active,
                }

            return None

    # ── 内部方法 ────────────────────────────────────────

    def _generate_challenge(self, user_id: str) -> str:
        """生成 HMAC 签名挑战"""
        nonce = secrets.token_hex(16)
        payload = f"{user_id}:{nonce}:{int(time.time())}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def _compute_challenge_response(self, challenge: str) -> str:
        """计算挑战的预期响应"""
        return hmac.new(
            self._signing_key,
            challenge.encode(),
            hashlib.sha256,
        ).hexdigest()

    def verify_challenge_signature(self, challenge: str, signature: str,
                                   public_key: str) -> bool:
        """
        C6: 用 Ed25519 公钥验证挑战签名

        - challenge: 原始挑战字符串
        - signature: Ed25519 签名的 hex 编码
        - public_key: Ed25519 公钥的 hex 编码

        返回 True 表示签名有效，False 表示无效或格式错误。
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            pub_bytes = bytes.fromhex(public_key)
            sig_bytes = bytes.fromhex(signature)
            pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub_key.verify(sig_bytes, challenge.encode("utf-8"))
            return True
        except Exception as e:
            logger.warning("Ed25519 challenge signature verification failed: %s", e)
            return False

    def _check_rate_limit(self, user_id: str, max_attempts: int = 10,
                          window: int = 60) -> None:
        """
        H8: 漏桶限流 — 每个 user_id 在 window 秒内最多 max_attempts 次验证尝试

        清理 window 外的旧时间戳；若当前窗口内已满 max_attempts 则抛
        PairingRateLimitError；否则记录本次尝试时间戳。

        无论后续验证成功失败，时间戳均在此记录（在 verify_code 开头调用）。
        """
        now = time.time()
        timestamps = self._rate_limiter.get(user_id, [])
        # 清理 window 外的旧时间戳
        cutoff = now - window
        timestamps = [ts for ts in timestamps if ts > cutoff]
        # 当前窗口内已满则拒绝
        if len(timestamps) >= max_attempts:
            self._rate_limiter[user_id] = timestamps
            raise PairingRateLimitError(
                f"验证尝试过于频繁: user={user_id}, "
                f"attempts={len(timestamps)}/{max_attempts} in {window}s"
            )
        # 记录本次尝试时间戳
        timestamps.append(now)
        self._rate_limiter[user_id] = timestamps

    def _cleanup_expired(self) -> None:
        """清理过期的 pending 配对请求"""
        expired_codes = [
            code for code, req in self._pending.items()
            if req.is_expired
        ]
        for code in expired_codes:
            self._pending[code].status = PairingStatus.EXPIRED

    def _cleanup_challenges(self) -> None:
        """清理过期的挑战"""
        expired = [
            c for c, (_, exp) in self._challenges.items()
            if time.time() > exp
        ]
        for c in expired:
            del self._challenges[c]

    # ── 持久化 ──────────────────────────────────────────

    def _load_state(self) -> None:
        """从 JSON 文件加载 signing_key 和已配对用户"""
        if self._db_path is None or not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            key_hex = data.get("signing_key", "")
            if key_hex:
                self._signing_key = bytes.fromhex(key_hex)
            for item in data.get("paired_users", []):
                user = PairedUser(
                    user_id=item["user_id"],
                    platform=item["platform"],
                    device_family=item.get("device_family", ""),
                    paired_at=item["paired_at"],
                    approved_by=item.get("approved_by", ""),
                    last_active=item.get("last_active", item["paired_at"]),
                    public_key=item.get("public_key", ""),
                )
                self._paired[user.user_id] = user
            logger.info("Loaded %d paired users from %s", len(self._paired), self._db_path)
        except Exception as e:
            logger.error("Failed to load pairing state: %s", e)

    def _save_state(self) -> None:
        """将 signing_key 和已配对用户保存到 JSON 文件"""
        if self._db_path is None:
            return
        try:
            data = {
                "signing_key": self._signing_key.hex(),
                "paired_users": [
                    {
                        "user_id": u.user_id,
                        "platform": u.platform,
                        "device_family": u.device_family,
                        "paired_at": u.paired_at,
                        "approved_by": u.approved_by,
                        "last_active": u.last_active,
                        "public_key": u.public_key,
                    }
                    for u in self._paired.values()
                ],
            }
            self._db_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save pairing state: %s", e)

"""
RSA Key Manager
===============
負責 RSA 金鑰的生成、載入與存取。

啟動時嘗試從 keys/ 目錄載入金鑰；
若檔案不存在則自動生成 2048-bit RSA key pair 並寫入磁碟。
"""

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class KeyManager:
    """RSA 金鑰管理器（單一職責：只管金鑰的生命週期）"""

    _DEFAULT_KEY_DIR = Path(__file__).resolve().parents[2] / "keys"
    _PRIVATE_KEY_FILE = "private.pem"
    _PUBLIC_KEY_FILE = "public.pem"
    _KEY_SIZE = 2048

    def __init__(self, key_dir: Path | str | None = None) -> None:
        self._key_dir = Path(key_dir) if key_dir else self._DEFAULT_KEY_DIR
        self._private_key: rsa.RSAPrivateKey | None = None
        self._public_key: rsa.RSAPublicKey | None = None
        self._load_or_generate()

    # ── Public Properties ────────────────────────

    @property
    def private_key(self) -> rsa.RSAPrivateKey:
        """取得 RSA 私鑰（用於簽發 JWT）"""
        assert self._private_key is not None, "Private key not loaded"
        return self._private_key

    @property
    def public_key(self) -> rsa.RSAPublicKey:
        """取得 RSA 公鑰（用於驗證 JWT）"""
        assert self._public_key is not None, "Public key not loaded"
        return self._public_key

    # ── Internal ────────────────────────────────

    def _load_or_generate(self) -> None:
        """載入現有金鑰或自動生成新的 key pair"""
        private_path = self._key_dir / self._PRIVATE_KEY_FILE
        public_path = self._key_dir / self._PUBLIC_KEY_FILE

        if private_path.exists() and public_path.exists():
            self._load_keys(private_path, public_path)
        else:
            self._generate_and_save(private_path, public_path)

    def _load_keys(self, private_path: Path, public_path: Path) -> None:
        """從檔案載入金鑰"""
        private_pem = private_path.read_bytes()
        self._private_key = serialization.load_pem_private_key(
            private_pem, password=None
        )  # type: ignore[assignment]

        public_pem = public_path.read_bytes()
        self._public_key = serialization.load_pem_public_key(
            public_pem
        )  # type: ignore[assignment]

    def _generate_and_save(self, private_path: Path, public_path: Path) -> None:
        """生成 RSA key pair 並寫入磁碟"""
        self._key_dir.mkdir(parents=True, exist_ok=True)

        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self._KEY_SIZE,
        )
        self._public_key = self._private_key.public_key()

        # 寫入私鑰
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        private_path.write_bytes(private_pem)
        os.chmod(private_path, 0o600)  # 限制權限

        # 寫入公鑰
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_path.write_bytes(public_pem)

"""Multi-key load balancer for provider accounts.

Manages multiple API keys per provider (e.g., multiple Claude subscriptions)
with round-robin, least-used, priority, and budget-aware strategies.
"""

import asyncio
import time
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import select, update

from a1.common.logging import get_logger
from a1.common.tz import now_ist
from a1.db.engine import async_session
from a1.db.models import ProviderAccount
from config.settings import settings

log = get_logger("providers.key_pool")


class KeyPoolError(Exception):
    pass


def _get_fernet() -> Fernet | None:
    if settings.encryption_key:
        return Fernet(
            settings.encryption_key.encode()
            if isinstance(settings.encryption_key, str)
            else settings.encryption_key
        )
    return None


def encrypt_key(api_key: str) -> str:
    f = _get_fernet()
    if f:
        return f.encrypt(api_key.encode()).decode()
    return api_key  # store plaintext if no encryption key configured


def decrypt_key(encrypted: str) -> str:
    f = _get_fernet()
    if f:
        try:
            return f.decrypt(encrypted.encode()).decode()
        except Exception:
            return encrypted  # may be plaintext from before encryption was configured
    return encrypted


class KeyPool:
    """Manages multiple API keys per provider with load balancing."""

    def __init__(self):
        self._accounts: dict[str, list[ProviderAccount]] = {}  # provider -> accounts
        self._round_robin_idx: dict[str, int] = {}
        self._disabled_until: dict[str, float] = {}  # account_id -> timestamp
        self._rpm_counters: dict[str, list[float]] = {}  # account_id -> list of request timestamps
        self._lock = asyncio.Lock()

    async def load_accounts(self):
        """Load all active provider accounts from DB."""
        async with async_session() as session:
            stmt = (
                select(ProviderAccount)
                .where(ProviderAccount.is_active.is_(True))
                .order_by(ProviderAccount.priority.desc())
            )
            result = await session.execute(stmt)
            accounts = list(result.scalars().all())

        self._accounts.clear()
        for acc in accounts:
            provider = acc.provider
            if provider not in self._accounts:
                self._accounts[provider] = []
            self._accounts[provider].append(acc)

        total = sum(len(accs) for accs in self._accounts.values())
        log.info(f"Loaded {total} provider accounts across {len(self._accounts)} providers")

    def get_providers_with_accounts(self) -> list[str]:
        """Return list of providers that have at least one account configured."""
        return [p for p, accs in self._accounts.items() if accs]

    async def get_key(self, provider: str) -> tuple[str, uuid.UUID, str] | None:
        """Get the best available API key for a provider.

        Returns (decrypted_api_key, account_id, account_name) or None if no keys available.
        """
        accounts = self._accounts.get(provider, [])
        if not accounts:
            return None

        strategy = settings.key_pool_strategy
        now = time.time()

        # Filter out temporarily disabled accounts
        available = [a for a in accounts if self._disabled_until.get(str(a.id), 0) < now]

        if not available:
            # All disabled — try the one with earliest re-enable
            available = accounts

        if not available:
            return None

        if strategy == "round_robin":
            account = self._select_round_robin(provider, available)
        elif strategy == "least_used":
            account = self._select_least_used(provider, available)
        elif strategy == "priority":
            account = available[0]  # already sorted by priority desc
        elif strategy == "budget_aware":
            account = self._select_budget_aware(available)
        else:
            account = self._select_round_robin(provider, available)

        api_key = decrypt_key(account.api_key_encrypted)
        return api_key, account.id, account.name

    def _select_round_robin(
        self, provider: str, accounts: list[ProviderAccount]
    ) -> ProviderAccount:
        idx = self._round_robin_idx.get(provider, 0) % len(accounts)
        self._round_robin_idx[provider] = idx + 1
        return accounts[idx]

    def _select_least_used(self, provider: str, accounts: list[ProviderAccount]) -> ProviderAccount:
        now = time.time()
        min_rpm = float("inf")
        best = accounts[0]
        for acc in accounts:
            acc_id = str(acc.id)
            timestamps = self._rpm_counters.get(acc_id, [])
            # Count requests in last 60 seconds
            recent = [t for t in timestamps if now - t < 60]
            self._rpm_counters[acc_id] = recent
            if len(recent) < min_rpm:
                min_rpm = len(recent)
                best = acc
        return best

    def _select_budget_aware(self, accounts: list[ProviderAccount]) -> ProviderAccount:
        for acc in accounts:
            if acc.monthly_budget_usd is None:
                return acc  # no budget = unlimited
            if float(acc.current_month_cost_usd) < float(acc.monthly_budget_usd):
                return acc
        # All over budget — use the one with most remaining budget
        return max(
            accounts,
            key=lambda a: float(a.monthly_budget_usd or 0) - float(a.current_month_cost_usd),
        )

    async def report_usage(self, account_id: uuid.UUID, tokens: int, cost: float):
        """Report successful usage for an account."""
        acc_id = str(account_id)
        # Track RPM
        if acc_id not in self._rpm_counters:
            self._rpm_counters[acc_id] = []
        self._rpm_counters[acc_id].append(time.time())

        # Update DB counters (fire-and-forget)
        try:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(ProviderAccount)
                        .where(ProviderAccount.id == account_id)
                        .values(
                            total_requests=ProviderAccount.total_requests + 1,
                            total_tokens=ProviderAccount.total_tokens + tokens,
                            current_month_cost_usd=ProviderAccount.current_month_cost_usd + cost,
                            last_used_at=now_ist(),
                            last_error=None,
                        )
                    )
        except Exception as e:
            log.error(f"Failed to update account usage: {e}")

    async def report_error(self, account_id: uuid.UUID, error: str):
        """Report an error for an account. Temporarily disables it on rate limit errors."""
        acc_id = str(account_id)

        # Disable for 60 seconds on rate limit
        if "429" in error or "rate" in error.lower():
            self._disabled_until[acc_id] = time.time() + 60
            log.warning(f"Account {acc_id} rate limited, disabled for 60s")

        # Disable for 300 seconds on auth error
        if "401" in error or "403" in error or "auth" in error.lower():
            self._disabled_until[acc_id] = time.time() + 300
            log.warning(f"Account {acc_id} auth error, disabled for 300s")

        try:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(ProviderAccount)
                        .where(ProviderAccount.id == account_id)
                        .values(last_error=error)
                    )
        except Exception as e:
            log.error(f"Failed to update account error: {e}")


# Singleton
key_pool = KeyPool()

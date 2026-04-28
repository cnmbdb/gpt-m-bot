import json
import requests
from typing import Optional
import config


class BillingService:
    def __init__(self):
        self.base = config.BILLING_URL

    def _get(self, path: str):
        r = requests.get(f"{self.base}{path}", timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, data: dict):
        r = requests.post(f"{self.base}{path}", json=data, timeout=10)
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        return self._get("/health")

    def get_user(self, user_id: str) -> dict:
        return self._get(f"/user/{user_id}")

    def get_balance(self, user_id: str) -> dict:
        return self._get(f"/balance/{user_id}")

    def deduct(self, user_id: str, amount: int, reason: str = "") -> dict:
        return self._post("/deduct", {"userId": user_id, "amount": amount, "reason": reason})

    def recharge(self, user_id: str, amount: float, coin: str = "USDT") -> dict:
        return self._post("/recharge", {"userId": user_id, "amount": amount, "coin": coin})

    def get_order(self, order_id: str) -> dict:
        return self._get(f"/order/{order_id}")

    def get_orders(self, user_id: str) -> dict:
        return self._get(f"/orders/{userId}")

    def refund(self, user_id: str, amount: int, reason: str = "") -> dict:
        return self._post("/refund", {"userId": user_id, "amount": amount, "reason": reason})

    def claim_bonus(self, user_id: str) -> dict:
        return self._post("/claim-bonus", {"userId": user_id})

    def notify_transfer(self, order_id: str, tx_hash: str = "") -> dict:
        return self._post("/notify-transfer", {"orderId": order_id, "txHash": tx_hash})

    def get_pending_orders(self) -> list:
        return self._get("/pending-orders")

    def get_transactions(self, user_id: str) -> list:
        return self._get(f"/transactions/{user_id}")

    def bind_referrer(self, user_id: str, referrer_id: str) -> dict:
        return self._post("/bind-referrer", {"userId": user_id, "referrerId": referrer_id})

    def get_referral_info(self, user_id: str) -> dict:
        return self._get(f"/referral/{user_id}")

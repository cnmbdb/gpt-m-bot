import json
import time
import config


class LanguageService:
    def __init__(self):
        self.lang_file = config.LANG_FILE

    def _load(self) -> dict:
        try:
            with open(self.lang_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, prefs: dict):
        with open(self.lang_file, "w") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)

    def get(self, user_id: str) -> str | None:
        prefs = self._load()
        return prefs.get(str(user_id), {}).get("lang")

    def set(self, user_id: str, lang: str):
        prefs = self._load()
        uid = str(user_id)
        if uid not in prefs:
            prefs[uid] = {}
        prefs[uid]["lang"] = lang
        prefs[uid]["last_active"] = int(time.time())
        self._save(prefs)

    def is_new_or_inactive(self, user_id: str, days: int = 7) -> bool:
        """没有设置过语言，或超过指定天数未活跃，需要重新选语言"""
        prefs = self._load()
        uid = str(user_id)
        if uid not in prefs:
            return True
        user_pref = prefs[uid]
        # 没有语言设置 → 选语言
        if not user_pref.get("lang"):
            return True
        last = user_pref.get("last_active")
        if not last:
            return True
        return (int(time.time()) - last) > (days * 86400)

    def touch(self, user_id: str):
        """更新最后活跃时间"""
        prefs = self._load()
        uid = str(user_id)
        if uid not in prefs:
            prefs[uid] = {}
        prefs[uid]["last_active"] = int(time.time())
        self._save(prefs)

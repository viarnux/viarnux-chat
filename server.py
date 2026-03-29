import socket
import threading
import time
from datetime import datetime
import customtkinter as ctk
import tkinter as tk
from tkinter import font as tkfont

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

HOST = '0.0.0.0'
PORT = 3455
MAX_CONNECTIONS = 250

clients = []
clients_lock = threading.Lock()
user_names = {}
user_avatars = {}
groups = {}

def send_line(sock, text):
    try:
        sock.send((text + '\n').encode('utf-8'))
        return True
    except:
        return False

def recv_line(sock, buffer, chunk_size=65536):
    while '\n' not in buffer:
        chunk = sock.recv(chunk_size).decode('utf-8')
        if not chunk:
            raise ConnectionError("Socket closed")
        buffer += chunk
    line, buffer = buffer.split('\n', 1)
    return line.strip(), buffer

def broadcast(message, sender=None):
    if not message.endswith(b'\n'):
        message = message + b'\n'
    with clients_lock:
        for client_sock, addr in clients[:]:
            try:
                if sender is None or client_sock != sender:
                    client_sock.send(message)
            except:
                pass

def sock_for_nick(nick):
    with clients_lock:
        for sock, name in user_names.items():
            if name == nick:
                return sock
    return None

def send_to_group(group_name, message_line, exclude_sock=None):
    members = groups.get(group_name, set())
    for member_nick in list(members):
        sock = sock_for_nick(member_nick)
        if sock and sock != exclude_sock:
            send_line(sock, message_line)

def remove_client(sock, addr):
    name = None
    with clients_lock:
        if (sock, addr) in clients:
            clients.remove((sock, addr))
            if sock in user_names:
                name = user_names.pop(sock)
                user_avatars.pop(name, None)
            if len(clients) == 0:
                groups.clear()
    if name:
        broadcast(f"USER_LEFT:{name}".encode('utf-8'))
        GUI.log_event(f"Відключився: {name}  ({addr[0]})", tag="leave")
        GUI.update_stats()
    try:
        sock.close()
    except:
        pass

def handle_client(client_sock, addr):
    try:
        buf = ""
        line, buf = recv_line(client_sock, buf)
        nickname = line.replace("UPDATE_NICK:", "").strip()
        user_names[client_sock] = nickname

        client_sock.settimeout(2.0)
        try:
            avatar_line, buf = recv_line(client_sock, buf)
            if avatar_line.startswith("AVATAR:"):
                parts = avatar_line.split(":", 2)
                if len(parts) == 3:
                    user_avatars[nickname] = parts[2]
        except:
            pass
        client_sock.settimeout(None)

        broadcast(f"NEW_USER:{nickname}".encode('utf-8'), sender=client_sock)
        GUI.log_event(f"Підключився: {nickname}  ({addr[0]})", tag="join")
        GUI.update_stats()

        if nickname in user_avatars:
            broadcast(f"NEW_USER_AVATAR:{nickname}:{user_avatars[nickname]}".encode('utf-8'), sender=client_sock)

        with clients_lock:
            existing = [(name, user_avatars.get(name, "")) for name in user_names.values() if name != nickname]

        if existing:
            names_only = [n for n, _ in existing]
            send_line(client_sock, f"USER_LIST:{','.join(names_only)}")
            for ex_name, ex_avatar in existing:
                if ex_avatar:
                    send_line(client_sock, f"AVATAR_OF:{ex_name}:{ex_avatar}")

        user_groups = [(gname, list(mems)) for gname, mems in groups.items() if nickname in mems]
        for gname, mems in user_groups:
            send_line(client_sock, f"GROUP_CREATED:{gname}:server:{','.join(mems)}")

        while True:
            line, buf = recv_line(client_sock, buf)
            if not line:
                continue
            if line.startswith("SEND_TO:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    target_user = parts[1]
                    msg_text = parts[2]
                    sender_name = "Unknown"
                    target_sock = None
                    with clients_lock:
                        sender_name = user_names.get(client_sock, "Unknown")
                        for sock, name in user_names.items():
                            if name == target_user:
                                target_sock = sock
                                break
                    sent = False
                    if target_sock:
                        sent = send_line(target_sock, f"MESSAGE_FROM:{sender_name}:{msg_text}")
                    if not sent:
                        send_line(client_sock, f"MESSAGE_FROM:System:Користувач {target_user} офлайн")
                    GUI.log_event(f"Повідомлення: {sender_name} → {target_user}", tag="msg")

            elif line.startswith("UPDATE_NICK:"):
                new_nick = line.replace("UPDATE_NICK:", "").strip()
                if new_nick and new_nick != user_names.get(client_sock):
                    old_nick = user_names.get(client_sock, "")
                    user_names[client_sock] = new_nick
                    if old_nick in user_avatars:
                        user_avatars[new_nick] = user_avatars.pop(old_nick)
                    for gname, mems in groups.items():
                        if old_nick in mems:
                            mems.discard(old_nick)
                            mems.add(new_nick)
                    GUI.log_event(f"Нік змінено: {old_nick} → {new_nick}", tag="info")

            elif line.startswith("AVATAR:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    nick = user_names.get(client_sock, "")
                    avatar_data = parts[2]
                    user_avatars[nick] = avatar_data
                    broadcast(f"NEW_USER_AVATAR:{nick}:{avatar_data}".encode('utf-8'), sender=client_sock)

            elif line.startswith("CREATE_GROUP:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    gname = parts[1].strip()
                    raw_members = parts[2].strip()
                    creator = user_names.get(client_sock, "Unknown")
                    members = set(m.strip() for m in raw_members.split(",") if m.strip())
                    members.add(creator)
                    if gname and gname not in groups:
                        groups[gname] = members
                        members_str = ",".join(members)
                        for member_nick in list(members):
                            sock = sock_for_nick(member_nick)
                            if sock:
                                send_line(sock, f"GROUP_CREATED:{gname}:{creator}:{members_str}")
                        GUI.log_event(f"Група створена: «{gname}» ({creator})", tag="group")
                    else:
                        send_line(client_sock, f"MESSAGE_FROM:System:Група '{gname}' вже існує")

            elif line.startswith("GROUP_MSG:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    gname = parts[1].strip()
                    msg_text = parts[2]
                    sender_name = user_names.get(client_sock, "Unknown")
                    if gname in groups and sender_name in groups[gname]:
                        send_to_group(gname, f"GROUP_MSG_FROM:{gname}:{sender_name}:{msg_text}")
                    else:
                        send_line(client_sock, f"MESSAGE_FROM:System:Ви не є учасником групи '{gname}'")
                    GUI.log_event(f"Груп. повідомлення: {sender_name} → [{gname}]", tag="group")

    except Exception as e:
        pass
    finally:
        remove_client(client_sock, addr)


class ViarnuxApp(ctk.CTk):
    ACCENT   = "#4FC3F7"
    ACCENT2  = "#00E5FF"
    BG_DEEP  = "#0A0E1A"
    BG_MID   = "#0F1628"
    BG_PANEL = "#131C35"
    BG_CARD  = "#1A2440"
    TEXT_DIM = "#4A5568"
    TAG_COLORS = {
        "join":  "#00E676",
        "leave": "#FF5252",
        "msg":   "#4FC3F7",
        "group": "#CE93D8",
        "info":  "#FFD54F",
        "sys":   "#546E7A",
    }

    def __init__(self):
        super().__init__()
        self.title("Viarnux — Server")
        self.geometry("960x660")
        self.minsize(820, 560)
        self.configure(fg_color=self.BG_DEEP)

        self._server_sock = None
        self._running = False
        self._blink_state = False
        self._blink_job = None

        self._build_ui()
        self.after(200, self._animate_idle)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=self.BG_MID, height=64, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        logo_frame = ctk.CTkFrame(header, fg_color="transparent")
        logo_frame.pack(side="left", padx=20, pady=0, fill="y")

        self._dot = tk.Canvas(logo_frame, width=12, height=12,
                              bg=self.BG_MID, highlightthickness=0)
        self._dot.pack(side="left", pady=0, padx=(0, 10))
        self._draw_dot(self.TEXT_DIM)

        title_lbl = ctk.CTkLabel(logo_frame, text="VIARNUX",
                                 font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
                                 text_color=self.ACCENT)
        title_lbl.pack(side="left")

        sub_lbl = ctk.CTkLabel(logo_frame, text=" · server",
                               font=ctk.CTkFont(family="Consolas", size=12),
                               text_color=self.TEXT_DIM)
        sub_lbl.pack(side="left", pady=(5, 0))

        self._status_lbl = ctk.CTkLabel(header, text="● OFFLINE",
                                        font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                                        text_color="#FF5252",
                                        fg_color="#1A0A0A",
                                        corner_radius=6,
                                        padx=10, pady=4)
        self._status_lbl.pack(side="left", padx=12, pady=18)

        ctrl = ctk.CTkFrame(header, fg_color="transparent")
        ctrl.pack(side="right", padx=20, pady=0, fill="y")

        self._toggle_btn = ctk.CTkButton(
            ctrl, text="  ▶  ЗАПУСТИТИ", width=160, height=36,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            fg_color=self.BG_CARD, hover_color="#1E3A5F",
            border_width=1, border_color=self.ACCENT,
            text_color=self.ACCENT, corner_radius=8,
            command=self._toggle_server)
        self._toggle_btn.pack(side="right", pady=14)

        self._clear_btn = ctk.CTkButton(
            ctrl, text="✕ Очистити лог", width=130, height=36,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="transparent", hover_color=self.BG_CARD,
            border_width=1, border_color=self.TEXT_DIM,
            text_color=self.TEXT_DIM, corner_radius=8,
            command=self._clear_log)
        self._clear_btn.pack(side="right", padx=(0, 10), pady=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        sidebar = ctk.CTkFrame(body, fg_color=self.BG_PANEL,
                               width=200, corner_radius=12)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="СТАТИСТИКА",
                     font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                     text_color=self.TEXT_DIM).pack(pady=(18, 6), padx=16, anchor="w")

        self._stat_widgets = {}
        stats = [
            ("online",   "● Онлайн",     "0"),
            ("groups",   "◈ Груп",        "0"),
            ("avatars",  "◉ Аватарів",    "0"),
            ("uptime",   "◷ Аптайм",      "—"),
        ]
        for key, label, val in stats:
            card = ctk.CTkFrame(sidebar, fg_color=self.BG_CARD, corner_radius=8)
            card.pack(fill="x", padx=12, pady=5)
            ctk.CTkLabel(card, text=label,
                         font=ctk.CTkFont(family="Consolas", size=10),
                         text_color=self.TEXT_DIM, anchor="w").pack(padx=12, pady=(8, 0), fill="x")
            vl = ctk.CTkLabel(card, text=val,
                              font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
                              text_color=self.ACCENT2, anchor="w")
            vl.pack(padx=12, pady=(2, 8), fill="x")
            self._stat_widgets[key] = vl

        ctk.CTkFrame(sidebar, fg_color=self.TEXT_DIM, height=1).pack(
            fill="x", padx=12, pady=14)

        ctk.CTkLabel(sidebar, text="КОНФІГУРАЦІЯ",
                     font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                     text_color=self.TEXT_DIM).pack(pady=(0, 6), padx=16, anchor="w")

        for label, value in [("HOST", HOST), ("PORT", str(PORT)), ("MAX", str(MAX_CONNECTIONS))]:
            row = ctk.CTkFrame(sidebar, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(family="Consolas", size=9),
                         text_color=self.TEXT_DIM, width=40, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value,
                         font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                         text_color="#90CAF9", anchor="w").pack(side="left")

        right = ctk.CTkFrame(body, fg_color=self.BG_PANEL, corner_radius=12)
        right.pack(side="left", fill="both", expand=True)

        log_header = ctk.CTkFrame(right, fg_color="transparent", height=40)
        log_header.pack(fill="x", padx=16, pady=(14, 0))
        log_header.pack_propagate(False)
        ctk.CTkLabel(log_header, text="ЖУРНАЛ ПОДІЙ",
                     font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
                     text_color=self.TEXT_DIM).pack(side="left", pady=8)

        legend = ctk.CTkFrame(log_header, fg_color="transparent")
        legend.pack(side="right")
        for tag, color in [("join", "#00E676"), ("leave", "#FF5252"),
                           ("msg", "#4FC3F7"), ("group", "#CE93D8")]:
            ctk.CTkLabel(legend, text=f"● {tag}",
                         font=ctk.CTkFont(family="Consolas", size=9),
                         text_color=color).pack(side="left", padx=5)

        log_frame = ctk.CTkFrame(right, fg_color=self.BG_DEEP, corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        self._log = tk.Text(
            log_frame,
            bg=self.BG_DEEP, fg="#CFD8DC",
            font=("Consolas", 11),
            bd=0, highlightthickness=0,
            insertbackground=self.ACCENT,
            selectbackground=self.BG_CARD,
            wrap="word", state="disabled",
            padx=14, pady=10,
            spacing1=3, spacing3=3,
        )
        self._log.pack(side="left", fill="both", expand=True)

        sb = ctk.CTkScrollbar(log_frame, command=self._log.yview,
                              fg_color=self.BG_DEEP, button_color=self.BG_CARD,
                              button_hover_color=self.ACCENT)
        sb.pack(side="right", fill="y")
        self._log.configure(yscrollcommand=sb.set)

        for tag, color in self.TAG_COLORS.items():
            self._log.tag_configure(tag, foreground=color)
        self._log.tag_configure("time", foreground=self.TEXT_DIM)
        self._log.tag_configure("dim",  foreground=self.TEXT_DIM)

        bar = ctk.CTkFrame(self, fg_color=self.BG_MID, height=28, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._footer_lbl = ctk.CTkLabel(
            bar, text=f"  {HOST}:{PORT}  |  Viarnux v1.0",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=self.TEXT_DIM, anchor="w")
        self._footer_lbl.pack(side="left", fill="y")

        self._msg_count_lbl = ctk.CTkLabel(
            bar, text="Повідомлень: 0  ",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=self.TEXT_DIM, anchor="e")
        self._msg_count_lbl.pack(side="right", fill="y")

        self._msg_count = 0
        self._start_time = None

    def _draw_dot(self, color):
        self._dot.delete("all")
        self._dot.create_oval(2, 2, 10, 10, fill=color, outline="")

    def _animate_idle(self):
        if not self._running:
            self._blink_state = not self._blink_state
            self._draw_dot(self.TEXT_DIM if self._blink_state else self.BG_MID)
        self._blink_job = self.after(900, self._animate_idle)

    def log_event(self, text, tag="sys"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"  {ts}  ", "time")
        self._log.insert("end", text + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")
        if tag == "msg" or tag == "group":
            self._msg_count += 1
            self._msg_count_lbl.configure(text=f"Повідомлень: {self._msg_count}  ")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def update_stats(self):
        self.after(0, self._refresh_stats)

    def _refresh_stats(self):
        with clients_lock:
            online = len(clients)
        self._stat_widgets["online"].configure(text=str(online))
        self._stat_widgets["groups"].configure(text=str(len(groups)))
        self._stat_widgets["avatars"].configure(text=str(len(user_avatars)))
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            h, m = divmod(elapsed // 60, 60)
            s = elapsed % 60
            self._stat_widgets["uptime"].configure(text=f"{h:02d}:{m:02d}:{s:02d}")

    def _toggle_server(self):
        if not self._running:
            self._start_server()
        else:
            self._stop_server()

    def _start_server(self):
        try:
            self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.bind((HOST, PORT))
            self._server_sock.listen(MAX_CONNECTIONS)
        except Exception as e:
            self.log_event(f"Помилка запуску: {e}", tag="leave")
            return

        self._running = True
        self._start_time = time.time()
        self._status_lbl.configure(text="● ONLINE", text_color="#00E676",
                                   fg_color="#0A1A0A")
        self._toggle_btn.configure(text="  ■  ЗУПИНИТИ",
                                   border_color="#FF5252", text_color="#FF5252")
        self._draw_dot(self.ACCENT)
        self.log_event(f"Сервер запущено → {HOST}:{PORT}", tag="join")
        self._uptime_job = self.after(1000, self._tick_uptime)

        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()

    def _stop_server(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except:
                pass
        self._status_lbl.configure(text="● OFFLINE", text_color="#FF5252",
                                   fg_color="#1A0A0A")
        self._toggle_btn.configure(text="  ▶  ЗАПУСТИТИ",
                                   border_color=self.ACCENT, text_color=self.ACCENT)
        self._draw_dot(self.TEXT_DIM)
        self.log_event("Сервер зупинено.", tag="leave")
        self._stat_widgets["uptime"].configure(text="—")
        self._start_time = None

    def _accept_loop(self):
        while self._running:
            try:
                client_sock, addr = self._server_sock.accept()
                with clients_lock:
                    clients.append((client_sock, addr))
                t = threading.Thread(target=handle_client,
                                     args=(client_sock, addr), daemon=True)
                t.start()
            except:
                break

    def _tick_uptime(self):
        if self._running and self._start_time:
            self._refresh_stats()
            self._uptime_job = self.after(1000, self._tick_uptime)

    def _on_close(self):
        self._stop_server()
        self.destroy()

GUI: ViarnuxApp = None  

def main():
    global GUI
    GUI = ViarnuxApp()
    GUI.mainloop()

if __name__ == "__main__":
    main()

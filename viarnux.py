from customtkinter import *
from PIL import Image, ImageDraw, ImageOps
from socket import *
from threading import *
import tkinter.filedialog as fd
import os
import tkinter as tk
import base64
import io

class Autenfig(CTk):
    def __init__(self):
        super().__init__()
        self.title("Messenger Setup")
        self.geometry("400x600")
        self.resizable(False, False)

        self.avatar_path = None
        self.bg_color = "#121212"
        self.accent_color = "#3D5AFE"
        self.configure(fg_color=self.bg_color)

        self.setup_ui()
        self.center_window()

    def setup_ui(self):
        self.main_container = CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=40)

        self.title_label = CTkLabel(self.main_container, text="Реєстрація",
                                    font=CTkFont(family="Inter", size=32, weight="bold"), text_color="#FFFFFF")
        self.title_label.pack(pady=(50, 10))

        self.avatar_frame = CTkFrame(self.main_container, fg_color="transparent")
        self.avatar_frame.pack(pady=10)

        self.avatar_btn = CTkButton(self.avatar_frame, text="+", width=80, height=80, corner_radius=40,
                                    fg_color="#2A2A2A", hover_color="#333333", font=CTkFont(size=30),
                                    command=self.choose_avatar)
        self.avatar_btn.pack()

        self.input_frame = CTkFrame(self.main_container, fg_color="transparent")
        self.input_frame.pack(fill="x", pady=10)

        self.entry_username = self.create_input("Нікнейм", "user123")
        self.entry_ip = self.create_input("Адреса сервера (IP)", "127.0.0.1")
        self.entry_port = self.create_input("Порт", "8080")

        self.btn_connect = CTkButton(self.main_container, text="Підключитися", height=55, corner_radius=15,
                                     fg_color=self.accent_color, font=CTkFont(size=16, weight="bold"),
                                     command=self.handle_registration)
        self.btn_connect.pack(fill="x", pady=(30, 10))

        self.status_label = CTkLabel(self.main_container, text="", text_color="#FF5252")
        self.status_label.pack()

    def create_input(self, label_text, placeholder):
        lbl = CTkLabel(self.input_frame, text=label_text, font=CTkFont(size=13, weight="bold"), text_color="#BBBBBB")
        lbl.pack(anchor="w", padx=5, pady=(10, 2))
        entry = CTkEntry(self.input_frame, placeholder_text=placeholder, height=45, corner_radius=10)
        entry.pack(fill="x", pady=(0, 5))
        return entry

    def choose_avatar(self):
        file_path = fd.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.jpeg")])
        if file_path:
            self.avatar_path = file_path
            img = Image.open(file_path)
            img = img.resize((80, 80), Image.Resampling.LANCZOS)
            self.avatar_img = CTkImage(light_image=img, dark_image=img, size=(80, 80))
            self.avatar_btn.configure(image=self.avatar_img, text="")

    def handle_registration(self):
        user = self.entry_username.get()
        ip = self.entry_ip.get()
        port = self.entry_port.get()

        if not user or not ip or not port:
            self.status_label.configure(text="Заповніть усі поля!")
            return

        try:
            client_socket = socket(AF_INET, SOCK_STREAM)
            client_socket.settimeout(5)
            client_socket.connect((ip, int(port)))
            client_socket.settimeout(None)

            client_socket.send(f"UPDATE_NICK:{user}\n".encode('utf-8'))

            if self.avatar_path:
                try:
                    img = Image.open(self.avatar_path).convert("RGB")
                    img = img.resize((45, 45), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    client_socket.send(f"AVATAR:{user}:{b64}\n".encode('utf-8'))
                except:
                    pass

            self.status_label.configure(text="Успішно!", text_color="#4CAF50")
            self.withdraw()
            Main(self, user, self.avatar_path, client_socket)
        except Exception:
            self.status_label.configure(text="Помилка з'єднання!")

    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.winfo_screenheight() // 2) - (600 // 2)
        self.geometry(f"400x600+{x}+{y}")

class Main(CTkToplevel):
    def __init__(self, master, current_user, avatar_path, client_socket):
        super().__init__(master)
        self.title("Messenger Pro")
        self.geometry("1100x750")
        self.minsize(900, 650)
        self.resizable(False, True)
        self.bg_color = "#121212"
        self.accent_color = "#3D5AFE"
        self.configure(fg_color=self.bg_color)

        self.client_socket = client_socket
        self.current_user = current_user
        self.user_description = "Немає опису"
        self.avatar_path = avatar_path

        self.chats_history = {"Нотатки": []}   
        self.active_chat = None
        self.all_users_buttons = {}             
        self.user_avatars = {}                  
        self.user_avatar_labels = {}            
        self.group_members = {}                 
        self.known_online_users = []           

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.setup_sidebar(avatar_path)
        self.setup_chat_area()
        self.add_user("Нотатки", is_notes=True)
        self.update_input_state()

        if self.client_socket:
            Thread(target=self.receive_messages, daemon=True).start()

    def make_circle(self, image, size=(45, 45)):
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + size, fill=255)
        output = ImageOps.fit(image, size, centering=(0.5, 0.5))
        output.putalpha(mask)
        return output

    def b64_to_ctk_circle(self, b64_str, size=(40, 40)):
        raw = base64.b64decode(b64_str)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img = img.resize(size, Image.Resampling.LANCZOS)
        return CTkImage(self.make_circle(img, size), size=size)

    def apply_avatar(self, username, b64_str):
        try:
            ctk_img = self.b64_to_ctk_circle(b64_str)
            self.user_avatars[username] = ctk_img
            if username in self.user_avatar_labels:
                self.user_avatar_labels[username].configure(image=ctk_img, text="")
        except:
            pass

    def setup_sidebar(self, avatar_path):
        self.sidebar = CTkFrame(self, width=280, corner_radius=0, fg_color="#1A1A1A")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        profile_box = CTkFrame(self.sidebar, fg_color="#252525", corner_radius=12)
        profile_box.pack(pady=20, padx=15, fill="x")
        try:
            raw_img = Image.open(avatar_path) if avatar_path else Image.new('RGB', (100, 100), color=self.accent_color)
            round_img = self.make_circle(raw_img, (45, 45))
            self.profile_img = CTkImage(round_img, size=(45, 45))
            CTkLabel(profile_box, text="", image=self.profile_img).pack(side="left", padx=10, pady=10)
        except:
            CTkLabel(profile_box, text="👤", font=("Inter", 20)).pack(side="left", padx=10, pady=10)

        self.profile_name_label = CTkLabel(profile_box, text=self.current_user, font=("Inter", 14, "bold"))
        self.profile_name_label.pack(side="left", padx=5)

        for widget in [profile_box] + list(profile_box.winfo_children()):
            widget.bind("<Button-1>", lambda e: self.open_profile())

        new_group_btn = CTkButton(self.sidebar, text="+ Нова група", height=36, corner_radius=10,
                                  fg_color="#1E2A5E", hover_color="#2A3A7A",
                                  font=CTkFont(size=13, weight="bold"),
                                  command=self.open_create_group_dialog)
        new_group_btn.pack(pady=(0, 6), padx=15, fill="x")

        self.search_entry = CTkEntry(self.sidebar, placeholder_text="🔍 Пошук або нік...", height=40,
                                     corner_radius=10, fg_color="#252525", border_width=0)
        self.search_entry.pack(pady=(0, 8), padx=15, fill="x")
        self.search_entry.bind("<KeyRelease>", self.filter_chats)

        self.scrollable_chats = CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.scrollable_chats.pack(fill="both", expand=True, padx=5, pady=5)

    def filter_chats(self, event):
        query = self.search_entry.get().lower().strip()
        found = False
        for name, frame in self.all_users_buttons.items():
            if query in name.lower():
                frame.pack(fill="x", pady=2, padx=5)
                found = True
            else:
                frame.pack_forget()
        if not found and query != "":
            if not hasattr(self, "add_new_btn"):
                self.add_new_btn = CTkButton(self.sidebar, text="", fg_color=self.accent_color,
                                             command=lambda: self.add_user(self.search_entry.get()))
            self.add_new_btn.configure(text=f"Додати: {query[:15]}...")
            self.add_new_btn.pack(pady=5, padx=15, fill="x")
        elif hasattr(self, "add_new_btn"):
            self.add_new_btn.pack_forget()

    def setup_chat_area(self):
        self.chat_container = CTkFrame(self, fg_color="transparent")
        self.chat_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.chat_container.grid_rowconfigure(1, weight=1)
        self.chat_container.grid_columnconfigure(0, weight=1)

        self.chat_header = CTkFrame(self.chat_container, height=65, fg_color="#1E1E1E", corner_radius=15)
        self.chat_header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.current_chat_label = CTkLabel(self.chat_header, text="Оберіть діалог", font=("Inter", 18, "bold"))
        self.current_chat_label.pack(side="left", padx=25, pady=18)

        self.messages_view = CTkScrollableFrame(self.chat_container, fg_color="#161616", corner_radius=15)
        self.messages_view.grid(row=1, column=0, sticky="nsew")

        self.input_frame = CTkFrame(self.chat_container, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        self.entry_message = CTkEntry(self.input_frame, height=55, corner_radius=15, font=("Inter", 14),
                                      border_width=2, border_color="#2A2A2A")
        self.entry_message.pack(side="left", fill="x", expand=True, padx=(0, 15))
        self.entry_message.bind("<Return>", lambda e: self.send_message())
        self.send_btn = CTkButton(self.input_frame, text="➞", width=60, height=55, corner_radius=15,
                                  fg_color=self.accent_color, font=("Inter", 20, "bold"), command=self.send_message)
        self.send_btn.pack(side="right")

    def add_user(self, username, is_notes=False, is_group=False):
        if username in self.all_users_buttons:
            return
        if username not in self.chats_history:
            self.chats_history[username] = []

        chat_frame = CTkFrame(self.scrollable_chats, fg_color="transparent", height=70, corner_radius=12)
        chat_frame.pack(fill="x", pady=4, padx=5)
        chat_frame.pack_propagate(False)

        # Icon / avatar
        if is_notes:
            icon_label = CTkLabel(chat_frame, text="📝", font=("Inter", 20), width=40)
        elif is_group:
            icon_label = CTkLabel(chat_frame, text="👥", font=("Inter", 20), width=40)
        elif username in self.user_avatars:
            icon_label = CTkLabel(chat_frame, text="", image=self.user_avatars[username], width=40)
        else:
            icon_label = CTkLabel(chat_frame, text="👤", font=("Inter", 20), width=40)
        icon_label.pack(side="left", padx=10)

        info_frame = CTkFrame(chat_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", pady=10)
        name_label = CTkLabel(info_frame, text=username, font=("Inter", 14, "bold"), anchor="w")
        name_label.pack(fill="x")

        if is_group:
            members = self.group_members.get(username, [])
            sub = f"Група · {len(members)} уч."
        else:
            sub = "Натисніть, щоб почати"
        status_label = CTkLabel(info_frame, text=sub, font=("Inter", 11), text_color="gray", anchor="w")
        status_label.pack(fill="x")

        click_widgets = [chat_frame, icon_label, info_frame, name_label, status_label]

        if not is_notes and not is_group:
            online_dot = CTkLabel(chat_frame, text="●", text_color="#00C853", font=("Inter", 18, "bold"))
            online_dot.pack(side="right", padx=15)
            click_widgets.append(online_dot)
            self.user_avatar_labels[username] = icon_label

        for widget in click_widgets:
            widget.bind("<Button-1>", lambda e, u=username: self.open_chat(u))

        self.all_users_buttons[username] = chat_frame
        if hasattr(self, "add_new_btn"):
            self.add_new_btn.pack_forget()

    def open_chat(self, username):
        self.active_chat = username
        is_group = username in self.group_members
        if is_group:
            members = self.group_members.get(username, [])
            self.current_chat_label.configure(text=f"👥 {username}  ({len(members)} уч.)")
        else:
            self.current_chat_label.configure(text=f"Чат: {username}")
        for name, frame in self.all_users_buttons.items():
            frame.configure(fg_color="#2A2A2A" if name == username else "transparent")
        self.update_input_state()
        self.refresh_messages()
    def display_message(self, sender, text, index, show_sender_name=False):
        container = CTkFrame(self.messages_view, fg_color="transparent")
        container.pack(fill="x", pady=8, padx=15)

        if sender == "System":
            bubble = CTkLabel(container, text=text, fg_color="#333333", corner_radius=18,
                              padx=20, pady=12, wraplength=700, font=("Inter", 14),
                              justify="center", text_color="gray")
            bubble.pack(anchor="center")
            bubble.bind("<Button-3>", lambda event, idx=index: self.show_context_menu(event, idx))
            return

        is_me = (sender == "Me")
        align = "e" if is_me else "w"
        color = self.accent_color if is_me else "#2A2A2A"

        if show_sender_name and not is_me:
            name_lbl = CTkLabel(container, text=sender, font=("Inter", 11, "bold"),
                                text_color="#8899CC", anchor="w")
            name_lbl.pack(anchor="w", padx=4, pady=(0, 2))

        bubble = CTkLabel(container, text=text, fg_color=color, corner_radius=18,
                          padx=20, pady=12, wraplength=700, font=("Inter", 14),
                          justify="left", text_color=None)
        bubble.pack(anchor=align)
        bubble.bind("<Button-3>", lambda event, idx=index: self.show_context_menu(event, idx))

    def _scroll_to_bottom(self):
        try:
            self.messages_view._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def send_message(self):
        if not self.active_chat or not self.entry_message.get().strip():
            return
        text = self.entry_message.get().strip()
        self.entry_message.delete(0, "end")

        if self.active_chat not in self.chats_history:
            self.chats_history[self.active_chat] = []

        is_group = self.active_chat in self.group_members

        if self.active_chat != "Нотатки" and self.client_socket:
            try:
                if is_group:
                    self.client_socket.send(f"GROUP_MSG:{self.active_chat}:{text}\n".encode('utf-8'))
                else:
                    self.client_socket.send(f"SEND_TO:{self.active_chat}:{text}\n".encode('utf-8'))
                    self.chats_history[self.active_chat].append(("Me", text))
                    self.display_message("Me", text, len(self.chats_history[self.active_chat]) - 1)
                    self.after(10, self._scroll_to_bottom)
            except Exception:
                self.chats_history[self.active_chat].append(("System", "Не вдалося відправити"))
                self.refresh_messages()
        else:
            self.chats_history[self.active_chat].append(("Me", text))
            self.display_message("Me", text, len(self.chats_history[self.active_chat]) - 1)
            self.after(10, self._scroll_to_bottom)

    def update_input_state(self):
        state = "normal" if self.active_chat else "disabled"
        self.entry_message.configure(state=state)
        self.send_btn.configure(state=state)

    def refresh_messages(self):
        for child in self.messages_view.winfo_children():
            child.destroy()
        if not self.active_chat or self.active_chat not in self.chats_history:
            return
        is_group = self.active_chat in self.group_members
        history = self.chats_history[self.active_chat]
        for i in range(len(history)):
            sender, text = history[i]
            self.display_message(sender, text, i, show_sender_name=is_group)
        self.after(10, self._scroll_to_bottom)

    def receive_messages(self):
        buffer = ""
        while True:
            try:
                if not self.client_socket:
                    break
                chunk = self.client_socket.recv(4096).decode('utf-8')
                if not chunk:
                    break
                buffer += chunk
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self.after(0, self.process_received_data, line)
            except Exception:
                break

    def process_received_data(self, data):
        if data.startswith("NEW_USER:"):
            username = data[9:].strip()
            if username and username != self.current_user and username not in self.all_users_buttons:
                if username not in self.known_online_users:
                    self.known_online_users.append(username)
                self.add_user(username)
                if username not in self.chats_history:
                    self.chats_history[username] = []
                self.chats_history[username].append(("System", f"{username} приєднався до сервера"))
                if self.active_chat == username:
                    self.refresh_messages()

        elif data.startswith("USER_LIST:"):
            try:
                usernames = data[10:].strip().split(',')
                for u in usernames:
                    u = u.strip()
                    if u and u != self.current_user:
                        if u not in self.known_online_users:
                            self.known_online_users.append(u)
                        if u not in self.all_users_buttons:
                            self.add_user(u)
            except:
                pass

        elif data.startswith("AVATAR_OF:"):
            try:
                parts = data.split(":", 2)
                if len(parts) == 3:
                    self.apply_avatar(parts[1], parts[2])
            except:
                pass

        elif data.startswith("NEW_USER_AVATAR:"):
            try:
                parts = data.split(":", 2)
                if len(parts) == 3:
                    self.apply_avatar(parts[1], parts[2])
            except:
                pass

        elif data.startswith("USER_LEFT:"):
            try:
                username = data[10:].strip()
                if username in self.known_online_users:
                    self.known_online_users.remove(username)
                if username in self.all_users_buttons:
                    frame = self.all_users_buttons.pop(username)
                    frame.pack_forget()
                    self.user_avatar_labels.pop(username, None)
                    self.user_avatars.pop(username, None)
                    if self.active_chat == username:
                        self.active_chat = None
                        self.current_chat_label.configure(text="Оберіть діалог")
                        self.update_input_state()
            except:
                pass

        elif data.startswith("MESSAGE_FROM:"):
            try:
                _, from_user, text = data.split(":", 2)
                if from_user not in self.chats_history:
                    self.chats_history[from_user] = []
                self.chats_history[from_user].append((from_user, text))
                if from_user not in self.all_users_buttons and from_user != self.current_user:
                    self.add_user(from_user)
                if self.active_chat == from_user:
                    self.display_message(from_user, text, len(self.chats_history[from_user]) - 1)
                    self.after(10, self._scroll_to_bottom)
            except Exception:
                pass
        elif data.startswith("GROUP_CREATED:"):
            try:
                parts = data.split(":", 3)
                if len(parts) == 4:
                    gname, creator, members_str = parts[1], parts[2], parts[3]
                    members = [m.strip() for m in members_str.split(",") if m.strip()]
                    self.group_members[gname] = members
                    if gname not in self.chats_history:
                        self.chats_history[gname] = []
                    if gname not in self.all_users_buttons:
                        self.add_user(gname, is_group=True)
                        msg = f"Групу '{gname}' створено користувачем {creator}"
                        self.chats_history[gname].append(("System", msg))
                    if self.active_chat == gname:
                        self.refresh_messages()
            except Exception:
                pass

        elif data.startswith("GROUP_MSG_FROM:"):
            try:
                parts = data.split(":", 3)
                if len(parts) == 4:
                    gname, sender, text = parts[1], parts[2], parts[3]
                    if gname not in self.chats_history:
                        self.chats_history[gname] = []
                    display_sender = "Me" if sender == self.current_user else sender
                    self.chats_history[gname].append((display_sender, text))
                    if self.active_chat == gname:
                        self.display_message(display_sender, text,
                                             len(self.chats_history[gname]) - 1,
                                             show_sender_name=True)
                        self.after(10, self._scroll_to_bottom)
            except Exception:
                pass

    def show_context_menu(self, event, index):
        if not self.active_chat:
            return
        history = self.chats_history.get(self.active_chat, [])
        if index >= len(history):
            return
        _, msg_text = history[index]
        self.clipboard_clear()
        self.clipboard_append(msg_text)

    def open_create_group_dialog(self):
        dialog = CTkToplevel(self)
        dialog.title("Нова група")
        dialog.geometry("420x600")
        dialog.configure(fg_color="#121212")
        dialog.resizable(False, False)
        dialog.grab_set()

        CTkLabel(dialog, text="Створити групу", font=CTkFont(size=22, weight="bold"),
                 text_color="#FFFFFF").pack(pady=(28, 4))
        CTkLabel(dialog, text="Оберіть учасників та назву", font=CTkFont(size=13),
                 text_color="#888888").pack(pady=(0, 18))
        name_card = CTkFrame(dialog, fg_color="#1E1E1E", corner_radius=12)
        name_card.pack(fill="x", padx=25, pady=(0, 14))
        CTkLabel(name_card, text="Назва групи", font=CTkFont(size=12, weight="bold"),
                 text_color="#888888").pack(anchor="w", padx=14, pady=(12, 2))
        name_entry = CTkEntry(name_card, placeholder_text="fids",
                              height=40, corner_radius=8, fg_color="#2A2A2A",
                              border_width=0, font=CTkFont(size=14))
        name_entry.pack(fill="x", padx=14, pady=(0, 12))

        CTkLabel(dialog, text="Учасники онлайн", font=CTkFont(size=13, weight="bold"),
                 text_color="#CCCCCC").pack(anchor="w", padx=25, pady=(0, 6))

        members_frame = CTkScrollableFrame(dialog, fg_color="#1A1A1A", corner_radius=12, height=200)
        members_frame.pack(fill="x", padx=25, pady=(0, 10))

        selected_vars = {}
        online_others = [u for u in self.known_online_users if u != self.current_user]

        if online_others:
            for user in online_others:
                var = tk.BooleanVar(value=False)
                selected_vars[user] = var

                row = CTkFrame(members_frame, fg_color="#222222", height=52, corner_radius=10)
                row.pack(fill="x", pady=3)
                row.pack_propagate(False)

                if user in self.user_avatars:
                    av_lbl = CTkLabel(row, text="", image=self.user_avatars[user], width=40)
                else:
                    av_lbl = CTkLabel(row, text="👤", font=CTkFont(size=18), width=40)
                av_lbl.pack(side="left", padx=(10, 6))

                name_lbl = CTkLabel(row, text=user, font=CTkFont(size=14, weight="bold"), anchor="w")
                name_lbl.pack(side="left", fill="x", expand=True)

                def on_row_click(e, v=var, r=row):
                    v.set(not v.get())
                    r.configure(fg_color="#2A3A5A" if v.get() else "#222222")

                cb = CTkCheckBox(row, text="", variable=var, width=28, height=28,
                                 fg_color=self.accent_color, hover_color="#5570FF",
                                 command=lambda v=var, r=row: r.configure(fg_color="#2A3A5A" if v.get() else "#222222"))
                cb.pack(side="right", padx=14)

                for w in [row, av_lbl, name_lbl]:
                    w.bind("<Button-1>", lambda e, v=var, r=row: on_row_click(e, v, r))
        else:
            CTkLabel(members_frame, text="Немає інших користувачів онлайн",
                     font=CTkFont(size=13), text_color="#666666").pack(pady=20)

        status_lbl = CTkLabel(dialog, text="", font=CTkFont(size=12), text_color="#FF5252")
        status_lbl.pack(pady=(5, 5))
        def do_create():
            gname = name_entry.get().strip()
            if not gname:
                status_lbl.configure(text="Введіть назву групи!")
                return
            chosen = [u for u, v in selected_vars.items() if v.get()]
            if not chosen:
                status_lbl.configure(text="Оберіть хоча б одного учасника!")
                return
            if self.client_socket:
                members_str = ",".join(chosen)
                self.client_socket.send(f"CREATE_GROUP:{gname}:{members_str}\n".encode('utf-8'))
            dialog.destroy()
        btn_create_group = CTkButton(
            dialog,
            text="Створити групу", 
            height=50, corner_radius=12,
            fg_color=self.accent_color, 
            hover_color="#5570FF",
            font=CTkFont(size=15, weight="bold"),
            command=do_create)
        btn_create_group.pack(side="bottom", fill="x", padx=25, pady=(0, 25))
    def open_profile(self):
        profile_win = CTkToplevel(self)
        profile_win.title("Профіль")
        profile_win.geometry("400x500")
        profile_win.configure(fg_color="#0F0F0F")
        profile_win.resizable(False, False)
        profile_win.grab_set()

        banner = CTkFrame(profile_win, fg_color="#1A1A2E", corner_radius=0, height=160)
        banner.pack(fill="x")
        banner.pack_propagate(False)

        self._new_avatar_path = None
        self._profile_avatar_label = None

        def render_avatar_preview(path=None):
            try:
                if path:
                    img = Image.open(path).convert("RGB")
                else:
                    img = Image.new('RGB', (80, 80), color=self.accent_color)
                img = img.resize((80, 80), Image.Resampling.LANCZOS)
                circle = self.make_circle(img, (80, 80))
                preview_img = CTkImage(circle, size=(80, 80))
                if self._profile_avatar_label:
                    self._profile_avatar_label.configure(image=preview_img, text="")
                    self._profile_avatar_label._preview_img_ref = preview_img
            except:
                pass

        def choose_new_avatar():
            path = fd.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.jpeg")])
            if path:
                self._new_avatar_path = path
                render_avatar_preview(path)

        av_btn = CTkButton(banner, text="", width=80, height=80, corner_radius=40,
                           fg_color="#2A2A4A", hover_color="#3A3A6A",
                           command=choose_new_avatar)
        av_btn.place(relx=0.5, rely=0.45, anchor="center")
        self._profile_avatar_label = av_btn
        render_avatar_preview(self.avatar_path)

        CTkLabel(banner, text="Натисніть на аватар, щоб змінити",
                 font=CTkFont(size=11), text_color="#555577").place(relx=0.5, rely=0.88, anchor="center")

        # ---- Fields card ----
        card = CTkFrame(profile_win, fg_color="#1A1A1A", corner_radius=16)
        card.pack(fill="x", padx=24, pady=(18, 0))

        def field_row(parent, label, initial, placeholder=""):
            CTkLabel(parent, text=label, font=CTkFont(size=11, weight="bold"),
                     text_color="#666666").pack(anchor="w", padx=16, pady=(12, 2))
            e = CTkEntry(parent, height=40, corner_radius=8, font=CTkFont(size=14),
                         fg_color="#252525", border_width=0, placeholder_text=placeholder)
            e.insert(0, initial)
            e.pack(fill="x", padx=16, pady=(0, 4))
            return e

        nick_entry = field_row(card, "НІКНЕЙМ", self.current_user)
        desc_entry = field_row(card, "ОПИС", self.user_description, "Розкажіть про себе...")

        # Divider
        CTkFrame(card, fg_color="#2A2A2A", height=1).pack(fill="x", padx=16, pady=6)

        # Online status row
        status_row = CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(4, 14))
        CTkLabel(status_row, text="●", text_color="#00C853", font=CTkFont(size=16)).pack(side="left", padx=(0, 6))
        CTkLabel(status_row, text="Онлайн", font=CTkFont(size=13), text_color="#AAAAAA").pack(side="left")

        # ---- Save button ----
        def save_profile():
            new_nick = nick_entry.get().strip()
            new_desc = desc_entry.get().strip()

            if new_nick and new_nick != self.current_user:
                self.current_user = new_nick
                if hasattr(self, "profile_name_label"):
                    self.profile_name_label.configure(text=new_nick)
                if self.client_socket:
                    try:
                        self.client_socket.send(f"UPDATE_NICK:{new_nick}\n".encode('utf-8'))
                    except:
                        pass

            self.user_description = new_desc if new_desc else "Немає опису"

            if self._new_avatar_path and self.client_socket:
                try:
                    img = Image.open(self._new_avatar_path).convert("RGB")
                    img = img.resize((45, 45), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=75)
                    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                    self.client_socket.send(f"AVATAR:{self.current_user}:{b64}\n".encode('utf-8'))
                    self.avatar_path = self._new_avatar_path
                except:
                    pass

            profile_win.destroy()

        CTkButton(profile_win, text="Зберегти зміни", height=48, corner_radius=12,
                  fg_color=self.accent_color, hover_color="#5570FF",
                  font=CTkFont(size=15, weight="bold"),
                  command=save_profile).pack(fill="x", padx=24, pady=20)


if __name__ == "__main__":
    app = Autenfig()
    app.mainloop()

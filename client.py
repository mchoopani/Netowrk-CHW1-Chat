import socket
import threading
from abc import ABC, abstractmethod
from queue import Queue
from time import sleep

from consts import PORT, PUBLIC_CHATROOM_ID, UDP_PORT
from db import Database
from message import MessageFactory, PrivateMessage, Packet, JoinChatroom, LeaveChatroom, PublicMessage, LoginPacket, \
    Response, ResponseStatus, StateMessage, ClientState, GroupMessage, JoinGroup, PVChatHistory
from database import FileSystemDatabase


class MessageHandler:
    def __init__(self, database: Database, response_queue: Queue):
        self.db = database
        self.response_queue = response_queue

    def handle(self, message: Packet):
        if isinstance(message, PrivateMessage) or isinstance(message, PublicMessage) or isinstance(message, GroupMessage):
            if isinstance(message, PublicMessage):
                key = f'channel:{message.chatroom_id}'
            elif isinstance(message, GroupMessage):
                key = f'group:{message.group_id}'
            else:
                key = message.sender_username
            # FIXME: this is not atomic!
            messages = self.db.get(key) or []
            messages.append(message)
            self.db.set(key, messages)
        elif isinstance(message, Response):
            self.response_queue.put(message)


db = Database.get_instance()
response_queue = Queue()
handler = MessageHandler(database=db, response_queue=response_queue)
_database = FileSystemDatabase()


def get_messages(tcp_sock):
    def func():
        while True:
            mes = MessageFactory.new_message(tcp_sock.recv(1024).decode())
            handler.handle(mes)

    return func


def print_online_users(udp_sock):
    udp_sock.sendto("list".encode('utf-8'), UDP_ADDR)
    response, _ = udp_sock.recvfrom(1024)
    print(f"online users:\n{response.decode('utf-8')}")


class CommandState(ABC):
    def __init__(self, sck: socket.socket, udp_sock: socket.socket, commander: str):
        self.sock = sck
        self.udp_sock = udp_sock
        self.commander = commander

    @abstractmethod
    def obey_and_go_next(self):
        raise NotImplementedError()


class MenuState(CommandState):
    def obey_and_go_next(self):
        menu = """
        1) start a new chat
        2) show your chat list
        3) open chat room
        4) list online clients
        5) change Availability
        6) group chat
        """
        print(menu)
        cmd = input("press any key: ")
        if cmd == '1':
            return NewChatState(self.sock, self.udp_sock, self.commander)
        elif cmd == '2':
            return ChatListState(self.sock, self.udp_sock, self.commander)
        elif cmd == '3':
            return ChatroomState(self.sock, self.udp_sock, self.commander, PUBLIC_CHATROOM_ID)
        elif cmd == '4':
            print_online_users(self.udp_sock)
            return self.obey_and_go_next()
        elif cmd == '5':
            return AvailabilityState(self.sock, self.udp_sock, self.commander)
        elif cmd == '6':
            group_id = input("Enter the group ID: ")
            if not _database.check_group_id(group_id):
                print_online_users(self.udp_sock)
                participants_str = input("Enter the usernames (comma-separated) to invite to the group: ")
                participants = [participant.strip() for participant in participants_str.split(",")]
                message = JoinGroup(self.commander, group_id, participants)
                self.sock.send(str(message).encode('utf-8'))
                _database.save_group_id(group_id)
            return GroupChatState(self.sock, self.udp_sock, self.commander, group_id)
        elif cmd == '-1':
            return None
        else:
            return self.obey_and_go_next()


class NewChatState(CommandState):
    def obey_and_go_next(self) -> CommandState:
        receiver = input('enter a username to say hello: ')
        message = PrivateMessage(self.commander, f'hello {receiver}', receiver)
        self.sock.send(str(message).encode('utf-8'))
        response = response_queue.get()
        if not isinstance(response, Response):
            print("Invalid response received.")
            return MenuState(self.sock, self.udp_sock, self.commander)
        elif response.status != ResponseStatus.OK:
            print("saying hello failed: ", response.content)
            return MenuState(self.sock, self.udp_sock, self.commander)

        messages = db.get(message.receiver_username) or []
        messages.append(message)
        db.set(message.receiver_username, messages)

        return MenuState(self.sock, self.udp_sock, self.commander)


class ChatListState(CommandState):
    def obey_and_go_next(self):
        usernames = list(filter(lambda key: not key.startswith('chatroom:'), db.get_all_keys()))
        console_output = ""
        for i, un in enumerate(usernames):
            console_output += f"""
            {i}) {un}
            """
        print(console_output)
        k = input("enter your friend to chat or quit to back: ")
        if k == 'quit':
            return MenuState(self.sock, self.udp_sock, self.commander)
        target = list(usernames)[int(k)]
        return ChatPage(self.sock, self.udp_sock, self.commander, target)


class ChatPage(CommandState):
    def __init__(self, sck: socket.socket, udp_sock: socket.socket, commander: str, friend_username: str):
        super().__init__(sck, udp_sock, commander)
        self.friend_username = friend_username
        self.closed = False

    def get_new_messages(self):
        prev_len = len(db.get(self.friend_username))
        while True:
            if self.closed:
                return
            sleep(.1)
            new_messages = db.get(self.friend_username)
            if len(new_messages) > prev_len:
                prev_len = len(new_messages)
                yield new_messages[-1]

    def print_new_messages(self):
        try:
            for mes in self.get_new_messages():
                if mes.sender_username == self.commander:
                    continue
                print(mes.get_human_readable_output())
        except Exception as e:
            print(e)

    def obey_and_go_next(self):
        chat_messages = db.get(self.friend_username) or []
        print("\n".join(list(map(lambda ms: ms.get_human_readable_output(), chat_messages))))
        threading.Thread(target=self.print_new_messages).start()
        while True:
            msg = input()
            if msg == 'quit':
                self.closed = True
                return ChatListState(self.sock, self.udp_sock, self.commander)
            message = PrivateMessage(self.commander, msg, self.friend_username)

            self.sock.send(str(message).encode('utf-8'))
            response = response_queue.get()
            if not isinstance(response, Response):
                print("Invalid response received.")
                return ChatListState(self.sock, self.udp_sock, self.commander)
            elif response.status != ResponseStatus.OK:
                print("saying hello failed: ", response.content)
                return ChatListState(self.sock, self.udp_sock, self.commander, )

            messages = db.get(message.receiver_username) or []
            messages.append(message)
            db.set(message.receiver_username, messages)


class ChatroomState(CommandState):
    def __init__(self, sck: socket.socket, udp_sock: socket.socket, commander: str, chatroom_id: str):
        super().__init__(sck, udp_sock, commander)
        self.chatroom_id = chatroom_id
        self.closed = False
        history_messages = _database.get_public_messages(self.chatroom_id)
        for message in history_messages:
            print(message.get_human_readable_output())

    def get_db_key(self):
        return f'channel:{self.chatroom_id}'

    def get_new_messages(self):  # FIXME: we have duplicate codes!
        prev_len = len(db.get(self.get_db_key()))
        while True:
            if self.closed:
                raise Exception('chat page state is closed.')
            sleep(.1)
            new_messages = db.get(self.get_db_key())
            if len(new_messages) > prev_len:
                prev_len = len(new_messages)
                yield new_messages[-1]

    def print_new_messages(self):
        try:
            for mes in self.get_new_messages():
                if mes.sender_username == self.commander:
                    continue
                print(mes.get_human_readable_output())
        except Exception as e:
            print(e)

    def obey_and_go_next(self):
        join = JoinChatroom(self.commander, self.chatroom_id)
        self.sock.send(str(join).encode('utf-8'))

        chat_messages = db.get(self.get_db_key()) or []
        print("\n".join(list(map(lambda mess: mess.get_human_readable_output(), chat_messages))))
        threading.Thread(target=self.print_new_messages).start()

        while True:
            msg = input()
            if msg == 'quit':
                self.closed = True
                break

            message = PublicMessage(self.commander, msg, self.chatroom_id)

            self.sock.send(str(message).encode('utf-8'))
            messages = db.get(self.get_db_key()) or []
            messages.append(message)
            db.set(self.get_db_key(), messages)

        leave = LeaveChatroom(self.commander, self.chatroom_id)
        self.sock.send(str(leave).encode('utf-8'))
        return MenuState(self.sock, self.udp_sock, self.commander)


class GroupChatState(CommandState):
    def __init__(self, sck: socket.socket, udp_sock: socket.socket, commander: str, group_id: str):
        super().__init__(sck, udp_sock, commander)
        self.group_id = group_id
        self.closed = False
        history_messages = _database.get_group_messages(self.group_id)
        for message in history_messages:
            print(message.get_human_readable_output())

    def get_db_key(self):
        return f'group:{self.group_id}'

    def get_new_messages(self):  # FIXME: we have duplicate codes!
        prev_len = len(db.get(self.get_db_key()))
        while True:
            if self.closed:
                raise Exception('group chat page state is closed.')
            sleep(.1)
            new_messages = db.get(self.get_db_key())
            if len(new_messages) > prev_len:
                prev_len = len(new_messages)
                yield new_messages[-1]

    def print_new_messages(self):
        try:
            for mes in self.get_new_messages():
                if mes.sender_username == self.commander:
                    continue
                print(mes.get_human_readable_output())
        except Exception as e:
            print(e)

    def obey_and_go_next(self):
        chat_messages = db.get(self.get_db_key()) or []
        print("\n".join(list(map(lambda mess: mess.get_human_readable_output(), chat_messages))))
        threading.Thread(target=self.print_new_messages).start()

        while True:
            msg = input()
            if msg == 'quit':
                self.closed = True
                break

            message = GroupMessage(self.commander, msg, self.group_id)

            self.sock.send(str(message).encode('utf-8'))
            messages = db.get(self.get_db_key()) or []
            messages.append(message)
            db.set(self.get_db_key(), messages)

        return MenuState(self.sock, self.udp_sock, self.commander)


class ListClientsState(CommandState):

    def obey_and_go_next(self):
        self.udp_sock.sendto("list".encode('utf-8'), UDP_ADDR)
        response, _ = self.udp_sock.recvfrom(1024)
        print(f"online users:\n{response.decode('utf-8')}")
        return MenuState(self.sock, self.udp_sock, self.commander)


class AvailabilityState(CommandState):
    def obey_and_go_next(self):
        status = input('enter your state as BUSY or AVAILABLE: ')
        message = StateMessage(self.commander, getattr(ClientState, status))
        self.sock.send(str(message).encode('utf-8'))
        return MenuState(self.sock, self.udp_sock, self.commander)


sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('127.0.0.1', PORT))

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
UDP_ADDR = ('127.0.0.1', UDP_PORT)

while True:
    username = input("enter your username or enter list to get online users: ")
    if username == 'list':
        print_online_users(udp_socket)
    else:
        break

while True:
    password = input("enter password: ")
    sock.send(str(LoginPacket(username, password)).encode("utf-8"))
    response: Packet = MessageFactory.new_message(sock.recv(1024).decode("utf-8"))
    if isinstance(response, Response):
        print(response.content)
        if response.status != ResponseStatus.OK:
            continue
        # get history of private messages and sync local database
        response: Packet = MessageFactory.new_message(sock.recv(1024).decode("utf-8"))
        if isinstance(response, PVChatHistory):
            for message in PVChatHistory.get_messages(response.content):
                friend_username = message.sender_username if message.receiver_username == username else message.receiver_username
                messages = db.get(friend_username) or []
                messages.append(message)
                db.set(friend_username, messages)
        break

threading.Thread(target=get_messages(sock)).start()
state = MenuState(sock, udp_socket, username)

try:
    while True:
        next_state = state.obey_and_go_next()
        if not next_state:
            break
        state = next_state
finally:
    sock.close()
    udp_socket.close()

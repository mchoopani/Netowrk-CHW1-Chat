import socket
import threading

from consts import PORT, UDP_PORT, PUBLIC_CHATROOM_ID
from database import DatabaseInterface, PasswordIsWrong, FileSystemDatabase
from exceptions import DisconnectException
from message import MessageFactory, PrivateMessage, Packet, JoinChatroom, LeaveChatroom, PublicMessage, LoginPacket, \
    Response, ResponseStatus, ClientState, StateMessage, GroupMessage, JoinGroup

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('0.0.0.0', PORT))
sock.listen(4)

udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.bind(('0.0.0.0', UDP_PORT))


class Handler:
    def __init__(self, database: DatabaseInterface):
        self.clients = {}
        self.chatroom_participants = {
            PUBLIC_CHATROOM_ID: []
        }
        self.group_participants = {}
        self.database = database

    def add_client(self, client: "Client"):
        self.clients[client.username] = client

    def add_to_group(self, group_id: str, client: "Client"):
        participants = self.group_participants.get(group_id, [])
        participants.append(client.username)
        self.group_participants[group_id] = participants

    def add_to_chatroom(self, chatroom_id: str, client: "Client"):
        participants = self.chatroom_participants.get(chatroom_id, [])
        participants.append(client)
        self.chatroom_participants[chatroom_id] = participants

    def leave_chatroom(self, chatroom_id: str, client: "Client"):
        participants = self.chatroom_participants.get(chatroom_id, [])
        participants.remove(client)

    def remove_client(self, username: str):
        try:
            del self.clients[username]
        except:
            pass

    def check_availability(self, receiver: str):
        receiver_client = self.clients.get(receiver)
        return receiver_client and receiver_client.state == ClientState.AVAILABLE

    def dispatch(self, message: Packet):
        if isinstance(message, PrivateMessage):
            receiver: Client = self.clients[message.receiver_username]
            if self.check_availability(message.receiver_username):
                receiver.conn.send(str(message).encode("utf-8"))
                _database.save_message(message)
                self.dispatch(Response(message.sender_username, 'message sent.', ResponseStatus.OK))
            else:
                self.dispatch(
                    Response(message.sender_username, f"{message.receiver_username} is busy.", ResponseStatus.FAIL)
                )
        elif isinstance(message, StateMessage):
            self.clients[message.sender_username].state = message.state
        elif isinstance(message, JoinChatroom):
            self.dispatch(
                PublicMessage(message.sender_username, f'I have joined.', message.chatroom_id)
            )
            self.add_to_chatroom(message.chatroom_id, self.clients[message.sender_username])
            _database.save_message(message)
        elif isinstance(message, LeaveChatroom):
            self.dispatch(
                PublicMessage(message.sender_username, f'I have left.', message.chatroom_id)
            )
            self.leave_chatroom(message.chatroom_id, self.clients[message.sender_username])
            _database.save_message(message)
        elif isinstance(message, PublicMessage):
            for client in self.chatroom_participants[message.chatroom_id]:
                client.conn.send(str(message).encode("utf-8"))
                _database.save_message(message)
        elif isinstance(message, JoinGroup):
            for participant in message.participants:
                self.add_to_group(participant, self.clients[participant])

            self.dispatch(
                GroupMessage(message.sender_username, f'I have joined.', message.group_id)
            )
            _database.save_message(message)
        elif isinstance(message, GroupMessage):
            participants = self.group_participants.get(message.group_id, [])
            for participant_username in participants:
                participant_client = self.clients.get(participant_username)
                if participant_client:
                    participant_client.conn.send(str(message).encode("utf-8"))
            _database.save_message(message)
        elif isinstance(message, Response):
            receiver: Client = self.clients[message.receiver]
            receiver.conn.send(str(message).encode("utf-8"))
        elif isinstance(message, StateMessage):
            self.clients[message.sender_username].state = message.state
        else:
            raise Exception("unknown message." + str(message))


_database = FileSystemDatabase()
handler = Handler(_database)


class Client:
    def __init__(self, username: str, address: str, conn: socket.socket):
        self.username = username
        self.address = address
        self.conn = conn
        self.state = ClientState.AVAILABLE

    def serve(self):
        while True:
            try:
                client_in = self.conn.recv(1024).decode()
                if len(client_in) == 0:
                    raise DisconnectException()
                message = MessageFactory.new_message(client_in)
                if self.state == ClientState.BUSY:
                    continue
            except DisconnectException:
                handler.remove_client(self.username)
                self.conn.close()
                print(f'client {self.username} disconnected')
                return

            handler.dispatch(message)


def handle_udp_requests():
    while True:
        message, address = udp_sock.recvfrom(1024)
        message = message.decode('utf-8')
        response = "unknown command."
        if message == 'list':
            response = "\n".join(handler.clients)
        udp_sock.sendto(response.encode('utf-8'), address)


def add_client(conn, address):
    def func():
        mes = MessageFactory.new_message(conn.recv(1024).decode())
        if not isinstance(mes, LoginPacket):
            conn.close()
            return
        client = Client(mes.sender_username, address, conn)
        handler.add_client(client)
        try:
            _, exist = _database.get_user_if_exist(mes.sender_username, mes.password)
            if not exist:
                _database.save_user(mes.sender_username, mes.password)
            handler.dispatch(Response(mes.sender_username, "you are logged in.", ResponseStatus.OK))
        except PasswordIsWrong:
            handler.dispatch(Response(mes.sender_username, "your password is wrong", ResponseStatus.FAIL))
            func()
            return

        threading.Thread(target=client.serve).start()
        print(f"user {mes.sender_username} connected.")

    return func


def accept_clients():
    while True:
        conn, address = sock.accept()
        threading.Thread(target=add_client(conn, address)).start()


udp_thread = threading.Thread(target=handle_udp_requests)
udp_thread.start()
tcp_thread = threading.Thread(target=accept_clients)
tcp_thread.start()
print("server is running.")

try:
    tcp_thread.join()
    udp_thread.join()
except KeyboardInterrupt:
    for _, client in handler.clients.items():
        client.conn.close()
    udp_sock.close()
    sock.close()

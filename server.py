import socket
import threading

from consts import PORT, UDP_PORT, PUBLIC_CHATROOM_ID
from message import MessageFactory, PrivateMessage, Packet, JoinChatroom, LeaveChatroom, PublicMessage

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind(('0.0.0.0', PORT))
sock.listen(4)

udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.bind(('0.0.0.0', UDP_PORT))


class Handler:
    def __init__(self):
        self.clients = {}
        self.chatroom_participants = {
            PUBLIC_CHATROOM_ID: []
        }

    def add_client(self, client: "Client"):
        self.clients[client.username] = client

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

    def dispatch(self, message: Packet):
        if isinstance(message, PrivateMessage):
            receiver: Client = self.clients[message.receiver_username]
            receiver.conn.send(str(message).encode("utf-8"))
        elif isinstance(message, JoinChatroom):
            self.dispatch(
                PublicMessage(message.sender_username, f'I have joined.', message.chatroom_id)
            )
            self.add_to_chatroom(message.chatroom_id, self.clients[message.sender_username])
        elif isinstance(message, LeaveChatroom):
            self.dispatch(
                PublicMessage(message.sender_username, f'I have left.', message.chatroom_id)
            )
            self.leave_chatroom(message.chatroom_id, self.clients[message.sender_username])
        elif isinstance(message, PublicMessage):
            for client in self.chatroom_participants[message.chatroom_id]:
                client.conn.send(str(message).encode("utf-8"))
        else:
            raise Exception("unknown message." + str(message))


handler = Handler()


class Client:
    def __init__(self, username: str, address: str, conn: socket.socket):
        self.username = username
        self.address = address
        self.conn = conn

    def serve(self):
        while True:
            try:
                client_in = self.conn.recv(1024).decode()
                message = MessageFactory.new_message(client_in)
            except Exception as _:
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
        username = conn.recv(1024).decode()
        client = Client(username, address, conn)
        threading.Thread(target=client.serve).start()
        handler.add_client(client)
        print(f"user {username} connected.")

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

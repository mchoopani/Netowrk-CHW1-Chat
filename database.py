import abc
import os
import hashlib
from message import MessageFactory, PrivateMessage, Packet, JoinChatroom, LeaveChatroom, PublicMessage, LoginPacket, \
    Response, ResponseStatus, GroupMessage, JoinGroup


class PasswordIsWrong(Exception):
    pass


class DatabaseInterface(metaclass=abc.ABCMeta):
    def get_user_if_exist(self, username: str, password: str):
        raise NotImplementedError

    def save_user(self, username: str, password: str):
        raise NotImplementedError


class FileSystemDatabase(DatabaseInterface):
    # FIXME: concurrency problem !
    _USERNAMES_PATH = "./data.txt"
    _PRIVATE_CHAT_PATH = "./messages.txt"
    _PUBLIC_CHAT_PATH = "_PublicMessages.txt"
    _GROUP_CHAT_PATH = "_GroupMessages.txt"

    def __init__(self, user_path: str = None, pv_path: str = None, public_path: str = None, group_path: str = None):
        if not user_path:
            user_path = self._USERNAMES_PATH
        if not pv_path:
            pv_path = self._PRIVATE_CHAT_PATH
        if not public_path:
            public_path = self._PUBLIC_CHAT_PATH
        if not group_path:
            group_path = self._GROUP_CHAT_PATH
        self.user_path = user_path
        self.pv_path = pv_path
        self.public_path = public_path
        self.group_path = group_path
        open(self.user_path, "a+").close()
        open(self.pv_path, "a+").close()

    @classmethod
    def get_encoded_password(cls, password):
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def get_user_if_exist(self, username: str, password: str):  # TODO: return user if needed
        encoded_pass = self.get_encoded_password(password)
        with open(self.user_path, 'r') as f:
            for line in f.readlines():
                if not line.startswith("user"):
                    continue

                _, current_username, current_password = line.strip().split("###")
                if current_username == username and current_password == encoded_pass:
                    return None, True
                elif current_username == username and current_password != encoded_pass:
                    raise PasswordIsWrong
            return None, False

    def save_user(self, username: str, password: str):
        with open(self.user_path, 'a') as f:
            f.write(f"user###{username}###{self.get_encoded_password(password)}\n")

    def get_pv_messages(self, sender: str, receiver: str):
        history = []
        with open(self.pv_path, "r") as f:
            for line in f.readlines():
                current_sender, content, current_receiver = line.strip().split("###")
                if sender == current_sender and receiver == current_receiver:
                    history.append(PrivateMessage(current_sender, content, current_receiver))
                elif sender == current_receiver and receiver == current_sender:
                    history.append(PrivateMessage(current_receiver, content, current_sender))

        return history

    def get_public_messages(self, chatroom_id: str):
        history = []
        if os.path.exists(f"./{chatroom_id}{self.public_path}"):
            with open(f"./{chatroom_id}{self.public_path}", "r") as f:
                for line in f.readlines():
                    sender_username, content = line.strip().split("###")
                    if "join" in content:
                        history.append(PublicMessage(sender_username, f'I have joined.', chatroom_id))
                    elif "left" in content:
                        history.append(PublicMessage(sender_username, f'I have left.', chatroom_id))
                    else:
                        history.append(PublicMessage(sender_username, content, chatroom_id))
        return history

    def get_group_messages(self, group_id: str):
        history = []
        if os.path.exists(f"./{group_id}{self.group_path}"):
            with open(f"./{group_id}{self.group_path}", "r") as f:
                for line in f.readlines():
                    sender_username, content = line.strip().split("###")
                    history.append(GroupMessage(sender_username, content, group_id))
        return history

    def save_message(self, message: Packet):
        if isinstance(message, PrivateMessage):
            with open(self.pv_path, 'a') as f:
                f.write(f"{message.sender_username}###{message.content}###{message.receiver_username}\n")
        elif isinstance(message, JoinChatroom):
            with open(f"./{message.chatroom_id}{self.public_path}", 'a') as f:
                f.write(f"{message.sender_username}###have joined.\n")
        elif isinstance(message, LeaveChatroom):
            with open(f"./{message.chatroom_id}{self.public_path}", 'a') as f:
                f.write(f"{message.sender_username}###have left.\n")
        elif isinstance(message, PublicMessage):
            with open(f"./{message.chatroom_id}{self.public_path}", 'a') as f:
                f.write(f"{message.sender_username}###{message.content}\n")
        elif isinstance(message, JoinGroup):
            with open(f"./{message.group_id}{self.group_path}", 'a') as f:
                f.write(f"{message.sender_username}###have joined.\n")
        elif isinstance(message, GroupMessage):
            with open(f"./{message.group_id}{self.group_path}", 'a') as f:
                f.write(f"{message.sender_username}###{message.content}\n")
        else:
            raise Exception("unknown message." + str(message))

    def save_group_id(self, group_id):
        with open(self.group_path, 'a') as f:
            f.write(f"{group_id}\n")

    def check_group_id(self, group_id):
        with open(self.group_path, 'r') as f:
            for line in f.readlines():
                if line.strip() == group_id:
                    return True
            return False

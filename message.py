from enum import Enum
import time
from typing import List


class Packet:
    def __init__(self, sender_username: str):
        self.sender_username = sender_username


class Message(Packet):
    def __init__(self, sender_username: str, content: str, message_time: time):
        super(Message, self).__init__(sender_username)
        self.content = content
        self.time = message_time

    def get_human_readable_output(self):
        return f'{self.sender_username} says: {self.content} at: {self.time}'


class PrivateMessage(Message):
    def __init__(self, sender_username: str, content: str, receiver_username: str, message_time: time):
        super().__init__(sender_username, content, message_time)
        self.receiver_username = receiver_username

    def __str__(self):
        return f"private###{self.sender_username}###{self.receiver_username}###{self.content}###{self.time}"


class Chatroom(Packet):
    def __init__(self, sender_username: str, chatroom_id: str):
        super().__init__(sender_username)
        self.chatroom_id = chatroom_id

    def __str__(self):
        raise NotImplementedError()


class GroupRoom(Packet):
    def __init__(self, sender_username: str, group_id: str):
        super().__init__(sender_username)
        self.group_id = group_id

    def __str__(self):
        raise NotImplementedError()


class JoinChatroom(Chatroom):
    def __str__(self):
        return f"join###{self.sender_username}###{self.chatroom_id}"


class LeaveChatroom(Chatroom):
    def __str__(self):
        return f"leave###{self.sender_username}###{self.chatroom_id}"


class PublicMessage(Message):
    def __init__(self, sender_username: str, content: str, chatroom_id: str, message_time: time):
        super().__init__(sender_username, content, message_time)
        self.chatroom_id = chatroom_id

    def __str__(self):
        return f"public###{self.sender_username}###{self.chatroom_id}###{self.content}###{self.time}"


class GroupMessage(Message):
    def __init__(self, sender_username: str, content: str, group_id: str, message_time: str):
        super().__init__(sender_username, content, message_time)
        self.group_id = group_id

    def __str__(self):
        return f"group###{self.sender_username}###{self.group_id}###{self.content}###{self.time}"


class JoinGroup(GroupRoom):
    def __init__(self, sender_username: str, group_id: str, participants: list):
        super().__init__(sender_username, group_id)
        self.participants = participants

    def __str__(self):
        return f"joinGroup###{self.sender_username}###{self.group_id}"


class StateMessage(Message):
    def __init__(self, sender_username: str, state: "ClientState"):
        super().__init__(sender_username, state, time.strftime('%H:%M:%S'))
        self.state = state

    def __str__(self):
        return f"state###{self.sender_username}###{self.state.value}"


class BusyStateMessage(Message):
    def __init__(self, sender_username: str, content: str):
        super().__init__(sender_username, content, time.strftime('%H:%M:%S'))
        self.content = content

    def __str__(self):
        return f"busyState###{self.sender_username}###{self.content}"


class LoginPacket(Packet):
    def __init__(self, sender_username: str, password: str):
        super().__init__(sender_username)
        self.password = password

    def __str__(self):
        return f"login###{self.sender_username}###{self.password}"


class ResponseStatus(str, Enum):
    OK = "OK"
    FAIL = "FAIL"


class ClientState(str, Enum):
    BUSY = "BUSY"
    AVAILABLE = "AVAILABLE"


class Response(Message):
    def __init__(self, receiver: str, response: str, status: ResponseStatus, message_time: time):
        super().__init__("server", response, message_time)
        self.receiver = receiver
        self.status = status

    def __str__(self):
        return f"response###{self.receiver}###{self.status.value}###{self.content}###{self.time}"


class PVChatHistory(Message):
    def __init__(self, target_username: str, messages: List[PrivateMessage]):
        super().__init__("server", self._stringify_messages(messages), time.strftime('%H:%M:%S'))
        self.target_username = target_username

    @classmethod
    def _stringify_messages(cls, messages: List[PrivateMessage]):
        string_history = []
        for message in messages:
            string_history.append(
                f"{message.sender_username}#{message.receiver_username}#{message.content}#{message.time}"
            )
        return "##".join(string_history)

    @staticmethod
    def get_messages(raw_string: str):
        output = []
        for history in raw_string.split("##"):
            history_splits = history.split("#")
            if len(history_splits) != 4:
                continue
            output.append(
                PrivateMessage(history_splits[0], history_splits[2], history_splits[1], history_splits[3])
            )
        return output

    def __str__(self):
        return f"PVChatHistory###{self.target_username}###{self.content}"


class MessageFactory:
    @classmethod
    def new_message(cls, raw_message: str) -> Packet:
        message_splits = raw_message.split("###")
        sender = message_splits[1]
        if message_splits[0] == 'private':
            receiver = message_splits[2]
            content = message_splits[3]
            time = message_splits[4]
            return PrivateMessage(sender, content, receiver, time)
        elif message_splits[0] == 'join':
            chatroom_id = message_splits[2]
            return JoinChatroom(sender, chatroom_id)
        elif message_splits[0] == 'leave':
            chatroom_id = message_splits[2]
            return LeaveChatroom(sender, chatroom_id)
        elif message_splits[0] == 'public':
            group_id = message_splits[2]
            content = message_splits[3]
            time = message_splits[4]
            return PublicMessage(sender, content, group_id, time)
        elif message_splits[0] == 'joinGroup':
            group_id = message_splits[2]
            return JoinGroup(sender, group_id, [])
        elif message_splits[0] == 'group':
            group_id = message_splits[2]
            content = message_splits[3]
            time = message_splits[4]
            return GroupMessage(sender, content, group_id, time)
        elif message_splits[0] == 'login':
            password = message_splits[2]
            return LoginPacket(sender, password)
        elif message_splits[0] == 'state':
            state = ClientState(message_splits[2])
            return StateMessage(sender, state)
        elif message_splits[0] == 'busyState':
            content = message_splits[2]
            return BusyStateMessage(sender, content)
        elif message_splits[0] == 'response':
            status = message_splits[2]
            receiver = message_splits[1]
            content = message_splits[3]
            time = message_splits[4]
            return Response(receiver, content, ResponseStatus(status), time)
        elif message_splits[0] == 'PVChatHistory':
            return PVChatHistory(message_splits[1], PVChatHistory.get_messages(message_splits[2]))

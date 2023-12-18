import abc
import hashlib


class PasswordIsWrong(Exception):
    pass


class DatabaseInterface(metaclass=abc.ABCMeta):
    def get_user_if_exist(self, username: str, password: str):
        raise NotImplementedError

    def save_user(self, username: str, password: str):
        raise NotImplementedError


class FileSystemDatabase(DatabaseInterface):
    # FIXME: concurrency problem !
    _DEFAULT_PATH = "./data.txt"

    def __init__(self, path: str = None):
        if not path:
            path = self._DEFAULT_PATH
        self.path = path
        open(self.path, "a+").close()

    @classmethod
    def get_encoded_password(cls, password):
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    def get_user_if_exist(self, username: str, password: str):  # TODO: return user if needed
        encoded_pass = self.get_encoded_password(password)
        with open(self.path, 'r') as f:
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
        with open(self.path, 'a') as f:
            f.write(f"user###{username}###{self.get_encoded_password(password)}\n")

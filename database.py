import abc


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

    def get_user_if_exist(self, username: str, password: str):  # TODO: return user if needed
        with open(self.path, 'r') as f:
            for line in f.readlines():
                if not line.startswith("user"):
                    continue

                _, current_username, current_password = line.strip().split("###")
                if current_username == username and current_password == password:
                    return None, True
                elif current_username == username and current_password != password:
                    raise PasswordIsWrong
            return None, False

    def save_user(self, username: str, password: str):
        with open(self.path, 'a') as f:
            f.write(f"user###{username}###{password}\n")

from collections import defaultdict


class Database:
    _instance = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = Database()
        return cls._instance

    def __init__(self):
        self.storage = defaultdict(lambda: [])

    def get(self, key):
        return self.storage[key]

    def set(self, key, value):
        self.storage[key] = value

    def get_all_keys(self):
        return self.storage.keys()

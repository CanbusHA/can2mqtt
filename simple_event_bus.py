# TODO use weak refs to handlers

class Slot(object):
    def __init__(self):
        self.handlers = {}

    def __call__(self, *args, **kwargs):
        for handler in self.handlers.values():
            handler(*args, **kwargs)

    def register(self, fun):
        handle = object()
        self.handlers[handle] = fun
        return handle

    def unregister(self, handle):
        del self.handlers[handle]

"""Importable runtime shims for translated reference-plugin fixtures."""


class MappedControllerBase:
    pass


def mapped_controller(cls):
    return cls


def mapped_route(path):
    def decorate(func):
        return func

    return decorate

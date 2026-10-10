"""Domain whose snapshot state changed shape across releases.

Version history of ``Contact`` state:

1. ``name`` (full name) and ``phone``.
2. Adds ``email``; old contacts get ``None``.
3. Renames ``phone`` to ``telephone``.
4. Splits ``name`` into ``first_name`` and ``last_name``.
"""

from coopy.decorators import readonly


def split_name(name):
    first, _, last = name.partition(" ")
    return first, last


class Contact:
    STATE_VERSION = 4

    def __init__(self, first_name, last_name, telephone, email=None):
        self.first_name = first_name
        self.last_name = last_name
        self.telephone = telephone
        self.email = email

    def __getstate__(self):
        # Store the version with the fields so later code knows the shape.
        return dict(vars(self), state_version=self.STATE_VERSION)

    def __setstate__(self, state):
        state = dict(state)
        # Version 1 snapshots predate the marker.
        version = state.pop("state_version", 1)
        if version > self.STATE_VERSION:
            raise ValueError(f"Contact state version {version} is newer than this code")
        if version < 2:  # added a field with a default
            state["email"] = None
        if version < 3:  # renamed a field
            state["telephone"] = state.pop("phone")
        if version < 4:  # split one field into two
            state["first_name"], state["last_name"] = split_name(state.pop("name"))
        self.__dict__.update(state)


class AddressBook:
    def __init__(self):
        self.contacts = {}

    def add(self, first_name, last_name, telephone, email=None):
        contact = Contact(first_name, last_name, telephone, email)
        self.contacts[f"{first_name} {last_name}"] = contact

    @readonly
    def describe(self, key):
        contact = self.contacts[key]
        return {
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "telephone": contact.telephone,
            "email": contact.email,
        }

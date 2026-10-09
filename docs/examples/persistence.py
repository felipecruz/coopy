"""Run with: python docs/examples/persistence.py"""

from tempfile import TemporaryDirectory

from wiki import Wiki

from coopy.base import init_persistent_system


def round_trip(directory):
    wiki = init_persistent_system(Wiki, basedir=directory)
    try:
        wiki.create_page("Home", "Before the checkpoint")
        wiki.take_snapshot()
        wiki.create_page("Journal", "After the checkpoint")
        expected = wiki.get_page("Journal")
        detached = wiki.get_page("Home")
        detached["content"] = "Only changes this copy"
        assert wiki.get_page("Home")["content"] == "Before the checkpoint"
    finally:
        wiki.close()

    # An instance is also accepted. Stored state replaces this fresh instance.
    wiki = init_persistent_system(Wiki(), basedir=directory)
    try:
        assert wiki.get_page("Home")["content"] == "Before the checkpoint"
        # Includes all three clock values, recovered by journal replay.
        assert wiki.get_page("Journal") == expected
        wiki.start_snapshot_manager(60)  # seconds; first snapshot after 60 s
        wiki.create_page("Reopened", "Written after recovery")
        wiki.take_snapshot()
    finally:
        wiki.close()  # stops the timer and closes the journal

    wiki = init_persistent_system(Wiki, basedir=directory)
    try:
        assert wiki.get_page("Journal") == expected
        assert wiki.get_page("Reopened")["content"] == "Written after recovery"
    finally:
        wiki.close()


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        round_trip(directory)

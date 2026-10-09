.. _util_api:

Utilitary API
=============

There are some utilitary methods to help you.

Given::

    from coopy.base import init_persistent_system
    from wiki import Wiki  # the tutorial domain

    wiki = init_persistent_system(Wiki, basedir="wiki-data")
    try:
        paths = wiki.basedir_abspath()
    finally:
        wiki.close()


.. function:: basedir_abspath()

    Return a list with all basedirs absolute paths


Tests utils
-----------

If your domain uses the :doc:`use_clock` feature, you'll likely to face errors while
testing your pure domain since the `_clock` is injected by coopy.

There are 2 ways of handle this: Enable a regular clock on your domain, for testing
or mock your clock to return the same date.

.. function:: TestSystemMixin.mock_clock(domain, mocked_date)

    This method will inject a clock that always return `mocked_date`

.. function:: TestSystemMixin.enable_clock(domain)

    This method will inject a regular coopy clock on your domain instance

.. toctree::
   :maxdepth: 1

   modern-api

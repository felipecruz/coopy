{{ fullname | escape | underline }}

.. currentmodule:: {{ module }}

{% if objtype == "class" %}
.. autoclass:: {{ objname }}
   :members:
   :undoc-members:
{% else %}
.. autofunction:: {{ objname }}
{% endif %}

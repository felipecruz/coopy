# Sphinx configuration for the coopy documentation.
# Reference: https://www.sphinx-doc.org/en/master/usage/configuration.html

from coopy import __version__

project = "coopy"
author = "Felipe Cruz"
copyright = "2012–2026, Felipe Cruz"
version = ".".join(__version__.split(".")[:2])
release = __version__

extensions = ["sphinx.ext.autodoc", "sphinx.ext.autosummary"]
autosummary_generate = True
autodoc_typehints = "both"
autodoc_typehints_format = "short"
autodoc_member_order = "bysource"

templates_path = ["_templates"]
root_doc = "index"
exclude_patterns = ["build", "_build"]

# Furo: https://pradyunsg.me/furo/ (light and dark mode, sidebar navigation).
html_theme = "furo"
html_title = f"coopy {release}"
html_use_index = False
html_theme_options = {
    "source_repository": "https://github.com/felipecruz/coopy/",
    "source_branch": "main",
    "source_directory": "docs/",
}
pygments_style = "tango"
pygments_dark_style = "monokai"

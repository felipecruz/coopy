1 minute coopy tutorial
=========================

**coopy** enforces you to implement code in the object-oriented way. Imagine a wiki system::

    class WikiPage():
        def __init__(self, id, content):
            self.id = id
            self.content = content
            self.history = []
            self.last_modify = datetime.datetime.now()

    class Wiki():
        def __init__(self):
            self.pages = {}
        def create_page(self, page_id, content):
            page = None
            if page_id in self.pages:
                page = self.pages[page_id]
            if not page:
                page = WikiPage(page_id, content)
                self.pages[page_id] = page	    
            return page

It's very easy to implement a wiki system thinking only on it's objects. Let's move forward::

    from coopy import init_system
    wiki = init_system(Wiki(), "/path/to/somedir")
    wiki.create_page('My First Page', 'My First Page Content')

That's all you need to use coopy. If you stop your program and run again::

    from coopy import init_system
    wiki = init_system(Wiki(), "/path/to/somedir")
    page = wiki.pages['My First Page']

If you want to know how coopy works, check out :doc:`basics` 

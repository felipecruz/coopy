.. _usage:

Using coopy 
=============

There are many different ways to use **coopy**. Let me show you some::

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

    wiki = init_system(Wiki)

or::

    wiki = init_system(Wiki())

or::

    wiki = init_system(Wiki(),'/path/to/log/files')

or setup a Master node::

    init_system(Wiki, master=True)

or setup a Slave node::

     init_system(Wiki, replication=True)

or check all arguments::

    def init_system(obj, basedir=None, snapshot_time=0, master=False, replication=False, port=5466, host='127.0.0.1', password='copynet'):

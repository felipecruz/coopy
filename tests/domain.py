'''
Created on May 19, 2010

@author: felipe
'''

from coopy.decorators import readonly

class WikiPage(object):
    def __init__(self, id, content, last_modified, parent=None):
        self.id = id
        self.content = content
        self.history = []
        self.last_modified = last_modified
        self.parent = parent

class Wiki(object):
    def __init__(self):
        self.pages = {}
        
    def create_page(self, id, content, parent):
        page = WikiPage(id, content, self._clock.now(), parent)
        
        if not id in self.pages:
            self.pages[id] = page
        else:
            self.update_page(id, content, parent)

        return page

    @readonly
    def get_page(self, id):
        if id in self.pages:
            return self.pages[id]
        else:
            return None

    def update_page(self, page_id, content, parent):
        old_page = self.pages[page_id]
        page = WikiPage(id, content, self._clock.now(), parent)
        page = self.add_history(old_page, page)
        self.pages[page_id] = page

        
    def add_history(self, old_page, page):
        page.history = old_page.history
        page.history.append(old_page)
        return page

    def multiple_call_now(self):
        self.dt1 = self._clock.now()
        import time
        time.sleep(0.1)
        self.dt2 = self._clock.now()

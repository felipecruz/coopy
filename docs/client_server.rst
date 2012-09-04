.. _client_server:

Client-Server
-------------

When you want to detach client from server, you can use coopy + Pyro (or xmlrpclib) in order to have a client and a server (running coopy).

This is useful when you want to have only one machine dedicated to have it's ram memory filled with python objects.

Note, that this example uses Pyro.core.ObjBase instead of Pyro.core.SynchronizedObjBase, because by default, coopy proxy (wiki object) is already thread-safe unless you decorate your business methods with @unlocked decorator.

Server Code::

    #coopy code
    wiki = coopy.init_system(Wiki(), "pyro")

    #pyro code
    obj = Pyro.core.ObjBase()
    obj.delegateTo(wiki)
    Pyro.core.initServer()
    daemon=Pyro.core.Daemon()
    uri=daemon.connect(obj,"wiki")
    daemon.requestLoop()

Client code::

    #pyro code
    wiki = Pyro.core.getProxyForURI("PYRO://127.0.0.1:7766/whatever")

.. _replication:

Master/Slave replication
------------------------

**coopy** comes with master/slave replication mechanism.

Basically:

* Master instance are read/write
* Slaves are read only
* Slaves can only execute @readonly methods.

Another detail, is that you can set a password on master. This password provides basich auth to slaves connects to a master instance.

When slaves connects to master and passes authentication process, it will receive all data to synchronize with master state. Commands executed further on master will be replicated to slave node.

Slaves are useful to take snapshots without needing master to be locked as well to provide load balancing for reading.

Snipets to run master and slave instances

Master instance::

    init_system(Wiki, master=True)

Slave instance, default host and default port::

    init_system(Wiki, replication=True)

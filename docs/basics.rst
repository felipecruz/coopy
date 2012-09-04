coopy basics
===================================

**coopy** returns to you a proxy to your object. Everytime you call some method on this proxy, coopy will log to disk this operation, so it can be re-executed later on a restore process. This behaviour assures that you object will have their state persisted. 

So far, you know that you are manipulating a proxy object and when you call methods on this object, this invocation will be written to disk. We call **log file** the files that contains all operations executed on your object. This log files are created on what we call **basedir**. You can specify basedir or coopy will lowercase your object class name and create a directory with this name to store all log files. 

**coopy logger** is responsible to receive this methods invocations, create **Action** objects and serialize to disk. It automatically handles file rotations, like python logging RotateFileHandler, in order to keep log files not too big. 

As your application is running, your log file number will be increasing and restore process can start to run slowly, becase it'll open many log files. To avoid that you can take **snapshots** from your object.
**Snapshot file** is a copy of your objects in memory serialized trhough the disk. As you take a snapshot, all log files older than this snapshots can be deleted if you want. Take snapshots will also speed up the restore process, because is much more fast open 1 file and deserialize to memory than open 10 files to execute each action inside of them.

Now, you know everything about how information are stored. Let's see how this information are restored.

**Restore process** is what coopy do to restore your object state. It checks for **log files** and **snapshot files** on your **basedir** to look to the last snapshot taken and all log files created after. It'll deserialize this **snapshot file** and then open all log files to re-execute all **Actions** that were executed after the snapshot was created. This will assure that your object will have the same state as your object had once in the past when your program was terminated or maybe killed.

The bascis of **coopy** is covered here

* You are manipulating a proxy object that delegates memory execution to your **domain** object
* Once you call a method on proxy, this call turns into a **Action** object and then serialized to disk.
* **Log files** contain **Action** objects to be re-executed
* You can take **Snapshots** of your object to increase your **restore process** and have a small number of files on your **basedir**
* Everytime you use **coopy** it'll look to your **basedir** and restore your object state with the files there

All this is done using python cPickle module. 

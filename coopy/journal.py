import six
import os
import pickle

from base64 import b64encode, b64decode

from coopy import fileutils

if six.PY3:
    from pickle import Pickler, dumps
else:
    from cPickle import Pickler, dumps

class DiskJournal(object):
    def __init__(self, basedir, system_data_path):
        '''
            set basedir and declare file attribute
        '''
        self.basedir = basedir
        self.file = None
        self.system_data_path = system_data_path

    def setup(self):
        '''
            configure file attribute, create pickler
        '''
        self.file = self.current_journal_file(self.basedir)
        self.pickler = Pickler(self.file, pickle.HIGHEST_PROTOCOL)
        self.file.set_pickler(self.pickler)

    def current_journal_file(self, basedir):
        '''
            get current file on basedir(last created one)
            and return a Rotate wrapper.

            if current file size > 1Mb (configured on fileutils) crate
            another file with the next name
        '''

        last_file_name = fileutils.last_log_file(self.basedir)

        if last_file_name and os.path.getsize(self.basedir + last_file_name) \
            < fileutils.MAX_LOGFILE_SIZE:

            file = fileutils.RotateFileWrapper(
                       open(self.basedir + last_file_name, 'ab'),
                       self.basedir,
                       self.system_data_path)
        else:
            file = fileutils.RotateFileWrapper(
                       open(fileutils.next_log_file(self.basedir), 'wb'),
                       self.basedir,
                       self.system_data_path)

        return file

    def receive_before(self, message):
        pass

    def receive(self, message):
        '''
            receive a message and pickle
        '''
        self.pickler.dump(message)

    def receive_exception(self, message):
        pass

    def close(self):
        '''
            close file instance
        '''
        if not self.file.closed:
            self.file.close()


def sign_data(private_key_loc, data):
    '''
    param: private_key_loc Path to your private key
    param: package Data to be signed
    return: base64 encoded signature
    '''
    from Crypto.PublicKey import RSA
    from Crypto.Signature import PKCS1_v1_5
    from Crypto.Hash import SHA256
    from base64 import b64encode, b64decode
    key = open(private_key_loc, "r").read()
    rsakey = RSA.importKey(key)
    signer = PKCS1_v1_5.new(rsakey)
    digest = SHA256.new()
    digest.update(b64decode(data))
    sign = signer.sign(digest)
    return b64encode(sign)


def verify_sign(public_key_loc, signature, data):
    '''
    Verifies with a public key from whom the data came that it was indeed
    signed by their private key
    param: public_key_loc Path to public key
    param: signature String signature to be verified
    return: Boolean. True if the signature is valid; False otherwise.
    '''
    from Crypto.PublicKey import RSA
    from Crypto.Signature import PKCS1_v1_5
    from Crypto.Hash import SHA256
    from base64 import b64decode
    pub_key = open(public_key_loc, "r").read()
    rsakey = RSA.importKey(pub_key)
    signer = PKCS1_v1_5.new(rsakey)
    digest = SHA256.new()
    digest.update(b64decode(data))
    if signer.verify(digest, b64decode(signature)):
        return True
    return False


def generate_RSA(bits=2048):
    '''
    Generate an RSA keypair with an exponent of 65537 in PEM format
    param: bits The key length in bits
    Return private key and public key
    '''
    from Crypto.PublicKey import RSA
    new_key = RSA.generate(bits, e=65537)
    public_key = new_key.publickey().exportKey("PEM")
    private_key = new_key.exportKey("PEM")
    return private_key, public_key


class SecureJournal(DiskJournal):
    def __init__(self, private_key_file, basedir, system_data_path):
        super(SecureJournal, self).__init__(basedir, system_data_path)
        self.signatures = []
        self.private_key_file = private_key_file

    def setup(self):
        super(SecureJournal, self).setup()
        self.last_file_id = self.file.name
        self.sig_file_name = self.last_file_id.replace('transaction', 'signatures')
        self.sig_file = open(self.sig_file_name, 'w')

    def receive(self, message):
        if self.last_file_id != self.file.name:
            self.sig_file.close()
            self.last_file_id = self.file.name
            self.sig_file_name = self.last_file_id.replace('transaction', 'signatures')
            self.sig_file = open(self.sig_file_name, 'w')

        pickled_message_bytes = b64encode(dumps(message))
        signature = sign_data(self.private_key_file.name, pickled_message_bytes)
        self.pickler.dump(pickled_message_bytes)
        self.signatures.append(signature)
        self.sig_file.write("{}\n".format(signature))

    def close(self):
        super(SecureJournal, self).close()
        if not self.sig_file.closed:
            self.sig_file.close()

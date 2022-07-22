import os.path

import nitrate
from bugzilla._backendxmlrpc import _BugzillaXMLRPCTransport
from pylero import session
from requests import sessions
from requre import cassette
from requre.cassette import StorageKeysInspectSimple
from requre.helpers.guess_object import Guess
from requre.helpers.requests_response import RequestResponseHandling
from requre.objects import ObjectStorage
from suds import reader
from suds.transport import http

import tmt.export

nitrate.set_cache_level(nitrate.CACHE_NONE)

# decorate functions what communicates with nitrate
nitrate.xmlrpc_driver.GSSAPITransport.single_request = Guess.decorator_plain()(
    nitrate.xmlrpc_driver.GSSAPITransport.single_request)
nitrate.xmlrpc_driver.GSSAPITransport.single_request_with_cookies = Guess.decorator_plain()(
    nitrate.xmlrpc_driver.GSSAPITransport.single_request_with_cookies)

# decorate functions that communicate with bugzilla (xmlrpc)
_BugzillaXMLRPCTransport.single_request = Guess.decorator_plain()(
    _BugzillaXMLRPCTransport.single_request)
sessions.Session.send = RequestResponseHandling.decorator(
    item_list=[1])(
        sessions.Session.send)

tmt.export.check_git_url = Guess.decorator_plain()(tmt.export.check_git_url)


class BinaryDataFile(ObjectStorage):
    def to_serializable(self, obj):
        cassette = self.get_cassette()
        counter = 0
        if hasattr(cassette, "counter"):
            counter = cassette.counter
        cassette.counter = counter + 1
        old_sf = self.get_cassette().storage_file
        sf = f"{old_sf}.bin.{cassette.counter}"
        data = super().to_serializable(obj)
        with open(sf, "wb") as fd:
            fd.write(data)
        return os.path.basename(os.path.basename(sf))

    def from_serializable(self, data):
        sf = os.path.join(os.path.dirname(self.get_cassette().storage_file), data)
        with open(sf, "rb") as fd:
            output = fd.read()
        return super().from_serializable(output)


# decorate functions that communicate with polarion (soap - sax)
reader.DocumentReader.open = BinaryDataFile.decorator_plain()(reader.DocumentReader.open)
http.HttpTransport.send = BinaryDataFile.decorator_plain()(http.HttpTransport.send)
session.Session._login = Guess.decorator_plain()(session.Session._login)

# use storage simple strategy to avoid use full stack info for keys
cassette.StorageKeysInspectDefault = StorageKeysInspectSimple

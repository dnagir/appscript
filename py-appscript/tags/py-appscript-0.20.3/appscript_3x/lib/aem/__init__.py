"""aem -- Mid-level wrapper for building and sending Apple events.

(C) 2005-2008 HAS
"""

from . import ae, kae, findapp, mactypes, aemconnect
from .aemconnect import CantLaunchApplicationError
from .aemsend import Event, EventError, newappleevent, sendappleevent
from .aemcodecs import Codecs
from .aemreference import app, con, its, customroot, Query
from .typewrappers import AETypeBase, AEType, AEEnum, AEProp, AEKey


__all__ = [
	'ae', 'kae',
	'findapp', 'mactypes',
	'Application',
	'Event', 'EventError',
	'CantLaunchApplicationError',
	'Codecs', 
	'app', 'con', 'its', 'customroot', 'Query',
	'AETypeBase', 'AEType', 'AEEnum', 'AEProp', 'AEKey',
]


######################################################################
# PRIVATE
######################################################################

_defaultcodecs = Codecs()

######################################################################
# PUBLIC
######################################################################

class Application(Query):
	"""Target application for Apple events."""
	
	# aem.Application subclasses can override these attributes to modify the creation
	# and sending of AppleEvent descriptors
	_createproc = staticmethod(newappleevent)
	_sendproc = staticmethod(sendappleevent)
	
	# aem.Application subclasses can override this attribute (typically with a subclass 
	# of the standard aemsend.Event class) to have the event() method return a different
	# class instance; simpler than overriding the event() method
	_Event = Event

	# need to keep a local copy of this constant to avoid upsetting Application.__del__() 
	# at cleanup time, otherwise it may be disposed of before __del__() can use it
	_transaction = _kAnyTransactionID = kae.kAnyTransactionID
	
	def __init__(self, path=None, pid=None, url=None, desc=None, codecs= _defaultcodecs):
		"""
			path : str | None -- full path to local application
			pid : int | None -- Unix process id for local process
			url : str | None -- url for remote process
			desc : AEAddressDesc | None -- AEAddressDesc for application
			codecs : Codecs -- used to convert Python values to AEDescs and vice-versa
			
			Notes: 
				- If no path, pid, url or aedesc is given, target will be 'current application'.
				- If path is given, application will be launched automatically; if pid, url or 
					desc is given, user is responsible for ensuring application is running 
					before sending it any events.
		"""
		self._codecs = codecs
		self._path = path
		if path:
			self._address = aemconnect.localapp(path)
			self.AEM_identity = ('path', path)
		elif pid:
			self._address = aemconnect.localappbypid(pid)
			self.AEM_identity = ('pid', pid)
		elif url:
			self._address = aemconnect.remoteapp(url)
			self.AEM_identity = ('url', url)
		elif desc:
			self._address = desc
			self.AEM_identity = ('desc', (desc.type, desc.data))
		else:
			self._address = aemconnect.currentapp
			self.AEM_identity = ('current', None)
	
	def __repr__(self):
		args = []
		if self.AEM_identity[0] == 'desc':
			args.append('desc=%r' % self._address)
		elif self.AEM_identity[0] == 'path':
			args.append(repr(self.AEM_identity[1]))
		elif self.AEM_identity[0] != 'current':
			args.append('%s=%r' % self.AEM_identity)
		if self._codecs != _defaultcodecs:
			args.append('codecs=%r' % self._codecs)
		modulename = '%s.' % self.__class__.__module__
		if modulename == 'aem.send.':
			modulename = 'aem.'
		elif modulename == '__main__.':
			modulename = ''
		return '%s%s(%s)' % (modulename, self.__class__.__name__, ', '.join(args))
			
	__str__ = __repr__
	
	def __eq__(self, val):
		return self is val or (
				self.__class__ == val.__class__ and 
				self.AEM_identity == val.AEM_identity)
	
	def __ne__(self, val):
		return not self == val
	
	def __hash__(self):
		return hash(self.AEM_identity)
	
	def AEM_comparable(self):
		return ['AEMApplication', self.AEM_identity]
	
	def AEM_packSelf(self, codecs):
		return self._address
	
	def __del__(self):
		# If user forgot to close a transaction before throwing away the Application object 
		# that opened it, try to close it for them. Otherwise application will be left in 
		# mid-transaction, preventing anyone else from using it.
		if self._transaction != self._kAnyTransactionID:
			self.endtransaction()
	
	#######
	# Utility functions; placed here for convenience
	
	# Launch a local application without sending it the usual 'run' event (aevtoapp):
	launch = staticmethod(aemconnect.launchapp)
	
	# Check if an application specified by path/pid/URL/AEAddressDesc is running:
	processexistsforpath = staticmethod(aemconnect.processexistsforpath)
	processexistsforpid = staticmethod(aemconnect.processexistsforpid)
	processexistsforurl = staticmethod(aemconnect.processexistsforurl)
	processexistsfordesc = staticmethod(aemconnect.processexistsfordesc)
	
	#######
	
	addressdesc = property(lambda self: self._address)
	
	def reconnect(self):
		"""If application has quit since this Application object was created, its 
			AEAddressDesc is no longer valid so this Application object 
			will not work even when application is restarted. reconnect() will 
			update this Application object's AEAddressDesc so it's valid again.
		
			Note: this only works for Application objects specified by path, not 
			by URL or AEDesc. Also, any Event objects created prior to calling 
			reconnect() will still be invalid.
		"""
		if self._path:
			self._address = aemconnect.localapp(self._path)
	
	##
	
	def event(self, event, params={}, atts={}, returnid=kae.kAutoGenerateReturnID, codecs=None):
		"""Construct an Apple event.
			event  : str -- 8-letter code indicating event's class, e.g. 'coregetd'
			params : dict -- a dict of form {AE_code:anything,...} containing zero or more 
					event parameters (message arguments)
			atts : dict -- a dict of form {AE_code:anything,...} containing zero or more 
					event attributes (event info)
			returnid : int  -- reply event's ID (default = kAutoGenerateReturnID)
			codecs : Codecs | None -- custom codecs to use when packing/unpacking this
					event; if None, codecs supplied in Application constructor are used
		"""
		return self._Event(self._address, event, params, atts, self._transaction, returnid, 
				codecs or self._codecs, self._createproc, self._sendproc)
	
	def begintransaction(self, session=None):
		"""Begin a transaction."""
		if self._transaction != self._kAnyTransactionID:
			raise RuntimeError("Transaction is already active.")
		self._transaction = self._Event(self._address, 'miscbegi', 
				session is not None and {'----':session} or {}, codecs=_defaultcodecs).send()
	
	def aborttransaction(self):
		"""Abort the current transaction."""
		if self._transaction == self._kAnyTransactionID:
			raise RuntimeError("No transaction is active.")
		self._Event(self._address, 'miscttrm', transaction=self._transaction).send()
		self._transaction = self._kAnyTransactionID
	
	def endtransaction(self):
		"""End the current transaction."""
		if self._transaction == self._kAnyTransactionID:
			raise RuntimeError("No transaction is active.")
		self._Event(self._address, 'miscendt', transaction=self._transaction).send()
		self._transaction = self._kAnyTransactionID


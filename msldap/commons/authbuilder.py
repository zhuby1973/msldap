import enum
import platform

import copy
from msldap.commons.credential import MSLDAPCredential, LDAPAuthProtocol
from msldap.authentication.spnego.native import SPNEGO
from msldap.authentication.ntlm.native import NTLMAUTHHandler, NTLMHandlerSettings
from msldap.authentication.kerberos.native import MSLDAPKerberos
from minikerberos.common.target import KerberosTarget
from minikerberos.common.proxy import KerberosProxy
from minikerberos.common.creds import KerberosCredential
from minikerberos.common.spn import KerberosSPN

from minikerberos.network.selector import KerberosClientSocketSelector


if platform.system().upper() == 'WINDOWS':
	from msldap.authentication.kerberos.sspi import MSLDAPKerberosSSPI
	from msldap.authentication.ntlm.sspi import MSLDAPNTLMSSPI

class MSLDAPNTLMCredential:
	def __init__(self):
		self.username = None
		self.domain = ''
		self.password = None
		self.workstation = None
		self.is_guest = False
		self.nt_hash = None
		self.lm_hash = None 
		self.signing_preferred = False
		self.encryption_preferred = False

class MSLDAPSIMPLECredential:
	def __init__(self):
		self.username = None
		self.domain = None
		self.password = None

class MSLDAPPLAINCredential:
	def __init__(self):
		self.username = None
		self.domain = None
		self.password = None

class MSLDAPKerberosCredential:
	def __init__(self):
		self.connection = None #KerberosCredential
		self.target = None #KerberosTarget
		self.ksoc = None #KerberosSocketAIO
		self.ccred = None
		self.signing_preferred = False
		self.encryption_preferred = False

class MSLDAPKerberosSSPICredential:
	def __init__(self):
		self.domain = None
		self.password = None
		self.username  = None
		self.signing_preferred = False
		self.encryption_preferred = False
		
class MSLDAPNTLMSSPICredential:
	def __init__(self):
		self.username = None
		self.password = None
		self.domain = None
		self.signing_preferred = False
		self.encryption_preferred = False



"""
class LDAPAuthProtocol(enum.Enum):
	PLAIN = 'PLAIN' #actually SASL-PLAIN

	MULTIPLEXOR = 'MULTIPLEXOR'
	MULTIPLEXOR_SSL = 'MULTIPLEXOR_SSL'
	SSPI_NTLM = 'SSPI_NTLM' #actually SASL-GSSAPI-SPNEGO-NTLM but with integrated SSPI
	SSPI_KERBEROS = 'SSPI_KERBEROS' #actually SASL-GSSAPI-SPNEGO-KERBEROS but with integrated SSPI
"""

class AuthenticatorBuilder:
	def __init__(self, creds, target = None):
		self.creds = creds
		self.target = target
	
	def build(self):
		if self.creds.auth_method == LDAPAuthProtocol.SICILY:
			ntlmcred = MSLDAPNTLMCredential()
			ntlmcred.username = self.creds.username
			ntlmcred.domain = self.creds.domain if self.creds.domain is not None else ''
			ntlmcred.workstation = None
			ntlmcred.is_guest = False
			ntlmcred.channelbind = self.creds.channelbind

			
			if self.creds.password is None:
				raise Exception('NTLM authentication requres password!')
			ntlmcred.password = self.creds.password
			
			settings = NTLMHandlerSettings(ntlmcred)
			return NTLMAUTHHandler(settings)

		elif self.creds.auth_method == LDAPAuthProtocol.SIMPLE:
			cred = MSLDAPPLAINCredential()
			cred.username = self.creds.username
			cred.domain = self.creds.domain
			cred.password = self.creds.password
			return cred

		elif self.creds.auth_method == LDAPAuthProtocol.PLAIN:
			cred = MSLDAPSIMPLECredential()
			cred.username = self.creds.username
			cred.domain = self.creds.domain
			cred.password = self.creds.password
			return cred

		elif self.creds.auth_method in [LDAPAuthProtocol.NTLM_PASSWORD, LDAPAuthProtocol.NTLM_NT]:
			ntlmcred = MSLDAPNTLMCredential()
			ntlmcred.username = self.creds.username
			ntlmcred.domain = self.creds.domain if self.creds.domain is not None else ''
			ntlmcred.workstation = None
			ntlmcred.is_guest = False
			ntlmcred.channelbind = self.creds.channelbind
			
			if self.creds.password is None:
				raise Exception('NTLM authentication requres password!')

			if self.creds.auth_method == LDAPAuthProtocol.NTLM_PASSWORD:
				ntlmcred.password = self.creds.password
			elif self.creds.auth_method == LDAPAuthProtocol.NTLM_NT:
				ntlmcred.nt_hash = self.creds.password
			else:
				raise Exception('Unknown NTLM auth method!')
			
			settings = NTLMHandlerSettings(ntlmcred)
			handler = NTLMAUTHHandler(settings)
			
			##setting up SPNEGO
			spneg = SPNEGO()
			spneg.add_auth_context('NTLMSSP - Microsoft NTLM Security Support Provider', handler)
			
			return spneg

		elif self.creds.auth_method in [
				LDAPAuthProtocol.KERBEROS_RC4, 
				LDAPAuthProtocol.KERBEROS_NT, 
				LDAPAuthProtocol.KERBEROS_AES,
				LDAPAuthProtocol.KERBEROS_PASSWORD, 
				LDAPAuthProtocol.KERBEROS_CCACHE, 
				LDAPAuthProtocol.KERBEROS_KEYTAB]:
			
			if self.target is None:
				raise Exception('Target must be specified with Kerberos!')
				
			if self.target.host is None:
				raise Exception('target must have a domain name or hostname for kerberos!')
				
			if self.target.dc_ip is None:
				raise Exception('target must have a dc_ip for kerberos!')
			
			
			kc = KerberosCredential()
			kc.username = self.creds.username
			kc.domain = self.creds.domain
			if self.creds.auth_method == LDAPAuthProtocol.KERBEROS_PASSWORD:
				kc.password = self.creds.password
			elif self.creds.auth_method == LDAPAuthProtocol.KERBEROS_NT:
				kc.nt_hash = self.creds.password
				
			elif self.creds.auth_method == LDAPAuthProtocol.KERBEROS_AES:
				if len(self.creds.password) == 32:
					kc.kerberos_key_aes_128 = self.creds.password
				elif len(self.creds.password) == 64:
					kc.kerberos_key_aes_256 = self.creds.password
					
			elif self.creds.auth_method == LDAPAuthProtocol.KERBEROS_RC4:
				kc.kerberos_key_rc4 = self.creds.password
			
			elif self.creds.auth_method == LDAPAuthProtocol.KERBEROS_CCACHE:
				kc.ccache = self.creds.password
			elif self.creds.auth_method == LDAPAuthProtocol.KERBEROS_KEYTAB:
				kc.keytab = self.creds.password
			else:
				raise Exception('No suitable secret type found to set up kerberos!')

			
			
				
			kcred = MSLDAPKerberosCredential()
			kcred.ccred = kc
			kcred.spn = KerberosSPN.from_target_string(self.target.to_target_string())
			kcred.target = KerberosTarget(self.target.dc_ip)
			kcred.channelbind = self.creds.channelbind
			
			if self.target.proxy is not None:
				kcred.target.proxy = KerberosProxy()
				kcred.target.proxy.target = copy.deepcopy(self.target.proxy.target)
				kcred.target.proxy.target.endpoint_ip = self.target.dc_ip
				kcred.target.proxy.target.endpoint_port = 88
				kcred.target.proxy.creds = copy.deepcopy(self.target.proxy.auth)

			handler = MSLDAPKerberos(kcred)
			
			#setting up SPNEGO
			spneg = SPNEGO()
			spneg.add_auth_context('MS KRB5 - Microsoft Kerberos 5', handler)
			return spneg

		elif self.creds.auth_method == LDAPAuthProtocol.SSPI_KERBEROS:
			if self.target is None:
				raise Exception('Target must be specified with Kerberos SSPI!')
				
			kerbcred = MSLDAPKerberosSSPICredential()
			kerbcred.username = self.creds.domain if self.creds.domain is not None else '<CURRENT>'
			kerbcred.username = self.creds.username if self.creds.username is not None else '<CURRENT>'
			kerbcred.password = self.creds.password if self.creds.password is not None else '<CURRENT>'
			kerbcred.spn = self.target.to_target_string()
			kerbcred.channelbind = self.creds.channelbind
			
			handler = MSLDAPKerberosSSPI(kerbcred)
			#setting up SPNEGO
			spneg = SPNEGO()
			spneg.add_auth_context('MS KRB5 - Microsoft Kerberos 5', handler)
			return spneg
		
		elif self.creds.auth_method == LDAPAuthProtocol.SSPI_NTLM:
			ntlmcred = MSLDAPNTLMSSPICredential()
			ntlmcred.username = self.creds.domain if self.creds.domain is not None else '<CURRENT>'
			ntlmcred.username = self.creds.username if self.creds.username is not None else '<CURRENT>'
			ntlmcred.password = self.creds.password if self.creds.password is not None else '<CURRENT>'
			ntlmcred.channelbind = self.creds.channelbind

			handler = MSLDAPNTLMSSPI(ntlmcred)
			#setting up SPNEGO
			spneg = SPNEGO()
			spneg.add_auth_context('NTLMSSP - Microsoft NTLM Security Support Provider', handler)
			return spneg


"""
elif creds.authentication_type.value.startswith('MULTIPLEXOR'):
			if creds.authentication_type in [SMBAuthProtocol.MULTIPLEXOR_SSL_NTLM, SMBAuthProtocol.MULTIPLEXOR_NTLM]:
				from aiosmb.authentication.ntlm.multiplexor import SMBNTLMMultiplexor

				ntlmcred = SMBMultiplexorCredential()
				ntlmcred.type = 'NTLM'
				if creds.username is not None:
					ntlmcred.username = '<CURRENT>'
				if creds.domain is not None:
					ntlmcred.domain = '<CURRENT>'
				if creds.secret is not None:
					ntlmcred.password = '<CURRENT>'
				ntlmcred.is_guest = False
				ntlmcred.is_ssl = True if creds.authentication_type == SMBAuthProtocol.MULTIPLEXOR_SSL_NTLM else False
				ntlmcred.parse_settings(creds.settings)
				
				handler = SMBNTLMMultiplexor(ntlmcred)
				#setting up SPNEGO
				spneg = SPNEGO()
				spneg.add_auth_context('NTLMSSP - Microsoft NTLM Security Support Provider', handler)
				return spneg

			elif creds.authentication_type in [SMBAuthProtocol.MULTIPLEXOR_SSL_KERBEROS, SMBAuthProtocol.MULTIPLEXOR_KERBEROS]:
				from aiosmb.authentication.kerberos.multiplexor import SMBKerberosMultiplexor

				ntlmcred = SMBMultiplexorCredential()
				ntlmcred.type = 'KERBEROS'
				ntlmcred.target = creds.target
				if creds.username is not None:
					ntlmcred.username = '<CURRENT>'
				if creds.domain is not None:
					ntlmcred.domain = '<CURRENT>'
				if creds.secret is not None:
					ntlmcred.password = '<CURRENT>'
				ntlmcred.is_guest = False
				ntlmcred.is_ssl = True if creds.authentication_type == SMBAuthProtocol.MULTIPLEXOR_SSL_NTLM else False
				ntlmcred.parse_settings(creds.settings)

				handler = SMBKerberosMultiplexor(ntlmcred)
				#setting up SPNEGO
				spneg = SPNEGO()
				spneg.add_auth_context('MS KRB5 - Microsoft Kerberos 5', handler)
				return spneg
"""

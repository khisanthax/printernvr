"""Minimal authenticated ONVIF Device and PTZ client for the two verified cameras."""
import base64
from datetime import datetime, timezone
import hashlib
import os
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests
from requests.auth import HTTPDigestAuth

SOAP="http://www.w3.org/2003/05/soap-envelope"
DEVICE="http://www.onvif.org/ver10/device/wsdl"
PTZ="http://www.onvif.org/ver20/ptz/wsdl"
SCHEMA="http://www.onvif.org/ver10/schema"
WS="http://docs.oasis-open.org/wss/2004/01/"
SEC=WS+"oasis-200401-wss-wssecurity-secext-1.0.xsd"
UTIL=WS+"oasis-200401-wss-wssecurity-utility-1.0.xsd"


def element(parent,ns,name,text=None,**attrs):
    node=ET.SubElement(parent,"{"+ns+"}"+name,attrs)
    node.text=text
    return node


class OnvifPTZ:
    def __init__(self,host,port,user,password,profile):
        self.profile=profile
        self.user,self.password=user,password
        self.session=requests.Session()
        self.session.trust_env=False
        self.session.auth=HTTPDigestAuth(user,password)
        self.url=f"http://{host}:{port}/onvif/device_service"
        response=self.call(DEVICE,"GetCapabilities",lambda n:element(n,DEVICE,"Category","All"))
        address=response.find(".//{"+SCHEMA+"}PTZ/{"+SCHEMA+"}XAddr")
        if address is None or urlsplit(address.text).hostname!=host:
            raise RuntimeError("No same-host PTZ endpoint")
        self.url=address.text

    def call(self,ns,name,fill):
        root=ET.Element("{"+SOAP+"}Envelope")
        header=element(root,SOAP,"Header")
        token=element(element(header,SEC,"Security"),SEC,"UsernameToken")
        nonce=os.urandom(20)
        created=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        digest=hashlib.sha1(nonce+created.encode()+self.password.encode()).digest()
        element(token,SEC,"Username",self.user)
        element(token,SEC,"Password",base64.b64encode(digest).decode(),Type=WS+"oasis-200401-wss-username-token-profile-1.0#PasswordDigest")
        element(token,SEC,"Nonce",base64.b64encode(nonce).decode(),EncodingType=WS+"oasis-200401-wss-soap-message-security-1.0#Base64Binary")
        element(token,UTIL,"Created",created)
        fill(element(element(root,SOAP,"Body"),ns,name))
        r=self.session.post(self.url,data=ET.tostring(root,encoding="utf-8"),timeout=2,allow_redirects=False,
                            headers={"Content-Type":f'application/soap+xml; charset=utf-8; action="{ns}/{name}"'})
        parsed=ET.fromstring(r.content)
        if not r.ok or parsed.find(".//{"+ns+"}"+name+"Response") is None:
            raise RuntimeError("ONVIF "+name+" failed")
        return parsed

    def stop(self):
        def fill(n):
            element(n,PTZ,"ProfileToken",self.profile)
            element(n,PTZ,"PanTilt","true")
            element(n,PTZ,"Zoom","false")
        self.call(PTZ,"Stop",fill)

    def move(self,x,y):
        def fill(n):
            element(n,PTZ,"ProfileToken",self.profile)
            element(element(n,PTZ,"Velocity"),SCHEMA,"PanTilt",x=str(x),y=str(y))
            element(n,PTZ,"Timeout","PT1S")
        self.call(PTZ,"ContinuousMove",fill)
